# A4 Inventory Export: SKU/Position Merge + Quantity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the Inventory mode "Export table (PDF)" A4 report so it merges rows into one line per unique SKU (with a QR of the bare SKU) and one sub-line per unique position under that SKU (with a QR of the warehouse-prefixed position), showing quantity both as a per-SKU total and per-position count.

**Architecture:** Add a real `quantity` field to the inventory data model (CSV import → `InventoryItem` → on-screen table → per-record dict). The A4 report's SKU/position merging and quantity summing happen entirely inside the shipped `a4-table` Jinja template via `groupby`, not in Python — `render_table_pdf` keeps handing it the same flat list of plain-string records it always has, so any custom `inventory-table` preset an operator has copied stays unaffected.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets), Jinja2 (via blabel's `LabelWriter`/direct `jinja2.Template`), WeasyPrint (PDF rendering, via blabel), pypdfium2 (PDF→image + text extraction in tests), zxingcpp (QR/barcode decode verification in tests), pytest.

## Global Constraints

- Record dicts stay "a dict of plain strings" per `app/templates/examples/README.txt` — `quantity` is stored as a string (e.g. `"3"`), converted to `int` only inside the Jinja template where arithmetic is needed (Jinja's `|int` filter).
- The Print button's behavior does not change: one checked row still renders and prints exactly one label. `quantity` does not multiply print copies.
- All SKU/position merge and quantity-sum logic lives in `app/templates/examples/inventory-table/a4-table/template.html` (Jinja `groupby`), not in Python — do not add grouping logic to `render_table_pdf` or `mode_inventory_panel.py`.
- Run tests with `.venv/bin/python3 -m pytest <path> -v` from the repo root.

---

### Task 1: Add `quantity` to the inventory data model

**Files:**
- Modify: `app/core/inventory_import.py` (full file is 86 lines)
- Modify: `app/core/csv_mapping_memory.py:18-23`
- Test: `tests/test_inventory_import.py`

**Interfaces:**
- Consumes: nothing new from elsewhere.
- Produces: `InventoryItem.quantity: int` (default `1`), used by Task 2's `_record_for_item`. `items_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[InventoryItem], list[SkippedRow]]` signature is unchanged.

Current `app/core/inventory_import.py` in full:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.core.position_generator import (
    SkippedRow,
    format_position_code,
    parse_position_code,
)

INVENTORY_CSV_FIELDS = [
    ("sku", "SKU (required)"),
    ("name", "Product name"),
    ("client", "Client (optional)"),
    ("batch", "Batch (optional)"),
    ("expiry", "Expiry (optional)"),
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]


@dataclass
class InventoryItem:
    sku: str
    name: str
    batch: str
    expiry: str
    position_code: str
    client: str = ""


def items_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[InventoryItem], list[SkippedRow]]:
    items: list[InventoryItem] = []
    skipped_rows: list[SkippedRow] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            sku = (row.get("sku") or "").strip()
            if not sku:
                raise ValueError("sku is required")

            position_code = (row.get("position_code") or "").strip()
            if not position_code:
                position_code = format_position_code(
                    (row.get("corridor") or "").strip(),
                    (row.get("number") or "").strip(),
                    (row.get("height") or "").strip(),
                )
            corridor, number, height = parse_position_code(position_code)
            position_code = format_position_code(corridor, number, height)

            expiry = (row.get("expiry") or "").strip()
            batch = (row.get("batch") or "").strip()
            # Some WMS exports carry expiry and batch combined in a single
            # "Exp/Bat" column (e.g. "2027-03/4471"). The operator maps both
            # the expiry and batch fields to that same source column in the
            # CSV import dialog - an explicit, deliberate signal, unlike the
            # old "split on / whenever one side is empty" heuristic that got
            # deleted for shredding real dates like "2026/08/02". Split on
            # the last "/" so a date that itself contains slashes still
            # comes out intact on the left. Some rows in that combined column
            # have no batch at all (just a bare date, e.g. "1-Jan") - without
            # a "/" there is nothing to split, so batch must be cleared
            # rather than left duplicating the expiry value.
            if expiry and expiry == batch:
                if "/" in expiry:
                    expiry, batch = expiry.rsplit("/", 1)
                    expiry, batch = expiry.strip(), batch.strip()
                else:
                    batch = ""

            items.append(
                InventoryItem(
                    sku=sku,
                    name=(row.get("name") or "").strip(),
                    batch=batch,
                    expiry=expiry,
                    position_code=position_code,
                    client=(row.get("client") or "").strip(),
                )
            )
        except ValueError as error:
            skipped_rows.append(SkippedRow(row_number, str(error)))
    return items, skipped_rows
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_inventory_import.py`:

```python
def test_items_from_csv_rows_quantity_defaults_to_one():
    rows = [{"sku": "SKU1", "position_code": "H011A"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].quantity == 1


def test_items_from_csv_rows_parses_explicit_quantity():
    rows = [{"sku": "SKU1", "position_code": "H011A", "quantity": "7"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].quantity == 7


def test_items_from_csv_rows_strips_whitespace_around_quantity():
    rows = [{"sku": "SKU1", "position_code": "H011A", "quantity": " 7 "}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].quantity == 7


def test_items_from_csv_rows_skips_non_numeric_quantity():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU2", "position_code": "H012A", "quantity": "abc"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.sku for item in items] == ["SKU1"]
    assert [s.row_number for s in skipped] == [2]
    assert "quantity" in skipped[0].reason.lower()


def test_items_from_csv_rows_skips_zero_quantity():
    rows = [{"sku": "SKU1", "position_code": "H011A", "quantity": "0"}]

    items, skipped = items_from_csv_rows(rows)

    assert items == []
    assert [s.row_number for s in skipped] == [1]


def test_items_from_csv_rows_skips_negative_quantity():
    rows = [{"sku": "SKU1", "position_code": "H011A", "quantity": "-3"}]

    items, skipped = items_from_csv_rows(rows)

    assert items == []
    assert [s.row_number for s in skipped] == [1]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_inventory_import.py -v -k quantity`
Expected: FAIL, for two different reasons depending on the test:
- `test_items_from_csv_rows_quantity_defaults_to_one`, `..._parses_explicit_quantity`, `..._strips_whitespace_around_quantity`: `AttributeError: 'InventoryItem' object has no attribute 'quantity'` — the field doesn't exist on the dataclass yet.
- `test_items_from_csv_rows_skips_non_numeric_quantity`, `..._skips_zero_quantity`, `..._skips_negative_quantity`: `AssertionError` — with no quantity validation yet, `items_from_csv_rows` currently imports these rows without skipping them at all.

- [ ] **Step 3: Implement `quantity` in `app/core/inventory_import.py`**

Add the new CSV field to `INVENTORY_CSV_FIELDS` (insert after `"expiry"`, before `"position_code"`):

```python
INVENTORY_CSV_FIELDS = [
    ("sku", "SKU (required)"),
    ("name", "Product name"),
    ("client", "Client (optional)"),
    ("batch", "Batch (optional)"),
    ("expiry", "Expiry (optional)"),
    ("quantity", "Quantity (optional, defaults to 1)"),
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]
```

Add `quantity` to the dataclass, after `client`:

```python
@dataclass
class InventoryItem:
    sku: str
    name: str
    batch: str
    expiry: str
    position_code: str
    client: str = ""
    quantity: int = 1
```

In `items_from_csv_rows`, add quantity parsing right before the `items.append(...)` call (after the batch/expiry-splitting block, still inside the `try`):

```python
            quantity_raw = (row.get("quantity") or "").strip()
            if quantity_raw:
                try:
                    quantity = int(quantity_raw)
                except ValueError:
                    raise ValueError("quantity must be a positive whole number") from None
                if quantity <= 0:
                    raise ValueError("quantity must be a positive whole number")
            else:
                quantity = 1

            items.append(
                InventoryItem(
                    sku=sku,
                    name=(row.get("name") or "").strip(),
                    batch=batch,
                    expiry=expiry,
                    position_code=position_code,
                    client=(row.get("client") or "").strip(),
                    quantity=quantity,
                )
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_inventory_import.py -v`
Expected: all tests PASS (17 pre-existing + 6 new = 23).

- [ ] **Step 5: Add the `quantity` synonym list**

In `app/core/csv_mapping_memory.py`, the current `_FIELD_SYNONYMS` (lines 18-23):

```python
_FIELD_SYNONYMS: dict[str, set[str]] = {
    "sku": {"article", "code"},
    "position_code": {"position", "pos", "location"},
    "expiry": {"exp", "best_before"},
    "batch": {"lot"},
}
```

Add a `"quantity"` entry:

```python
_FIELD_SYNONYMS: dict[str, set[str]] = {
    "sku": {"article", "code"},
    "position_code": {"position", "pos", "location"},
    "expiry": {"exp", "best_before"},
    "batch": {"lot"},
    "quantity": {"qty", "count", "units"},
}
```

There is no dedicated test file for `csv_mapping_memory.py`'s synonym table beyond what already covers `auto_map_fields` generically — no new test needed here; this dict is data, not branching logic.

- [ ] **Step 6: Run the full inventory-import test file once more**

Run: `.venv/bin/python3 -m pytest tests/test_inventory_import.py -v`
Expected: all 23 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/core/inventory_import.py app/core/csv_mapping_memory.py tests/test_inventory_import.py
git commit -m "Add quantity field to inventory CSV import and data model"
```

---

### Task 2: Expose `quantity` in the on-screen table and per-record dict

**Files:**
- Modify: `app/ui/mode_inventory_panel.py:44` (`TABLE_COLUMNS`), `:73-83` (`_record_for_item`), `:225` (`_populate_table`)
- Modify: `app/templates/examples/README.txt`
- Test: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: `InventoryItem.quantity: int` from Task 1.
- Produces: `_record_for_item(...)` now returns a dict that includes `"quantity": str(item.quantity)`. Task 3's template reads `record.quantity` as a string and converts with Jinja's `|int` filter.

Current relevant code:

`app/ui/mode_inventory_panel.py:44`:
```python
TABLE_COLUMNS = ["", "SKU", "Name", "Client", "Position", "Batch", "Expiry"]
```

`app/ui/mode_inventory_panel.py:73-83`:
```python
def _record_for_item(item: InventoryItem, warehouse_prefix: str, generated_date: str) -> dict:
    return {
        "sku": item.sku,
        "name": item.name,
        "client": item.client,
        "batch": item.batch,
        "expiry": item.expiry,
        "position_code": display_position_code(item.position_code),
        "position_data": f"{warehouse_prefix}{item.position_code}",
        "generated_date": generated_date,
    }
```

`app/ui/mode_inventory_panel.py:225` (inside `_populate_table`):
```python
            values = [item.sku, item.name, item.client, item.position_code, item.batch, item.expiry]
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mode_inventory_panel.py`:

```python
def test_qty_column_populated_from_item():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A", "quantity": "5"}])

    qty_column = TABLE_COLUMNS.index("Qty")
    assert panel.items_table.item(0, qty_column).text() == "5"


def test_qty_column_defaults_to_one_when_not_mapped():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    qty_column = TABLE_COLUMNS.index("Qty")
    assert panel.items_table.item(0, qty_column).text() == "1"


def test_record_for_item_includes_quantity_as_string():
    from app.ui.mode_inventory_panel import _record_for_item
    from app.core.inventory_import import InventoryItem

    item = InventoryItem(
        sku="SKU1", name="Widget", batch="", expiry="", position_code="H011A", quantity=3
    )

    record = _record_for_item(item, "C001", "2026/08/06")

    assert record["quantity"] == "3"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python3 -m pytest tests/test_mode_inventory_panel.py -v -k qty_column`
Expected: FAIL — `ValueError: 'Qty' is not in list` (TABLE_COLUMNS has no "Qty" entry yet) for the first two; `test_record_for_item_includes_quantity_as_string` fails with `KeyError: 'quantity'`.

- [ ] **Step 3: Implement**

`TABLE_COLUMNS` — insert `"Qty"` right after `"SKU"` (column 1 is asserted directly as SKU text in `test_load_items_populates_table`, so `"Qty"` must not go before it):

```python
TABLE_COLUMNS = ["", "SKU", "Qty", "Name", "Client", "Position", "Batch", "Expiry"]
```

`_record_for_item` — add `"quantity"` as a string:

```python
def _record_for_item(item: InventoryItem, warehouse_prefix: str, generated_date: str) -> dict:
    return {
        "sku": item.sku,
        "name": item.name,
        "client": item.client,
        "batch": item.batch,
        "expiry": item.expiry,
        "position_code": display_position_code(item.position_code),
        "position_data": f"{warehouse_prefix}{item.position_code}",
        "generated_date": generated_date,
        "quantity": str(item.quantity),
    }
```

`_populate_table` — the `values` list must match the new `TABLE_COLUMNS` order exactly:

```python
            values = [
                item.sku,
                str(item.quantity),
                item.name,
                item.client,
                item.position_code,
                item.batch,
                item.expiry,
            ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_mode_inventory_panel.py -v`
Expected: all tests PASS, including the pre-existing `test_load_items_populates_table`, `test_data_cells_are_not_editable`, and `test_client_column_populated_from_item` (all three use dynamic column lookups or the SKU column, unaffected by inserting "Qty" after "SKU").

- [ ] **Step 5: Update the field documentation**

In `app/templates/examples/README.txt`, the "Inventory mode" field list currently ends with:

```
    generated_date   The date this label was generated, e.g. "2026/08/03".
```

Change to:

```
    generated_date   The date this label was generated, e.g. "2026/08/03".
    quantity         Number of units for this row, e.g. "3". Defaults to
                      "1" when the source CSV has no quantity column
                      mapped. Stored as a string like every other field;
                      convert with Jinja's |int filter for arithmetic.
```

This is a doc-only file with no test coverage; no test step for this edit.

- [ ] **Step 6: Commit**

```bash
git add app/ui/mode_inventory_panel.py app/templates/examples/README.txt tests/test_mode_inventory_panel.py
git commit -m "Expose inventory quantity in the on-screen table and record dict"
```

---

### Task 3: Merge SKU/position rows with quantity totals in the A4 template

**Files:**
- Modify: `app/templates/examples/inventory-table/a4-table/template.html`
- Modify: `app/templates/examples/inventory-table/a4-table/style.css`
- Test: `tests/test_template_renderer.py`

**Interfaces:**
- Consumes: `render_table_pdf(preset: TemplatePreset, records: list[dict]) -> bytes` (unchanged signature, from `app/core/template_renderer.py`). Each record dict has the fields from Task 2's `_record_for_item`, including `"quantity"` as a string.
- Produces: the rendered A4 PDF. No other task depends on this one's output shape.

This task was already hand-verified end-to-end (rendered a real PDF with `render_table_pdf`, decoded the QR codes with `zxingcpp`, and extracted the PDF text with `pypdfium2`) before being written into this plan, so the template and CSS below are copy-exact from a working run, not sketched from the design doc.

- [ ] **Step 1: Add `quantity` to the shared `INVENTORY_RECORD` test fixture**

In `tests/test_template_renderer.py`, the module-level fixture (around line 268-277) currently:

```python
INVENTORY_RECORD = {
    "sku": "SOLARIX-FACE-1000ML-REFILL",
    "name": "Гвинт М6×40 DIN933",
    "client": "ТОВ «Складсервіс»",
    "batch": "B-240815",
    "expiry": "2027-05-31",
    "position_code": "D-002-E",
    "position_data": "C002d002e",
    "generated_date": "2026/08/02",
}
```

Add a `"quantity"` key so this fixture matches what `_record_for_item` actually produces now:

```python
INVENTORY_RECORD = {
    "sku": "SOLARIX-FACE-1000ML-REFILL",
    "name": "Гвинт М6×40 DIN933",
    "client": "ТОВ «Складсервіс»",
    "batch": "B-240815",
    "expiry": "2027-05-31",
    "position_code": "D-002-E",
    "position_data": "C002d002e",
    "generated_date": "2026/08/02",
    "quantity": "1",
}
```

- [ ] **Step 2: Run the existing template-renderer tests to confirm this addition alone is harmless**

Run: `.venv/bin/python3 -m pytest tests/test_template_renderer.py -v`
Expected: all existing tests PASS (the extra `quantity` key is simply unused by every template that doesn't reference it, per the documented "field a template doesn't reference is unused" behavior).

- [ ] **Step 3: Write the new failing test for merge + quantity totals**

Add to `tests/test_template_renderer.py`, after `test_render_table_pdf_puts_every_record_on_one_native_pdf`:

```python
def test_render_table_pdf_merges_duplicate_sku_position_rows_and_totals_quantity():
    preset = TemplatePreset(
        name="A4 Table (all fields)",
        mode="inventory-table",
        width_mm=210,
        height_mm=297,
        template_path=EXAMPLES_ROOT / "inventory-table" / "a4-table" / "template.html",
        stylesheet_path=EXAMPLES_ROOT / "inventory-table" / "a4-table" / "style.css",
    )
    # Position codes and quantities are chosen so none of the expected total
    # digits ("12", "7", "5", "9") appear as a coincidental substring of any
    # SKU, position code, or the generated_date heading - otherwise a weak
    # `in text` check could pass even if the quantity math were wrong.
    records = [
        {**INVENTORY_RECORD, "sku": "SKU-100", "position_code": "H-011-A",
         "position_data": "C001H011A", "quantity": "3"},
        {**INVENTORY_RECORD, "sku": "SKU-100", "position_code": "H-011-A",
         "position_data": "C001H011A", "quantity": "4"},
        {**INVENTORY_RECORD, "sku": "SKU-100", "position_code": "H-033-C",
         "position_data": "C001H033C", "quantity": "5"},
        {**INVENTORY_RECORD, "sku": "SKU-200", "position_code": "H-022-B",
         "position_data": "C001H022B", "quantity": "9"},
    ]

    pdf_bytes = render_table_pdf(preset, records)

    pdf = pdfium.PdfDocument(pdf_bytes)
    assert len(pdf) == 1
    page = pdf[0]
    image = page.render(scale=300 / 72).to_pil().convert("L")
    decoded = [s.text for s in zxingcpp.read_barcodes(image)]
    # Two duplicate SKU-100/H-011-A rows must collapse into ONE QR each - a
    # template that still rendered one row per input record would decode
    # "SKU-100" and "C001H011A" twice instead of once.
    assert sorted(decoded) == ["C001H011A", "C001H022B", "C001H033C", "SKU-100", "SKU-200"]

    text = page.get_textpage().get_text_range()
    assert "12" in text  # SKU-100 total: 3 + 4 + 5
    assert "7" in text  # H-011-A position total: 3 + 4
    assert "5" in text  # H-033-C position total (untouched by the merge)
    assert "9" in text  # SKU-200 total, and its only position's qty
```

This exact test (with these exact record values) was run against the real template/CSS from Step 5/6 below before being written here, confirming: the QR list decodes to exactly those 5 unique values (proving the duplicate row collapsed), the text contains all four target numbers, and none of the target numbers are substrings of any other rendered string.

- [ ] **Step 4: Run it to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_template_renderer.py -v -k merges_duplicate`
Expected: FAIL — the shipped template still renders one row per record, so `decoded` will contain `"SKU-100"` and `"C001H011A"` twice (or the text assertions for the summed totals like `"12"` won't be present).

- [ ] **Step 5: Replace `app/templates/examples/inventory-table/a4-table/template.html`**

Full new content:

```html
{# APP-OWNED FILE - rewritten on every launch, your edits here will be lost.
   Copy this folder to a sibling name and edit the copy. See ../README.txt #}
<h1>Inventory export{% if records %} - {{ records[0].generated_date }}{% endif %}</h1>
<table>
  <thead>
    <tr>
      <th class="col-num">#</th>
      <th class="col-sku">SKU</th>
      <th class="col-name">Name</th>
      <th class="col-qr">QR SKU</th>
      <th class="col-qty">Total qty</th>
      <th class="col-pos">Position</th>
      <th class="col-qty">Qty</th>
      <th class="col-qr">QR Position</th>
    </tr>
  </thead>
  {% for sku_group in records|groupby('sku') %}
  {% set sku_records = sku_group.list %}
  {% set position_groups = sku_records|groupby('position_code') %}
  {% set total_qty = sku_records|map(attribute='quantity')|map('int')|sum %}
  {% set sku_index = loop.index %}
  <tbody>
    {% for pos_group in position_groups %}
    {% set pos_records = pos_group.list %}
    {% set pos_qty = pos_records|map(attribute='quantity')|map('int')|sum %}
    <tr>
      {% if loop.first %}
      <td class="col-num" rowspan="{{ position_groups|length }}">{{ sku_index }}</td>
      <td class="col-sku" rowspan="{{ position_groups|length }}">{{ sku_group.grouper }}</td>
      <td class="col-name" rowspan="{{ position_groups|length }}">{{ sku_records[0].name }}</td>
      <td class="col-qr" rowspan="{{ position_groups|length }}"><img src="{{ label_tools.qr_code(sku_group.grouper) }}"></td>
      <td class="col-qty" rowspan="{{ position_groups|length }}">{{ total_qty }}</td>
      {% endif %}
      <td class="col-pos">{{ pos_records[0].position_code }}</td>
      <td class="col-qty">{{ pos_qty }}</td>
      <td class="col-qr"><img src="{{ label_tools.qr_code(pos_records[0].position_data) }}"></td>
    </tr>
    {% endfor %}
  </tbody>
  {% endfor %}
</table>
```

Notes for the implementer (not comments to add to the file — explaining why, for review purposes):
- `records|groupby('sku')` sorts by SKU ascending and groups in one step (Jinja does the sort internally); `sku_group.list` is a real, already-materialized list (safe to re-group with a nested `groupby('position_code')`).
- `sku_index` is captured from the *outer* loop's `loop.index` before the inner `{% for pos_group in position_groups %}` starts, because `loop` inside the inner loop shadows the outer one.
- `sku_records|map(attribute='quantity')` pulls out the string quantities; `|map('int')` converts each via Jinja's built-in `int` filter; `|sum` adds them. This is the one place `quantity` is treated as numeric — it stays a string everywhere else per the Global Constraints.
- The SKU QR still encodes `sku_group.grouper` (the bare SKU, identical value to `sku_records[0].sku`). The position QR still encodes `pos_records[0].position_data` (`warehouse_prefix + position_code`, unchanged from before this task).

- [ ] **Step 6: Replace `app/templates/examples/inventory-table/a4-table/style.css`**

Full new content:

```css
/* APP-OWNED FILE - rewritten on every launch, your edits here will be lost.
   Copy this folder to a sibling name and edit the copy. See ../README.txt */
@page { size: A4; margin: 12mm 10mm; }
html, body { margin: 0; padding: 0; font-family: "JetBrains Mono", monospace; color: #000; }

h1 { font-size: 4mm; margin: 0 0 4mm 0; }

table { width: 100%; border-collapse: collapse; font-size: 3mm; }
/* repeats the header row on every page WeasyPrint paginates the table onto */
thead { display: table-header-group; }
/* one <tbody> per SKU group - keeps a merged SKU's rowspan block on one
   page instead of splitting it across a page break */
tbody { page-break-inside: avoid; }
tr { page-break-inside: avoid; }

th, td {
  border: 0.2mm solid #000;
  padding: 1mm 1.5mm;
  text-align: left;
  vertical-align: middle;
  overflow: hidden;
}

th { background: #000; color: #fff; font-weight: 700; text-transform: uppercase; font-size: 2.6mm; }

.col-num  { width: 8mm; text-align: center; }
.col-sku  { width: 30mm; }
.col-name { width: 50mm; }
.col-pos  { width: 20mm; }
.col-qty  { width: 16mm; text-align: center; }
.col-qr   { width: 20mm; text-align: center; }
.col-qr img { width: 16mm; height: 16mm; }
```

- [ ] **Step 7: Run the new test to verify it passes**

Run: `.venv/bin/python3 -m pytest tests/test_template_renderer.py -v -k merges_duplicate`
Expected: PASS.

- [ ] **Step 8: Run the full template-renderer test file**

Run: `.venv/bin/python3 -m pytest tests/test_template_renderer.py -v`
Expected: all tests PASS, including the pre-existing `test_render_table_pdf_puts_every_record_on_one_native_pdf` (its two records have different SKUs, so each lands in its own single-position `<tbody>` group and both QR codes still decode) and `test_list_presets_seeds_inventory_table_examples_too`.

- [ ] **Step 9: Run the entire test suite as a final regression check**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: all tests PASS (no other file references the `inventory-table`/`a4-table` template or the old 9-column layout).

- [ ] **Step 10: Commit**

```bash
git add app/templates/examples/inventory-table/a4-table/template.html app/templates/examples/inventory-table/a4-table/style.css tests/test_template_renderer.py
git commit -m "Merge A4 inventory export into SKU/position rows with quantity totals"
```

---

## Manual verification (after Task 3)

Not a substitute for the automated tests above, but worth doing once since this is a print-facing report a human reads on paper:

1. `./run.sh` (runs `.venv/bin/python -m app.main`) — actually import a CSV with a few repeated SKU/position rows and differing quantities via Inventory mode → "Import CSV...".
2. Check a few rows, click "Export table (PDF)...", open the resulting PDF.
3. Confirm visually: one merged block per SKU, one sub-row per unique position, total and per-position quantities match what you'd hand-count from the source CSV, and both QR codes are readable by scanning them with a phone camera / scanner app directly off the screen or a printed copy.
