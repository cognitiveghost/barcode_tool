# Mode 2.2 — Inventory Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Mode 2.2 (Inventory from CSV) — import a stock CSV, review and select which SKU-position labels to print in a checkable table, and print the chosen batch (SKU QR + text + position QR per label) through the existing print/audit pipeline.

**Architecture:** Same layering as Mode 2.1 and the CSV import infrastructure — pure logic in `app/core/` (QR generation added to `barcode_engine.py`; a new strict position-code validator added to `position_generator.py`; a new `inventory_import.py` for CSV-row-to-item parsing; a new `render_inventory_label` added to `label_renderer.py`), a new Qt panel in `app/ui/mode_inventory_panel.py` that reuses the existing generic `CsvImportDialog` unmodified, and `main_window.py` gains a `QTabWidget` to host the Positions and Inventory panels side by side (the first second-panel addition, so it sets the pattern Modes 2.3/2.4 will reuse).

**Tech Stack:** Python 3.11+, `qrcode` (new dependency — both codes on this label are QR per the design decision, not Code128), PySide6, Pillow, pytest.

## Global Constraints

- The application and all code/comments must be in English.
- No emojis anywhere in the UI.
- Must run locally on Windows 10/11 and Ubuntu 25+.
- The warehouse prefix must be embedded in the position code's encoded data
  but must **never** appear in the visible printed text/caption.
- The SKU QR encodes the raw SKU with no warehouse prefix — SKUs are already
  globally unique, unlike position codes.
- No database — plain files only.
- Mode 2.1's existing CSV-import position-code path (`codes_from_csv_rows`)
  must not change behavior. Mode 2.2 adds a new, separate, stricter
  validator (`parse_position_code`) rather than modifying the shared one —
  Mode 2.1 deliberately accepts any ASCII string as a pre-formed position
  code, and that's a shipped behavior this plan must not touch.

Full design rationale:
`docs/superpowers/specs/2026-07-31-mode-2-2-inventory-design.md` and
`docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md`.

---

## Task 1: QR code generation (`barcode_engine.py`)

**Files:**
- Modify: `app/core/barcode_engine.py`
- Modify: `requirements.txt`
- Test: `tests/test_barcode_engine.py`

**Interfaces:**
- Consumes: nothing beyond the `qrcode` library.
- Produces: `generate_qr_image(data: str) -> Image.Image` — same shape as the
  existing `generate_barcode_image`, usable anywhere a `PIL.Image.Image` is
  expected (resize, paste, etc.).

- [ ] **Step 1: Write the failing tests**

Replace the top import line of `tests/test_barcode_engine.py` and add two tests:

```python
from PIL import Image

from app.core.barcode_engine import generate_barcode_image, generate_qr_image


def test_generate_barcode_image_returns_image():
    img = generate_barcode_image("C001H029A")
    assert isinstance(img, Image.Image)
    assert img.width > 0
    assert img.height > 0


def test_different_data_produces_different_image():
    img_a = generate_barcode_image("C001H029A")
    img_b = generate_barcode_image("C001H030A")
    assert img_a.tobytes() != img_b.tobytes()


def test_generate_qr_image_returns_image():
    img = generate_qr_image("SKU123")
    assert isinstance(img, Image.Image)
    assert img.width > 0
    assert img.height > 0


def test_different_qr_data_produces_different_image():
    img_a = generate_qr_image("SKU123")
    img_b = generate_qr_image("SKU456")
    assert img_a.tobytes() != img_b.tobytes()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_barcode_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'generate_qr_image'` (a
collection error, so every test in the file fails until Step 3 lands — this
is expected and resolves once the import succeeds).

- [ ] **Step 3: Add the dependency and implement**

Add to `requirements.txt` (after `python-barcode`):
```
qrcode>=7.4
```

Install it: `pip install -r requirements.txt`

Replace `app/core/barcode_engine.py`:
```python
from __future__ import annotations

import barcode
import qrcode
from barcode.writer import ImageWriter
from PIL import Image


def generate_barcode_image(data: str) -> Image.Image:
    code = barcode.get("code128", data, writer=ImageWriter())
    return code.render(writer_options={"write_text": False})


def generate_qr_image(data: str) -> Image.Image:
    return qrcode.make(data).get_image()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_barcode_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/barcode_engine.py requirements.txt tests/test_barcode_engine.py
git commit -m "feat: add QR code generation to barcode_engine"
```

---

## Task 2: Strict position-code validation (`position_generator.py`)

**Files:**
- Modify: `app/core/position_generator.py`
- Modify: `tests/test_position_generator.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `parse_position_code(code: str) -> tuple[str, str, str]` —
  returns `(corridor, number, height)` if `code` matches
  `<single letter><digits><optional single letter>` (e.g. `H011A` ->
  `("H", "011", "A")`, `H011` -> `("H", "011", "")`). Raises `ValueError`
  otherwise. Used only by Mode 2.2 — `format_position_code` and
  `generate_position_codes` (Mode 2.1) are untouched.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_position_generator.py` (extend the existing import line
with `parse_position_code`):

```python
from app.core.position_generator import (
    codes_from_csv_rows,
    format_position_code,
    generate_position_codes,
    parse_position_code,
)
```

```python
def test_parse_position_code_with_height():
    assert parse_position_code("H011A") == ("H", "011", "A")


def test_parse_position_code_without_height():
    assert parse_position_code("H011") == ("H", "011", "")


def test_parse_position_code_rejects_missing_number():
    with pytest.raises(ValueError):
        parse_position_code("H")


def test_parse_position_code_rejects_multi_letter_corridor():
    with pytest.raises(ValueError):
        parse_position_code("HH011A")


def test_parse_position_code_rejects_malformed_string():
    with pytest.raises(ValueError):
        parse_position_code("not-a-position")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_position_generator.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_position_code'`
(collection error — every test in the file fails until Step 3 lands).

- [ ] **Step 3: Implement**

Add `import re` as the first line after `from __future__ import annotations`
in `app/core/position_generator.py`, and append this to the end of the file:

```python
_POSITION_CODE_PATTERN = re.compile(r"^[A-Za-z]\d+[A-Za-z]?$")


def parse_position_code(code: str) -> tuple[str, str, str]:
    if not _POSITION_CODE_PATTERN.match(code):
        raise ValueError(
            f"position code {code!r} must be a letter, digits, and an "
            "optional trailing letter (e.g. H011A)"
        )
    corridor = code[0]
    if code[-1].isalpha():
        return corridor, code[1:-1], code[-1]
    return corridor, code[1:], ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_position_generator.py -v`
Expected: PASS — including every pre-existing test in this file.

- [ ] **Step 5: Commit**

```bash
git add app/core/position_generator.py tests/test_position_generator.py
git commit -m "feat: strict position-code format validation for inventory import"
```

---

## Task 3: Inventory CSV row parsing (`inventory_import.py`)

**Files:**
- Create: `app/core/inventory_import.py`
- Test: `tests/test_inventory_import.py`

**Interfaces:**
- Consumes: `app.core.position_generator.{format_position_code, parse_position_code}` (Task 2).
- Produces:
  - `InventoryItem` — dataclass with fields `sku: str, name: str, batch: str, expiry: str, position_code: str`.
  - `INVENTORY_CSV_FIELDS: list[tuple[str, str]]` — field list for `CsvImportDialog`.
  - `items_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[InventoryItem], list[int]]` —
    mirrors `codes_from_csv_rows`'s skip-and-continue shape: returns
    `(items, skipped_row_numbers)`, 1-indexed skip list. A row is skipped if
    `sku` is empty, or if the resolved position code (direct
    `position_code` column, or built from `corridor`/`number`/`height`) is
    empty or fails `parse_position_code`. `name`/`batch`/`expiry` default to
    `""` and never cause a skip.

- [ ] **Step 1: Write the failing tests**

`tests/test_inventory_import.py`:
```python
from app.core.inventory_import import InventoryItem, items_from_csv_rows


def test_items_from_csv_rows_builds_items_with_position_code_column():
    rows = [
        {
            "sku": "SKU1",
            "name": "Widget",
            "batch": "4471",
            "expiry": "2027-03",
            "position_code": "H011A",
        },
    ]

    items, skipped = items_from_csv_rows(rows)

    assert items == [
        InventoryItem(sku="SKU1", name="Widget", batch="4471", expiry="2027-03", position_code="H011A")
    ]
    assert skipped == []


def test_items_from_csv_rows_builds_position_from_components():
    rows = [{"sku": "SKU1", "corridor": "H", "number": "11", "height": "A"}]

    items, skipped = items_from_csv_rows(rows)

    assert items[0].position_code == "H011A"
    assert skipped == []


def test_items_from_csv_rows_optional_fields_default_empty():
    rows = [{"sku": "SKU1", "position_code": "H011A"}]

    items, skipped = items_from_csv_rows(rows)

    assert items[0].name == ""
    assert items[0].batch == ""
    assert items[0].expiry == ""


def test_items_from_csv_rows_skips_missing_sku():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "", "position_code": "H012A"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.sku for item in items] == ["SKU1"]
    assert skipped == [2]


def test_items_from_csv_rows_skips_malformed_position_code():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU2", "position_code": "not-a-position"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.sku for item in items] == ["SKU1"]
    assert skipped == [2]


def test_items_from_csv_rows_keeps_multiple_positions_for_same_sku():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU1", "position_code": "H014B"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.position_code for item in items] == ["H011A", "H014B"]
    assert skipped == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_inventory_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.inventory_import'`

- [ ] **Step 3: Implement**

`app/core/inventory_import.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from app.core.position_generator import format_position_code, parse_position_code

INVENTORY_CSV_FIELDS = [
    ("sku", "SKU (required)"),
    ("name", "Product name"),
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


def items_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[InventoryItem], list[int]]:
    items: list[InventoryItem] = []
    skipped_rows: list[int] = []
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
            parse_position_code(position_code)

            items.append(
                InventoryItem(
                    sku=sku,
                    name=(row.get("name") or "").strip(),
                    batch=(row.get("batch") or "").strip(),
                    expiry=(row.get("expiry") or "").strip(),
                    position_code=position_code,
                )
            )
        except ValueError:
            skipped_rows.append(row_number)
    return items, skipped_rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_inventory_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/inventory_import.py tests/test_inventory_import.py
git commit -m "feat: CSV row parsing for inventory items"
```

---

## Task 4: Inventory label rendering (`label_renderer.py`)

**Files:**
- Modify: `app/core/label_renderer.py`
- Test: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: `app.core.barcode_engine.generate_qr_image` (Task 1).
- Produces: `render_inventory_label(sku_data: str, text: str, position_data: str, width_mm: float, height_mm: float, dpi: int = 203) -> Image.Image`.
  Layout: SKU QR (left) + text (right) fill the top ~70% of the label; a
  horizontal divider; a smaller position QR + "shelf position" caption in
  the remaining strip below.

- [ ] **Step 1: Write the failing tests**

Replace the top import line of `tests/test_label_renderer.py` and add four
tests:

```python
from PIL import Image

from app.core.label_renderer import font_size_for_height, mm_to_px, render_inventory_label, render_label


def test_mm_to_px_at_203_dpi():
    assert mm_to_px(25.4, dpi=203) == 203


def test_font_size_scales_with_label_height():
    assert font_size_for_height(1198) > font_size_for_height(304) > font_size_for_height(100)


def test_render_label_returns_image_of_expected_size():
    img = render_label("C001H029A", "H029A", width_mm=68, height_mm=38, dpi=203)
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(68, 203), mm_to_px(38, 203))


def test_render_label_visible_text_differs_from_barcode_data_changes_output():
    img_with_prefix_text = render_label("C001H029A", "C001H029A", width_mm=68, height_mm=38)
    img_without_prefix_text = render_label("C001H029A", "H029A", width_mm=68, height_mm=38)
    assert img_with_prefix_text.tobytes() != img_without_prefix_text.tobytes()


def test_render_inventory_label_returns_image_of_expected_size():
    img = render_inventory_label("SKU1", "Widget\nBatch 4471", "C001H011A", width_mm=68, height_mm=38, dpi=203)
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(68, 203), mm_to_px(38, 203))


def test_render_inventory_label_changes_with_sku_data():
    img_a = render_inventory_label("SKU1", "Widget", "C001H011A", width_mm=68, height_mm=38)
    img_b = render_inventory_label("SKU2", "Widget", "C001H011A", width_mm=68, height_mm=38)
    assert img_a.tobytes() != img_b.tobytes()


def test_render_inventory_label_changes_with_position_data():
    img_a = render_inventory_label("SKU1", "Widget", "C001H011A", width_mm=68, height_mm=38)
    img_b = render_inventory_label("SKU1", "Widget", "C001H099Z", width_mm=68, height_mm=38)
    assert img_a.tobytes() != img_b.tobytes()


def test_render_inventory_label_changes_with_text():
    img_a = render_inventory_label("SKU1", "Widget", "C001H011A", width_mm=68, height_mm=38)
    img_b = render_inventory_label("SKU1", "Gadget", "C001H011A", width_mm=68, height_mm=38)
    assert img_a.tobytes() != img_b.tobytes()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_renderer.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_inventory_label'`
(collection error — every test in the file fails until Step 3 lands).

- [ ] **Step 3: Implement**

Change the barcode_engine import line at the top of
`app/core/label_renderer.py` to:
```python
from app.core.barcode_engine import generate_barcode_image, generate_qr_image
```

Append this function to the end of the file:
```python
def render_inventory_label(
    sku_data: str,
    text: str,
    position_data: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)
    canvas = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(canvas)

    top_height = round(height_px * 0.7)
    sku_qr = generate_qr_image(sku_data)
    sku_size = min(top_height - 4, width_px // 2)
    sku_qr = sku_qr.resize((sku_size, sku_size))
    canvas.paste(sku_qr, (0, 0))

    text_font = ImageFont.load_default(size=font_size_for_height(top_height))
    draw.multiline_text((sku_size + 6, 2), text, fill="black", font=text_font)

    draw.line([(0, top_height), (width_px, top_height)], fill="black", width=1)

    bottom_height = height_px - top_height
    position_qr = generate_qr_image(position_data)
    position_size = max(1, min(bottom_height - 4, width_px // 4))
    position_qr = position_qr.resize((position_size, position_size))
    position_y = top_height + max(0, (bottom_height - position_size) // 2)
    canvas.paste(position_qr, (4, position_y))

    caption_font = ImageFont.load_default(size=font_size_for_height(bottom_height))
    draw.text((position_size + 10, top_height + 4), "shelf position", fill="black", font=caption_font)

    return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_label_renderer.py -v`
Expected: PASS — including every pre-existing test in this file.

- [ ] **Step 5: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "feat: two-QR inventory label rendering"
```

---

## Task 5: Inventory panel — CSV import + selectable table (`mode_inventory_panel.py`)

**Files:**
- Create: `app/ui/mode_inventory_panel.py`
- Test: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes:
  - `app.core.inventory_import.{InventoryItem, INVENTORY_CSV_FIELDS, items_from_csv_rows}` (Task 3)
  - `app.ui.csv_import_dialog.CsvImportDialog` (existing, unmodified)
- Produces (`InventoryModePanel` — Task 6 extends this same class):
  - `__init__(self, settings: dict, parent=None)`
  - `refresh_from_settings(self, settings: dict) -> None`
  - Widgets: `warehouse_combo`, `label_size_combo`, `import_csv_button`,
    `select_all_button`, `select_none_button`, `items_table`,
    `result_label`, `print_button` (created here, wired to a handler in
    Task 6)
  - `items: list[InventoryItem]`
  - `load_items(self, rows: list[dict[str, str]]) -> list[InventoryItem]` —
    raises `ValueError` if zero valid items result.
  - `checked_items(self) -> list[InventoryItem]`

- [ ] **Step 1: Write the failing tests**

`tests/test_mode_inventory_panel.py`:
```python
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.mode_inventory_panel import InventoryModePanel

SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
    "label_sizes": [{"name": "68x38mm", "width_mm": 68, "height_mm": 38}],
}


def _app():
    return QApplication.instance() or QApplication([])


def test_load_items_populates_table():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "name": "Widget", "position_code": "H011A"},
        {"sku": "SKU2", "name": "Gadget", "position_code": "H012A"},
    ]

    items = panel.load_items(rows)

    assert [item.sku for item in items] == ["SKU1", "SKU2"]
    assert panel.items_table.rowCount() == 2
    assert panel.items_table.item(0, 1).text() == "SKU1"
    assert panel.result_label.text() == "2 items imported"


def test_load_items_reports_skipped_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "", "position_code": "H012A"},
    ]

    panel.load_items(rows)

    assert panel.result_label.text() == "1 item imported (1 row skipped)"


def test_load_items_raises_when_no_valid_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [{"sku": "", "position_code": "H011A"}]

    with pytest.raises(ValueError):
        panel.load_items(rows)


def test_rows_are_checked_by_default():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    assert panel.checked_items()[0].sku == "SKU1"


def test_select_none_then_select_all():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )

    panel.select_none_button.click()
    assert panel.checked_items() == []

    panel.select_all_button.click()
    assert [item.sku for item in panel.checked_items()] == ["SKU1", "SKU2"]


def test_unchecking_one_row_excludes_it_from_checked_items():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )

    panel.items_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)

    assert [item.sku for item in panel.checked_items()] == ["SKU2"]


def test_import_csv_button_opens_dialog_and_loads_items(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    fake_rows = [{"sku": "SKU1", "position_code": "H011A"}]

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return fake_rows

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert [item.sku for item in panel.items] == ["SKU1"]


def test_import_csv_button_does_nothing_when_dialog_cancelled(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return False

        def get_mapped_rows(self):
            raise AssertionError("should not be called when the dialog is cancelled")

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert panel.items == []


def test_import_csv_button_shows_warning_when_no_valid_rows(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return [{"sku": "", "position_code": "H011A"}]

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.import_csv_button.click()

    assert len(warnings) == 1


def test_refresh_from_settings_rebuilds_combos():
    _app()
    panel = InventoryModePanel(SETTINGS)

    panel.refresh_from_settings(
        {
            "warehouses": [{"name": "Second", "prefix": "C002"}],
            "label_sizes": [{"name": "80x80mm", "width_mm": 80, "height_mm": 80}],
        }
    )

    warehouse_names = [panel.warehouse_combo.itemText(i) for i in range(panel.warehouse_combo.count())]
    label_size_names = [panel.label_size_combo.itemText(i) for i in range(panel.label_size_combo.count())]
    assert warehouse_names == ["Second"]
    assert label_size_names == ["80x80mm"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.mode_inventory_panel'`

- [ ] **Step 3: Implement**

`app/ui/mode_inventory_panel.py`:
```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.inventory_import import INVENTORY_CSV_FIELDS, InventoryItem, items_from_csv_rows
from app.ui.csv_import_dialog import CsvImportDialog

TABLE_COLUMNS = ["", "SKU", "Name", "Position", "Batch", "Expiry"]


class InventoryModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.items: list[InventoryItem] = []

        self.warehouse_combo = QComboBox()
        self.label_size_combo = QComboBox()
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 items imported")

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))

        self.items_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(TABLE_COLUMNS)

        self.print_button = QPushButton("Print")

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Label size", self.label_size_combo)

        select_buttons = QHBoxLayout()
        select_buttons.addWidget(self.select_all_button)
        select_buttons.addWidget(self.select_none_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.import_csv_button)
        layout.addWidget(self.result_label)
        layout.addLayout(select_buttons)
        layout.addWidget(self.items_table)
        layout.addWidget(self.print_button)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        self.label_size_combo.clear()
        for size in settings.get("label_sizes", []):
            self.label_size_combo.addItem(size["name"], size)

    def load_items(self, rows: list[dict[str, str]]) -> list[InventoryItem]:
        items, skipped_rows = items_from_csv_rows(rows)
        if not items:
            raise ValueError("No valid inventory rows found in the imported file")

        self.items = items
        self._populate_table(items)

        item_unit = "item" if len(items) == 1 else "items"
        if skipped_rows:
            row_unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f"{len(items)} {item_unit} imported ({len(skipped_rows)} {row_unit} skipped)"
            )
        else:
            self.result_label.setText(f"{len(items)} {item_unit} imported")
        return items

    def _populate_table(self, items: list[InventoryItem]) -> None:
        self.items_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.items_table.setItem(row_index, 0, check_item)

            values = [item.sku, item.name, item.position_code, item.batch, item.expiry]
            for column, value in enumerate(values, start=1):
                self.items_table.setItem(row_index, column, QTableWidgetItem(value))

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None:
                check_item.setCheckState(state)

    def checked_items(self) -> list[InventoryItem]:
        checked = []
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None and check_item.checkState() == Qt.CheckState.Checked:
                checked.append(self.items[row])
        return checked

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(INVENTORY_CSV_FIELDS, parent=self)
        if not dialog.exec():
            return
        try:
            self.load_items(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "feat: inventory panel CSV import with selectable print table"
```

---

## Task 6: Inventory panel — print + audit log

**Files:**
- Modify: `app/ui/mode_inventory_panel.py`
- Modify: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes:
  - `app.core.label_renderer.render_inventory_label` (Task 4)
  - `app.core.print_service.print_labels` (existing, unmodified)
  - `app.core.audit_log.append_print_log` (existing, unmodified)
  - `app.core.config.default_settings_path` (existing, unmodified)
  - `self.checked_items()` (Task 5)
- Produces: `print_checked_items(self, output_pdf_path: Path | None = None) -> None`,
  wires `print_button.clicked` to a new `_on_print_clicked` handler.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mode_inventory_panel.py`:
```python
def test_print_checked_items_writes_pdf_and_log(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {
                "sku": "SKU1",
                "name": "Widget",
                "batch": "4471",
                "expiry": "2027-03",
                "position_code": "H011A",
            },
            {"sku": "SKU2", "name": "Gadget", "position_code": "H012A"},
        ]
    )

    pdf_path = tmp_path / "out.pdf"
    panel.print_checked_items(output_pdf_path=pdf_path)

    assert pdf_path.exists()
    log_path = tmp_path / "audit_log.csv"
    log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 2  # header + one entry
    assert log_lines[1].split(",")[2:] == ["inventory", "C001", "2", "SKU1..SKU2"]


def test_print_checked_items_skips_unchecked_rows(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )
    panel.items_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    log_path = tmp_path / "audit_log.csv"
    log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert log_lines[1].split(",")[2:] == ["inventory", "C001", "1", "SKU1"]


def test_print_checked_items_raises_when_nothing_checked(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])
    panel.select_none_button.click()

    with pytest.raises(ValueError):
        panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")


def test_print_checked_items_raises_without_label_size():
    _app()
    settings = {"warehouses": SETTINGS["warehouses"], "label_sizes": []}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    with pytest.raises(ValueError):
        panel.print_checked_items()


def test_print_button_click_invokes_print_checked_items(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    calls = []
    monkeypatch.setattr(panel, "print_checked_items", lambda: calls.append(True))

    panel.print_button.click()

    assert calls == [True]


def test_print_button_click_without_items_shows_warning(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert len(warnings) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: FAIL — `print_checked_items` doesn't exist yet (the
`test_print_button_click_*` tests fail at `monkeypatch.setattr` /
because clicking Print currently does nothing).

- [ ] **Step 3: Implement**

Add these imports to the top of `app/ui/mode_inventory_panel.py` (alongside
the existing ones):
```python
from pathlib import Path

from app.core.audit_log import append_print_log
from app.core.config import default_settings_path
from app.core.label_renderer import render_inventory_label
from app.core.print_service import print_labels
```

In `__init__`, change:
```python
        self.print_button = QPushButton("Print")
```
to:
```python
        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)
```

Add these methods to the end of the class:
```python
    def _on_print_clicked(self) -> None:
        try:
            self.print_checked_items()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Print failed", str(error))

    def print_checked_items(self, output_pdf_path: Path | None = None) -> None:
        checked = self.checked_items()
        if not checked:
            raise ValueError("Nothing to print - import a CSV and check at least one row")

        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")

        warehouse_prefix = self.warehouse_combo.currentData() or ""

        images = []
        for item in checked:
            text_lines = [item.name] if item.name else []
            if item.batch:
                text_lines.append(f"Batch {item.batch}")
            if item.expiry:
                text_lines.append(f"Exp {item.expiry}")
            image = render_inventory_label(
                item.sku,
                "\n".join(text_lines),
                f"{warehouse_prefix}{item.position_code}",
                width_mm=label_size["width_mm"],
                height_mm=label_size["height_mm"],
            )
            images.append(image)

        print_labels(
            images,
            width_mm=label_size["width_mm"],
            height_mm=label_size["height_mm"],
            printer_name=self._settings.get("default_printer") or None,
            output_pdf_path=output_pdf_path,
        )

        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        log_path = Path(shared_folder) / "audit_log.csv"
        skus = [item.sku for item in checked]
        description = f"{skus[0]}..{skus[-1]}" if len(skus) > 1 else skus[0]
        append_print_log(
            log_path,
            mode="inventory",
            warehouse_prefix=warehouse_prefix,
            count=len(checked),
            description=description,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: PASS — including every test from Task 5.

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "feat: print checked inventory rows and log the batch"
```

---

## Task 7: Wire the Inventory panel into the main window (tabs)

**Files:**
- Modify: `app/ui/main_window.py`
- Modify: `tests/test_main_window.py`

**Interfaces:**
- Consumes: `app.ui.mode_inventory_panel.InventoryModePanel` (Tasks 5-6).
- Produces: `MainWindow.tabs: QTabWidget`, `MainWindow.inventory_panel: InventoryModePanel`.
  `MainWindow.positions_panel` is unchanged, but it's no longer the central
  widget directly — it's `tabs.widget(0)`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_main_window.py` in full (the central-widget assertion
changes because the central widget becomes the tab container, and two new
tests cover the Inventory tab):
```python
from PySide6.QtWidgets import QApplication

import app.ui.main_window as main_window_module
from app.core.config import save_settings
from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"


def test_main_window_hosts_positions_and_inventory_tabs():
    _app()
    window = MainWindow()
    assert window.centralWidget() is window.tabs
    assert window.tabs.widget(0) is window.positions_panel
    assert window.tabs.widget(1) is window.inventory_panel
    assert window.tabs.tabText(0) == "Positions"
    assert window.tabs.tabText(1) == "Inventory"


def test_open_settings_refreshes_positions_panel_combos(monkeypatch, tmp_path):
    _app()
    window = MainWindow()
    window._settings_path = tmp_path / "settings.json"
    save_settings(
        window._settings_path,
        {"warehouses": [{"name": "New", "prefix": "C999"}], "label_sizes": []},
    )

    class FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window_module, "SettingsWindow", FakeSettingsDialog)

    window._open_settings()

    warehouse_names = [
        window.positions_panel.warehouse_combo.itemText(i)
        for i in range(window.positions_panel.warehouse_combo.count())
    ]
    assert warehouse_names == ["New"]


def test_open_settings_refreshes_inventory_panel_combos(monkeypatch, tmp_path):
    _app()
    window = MainWindow()
    window._settings_path = tmp_path / "settings.json"
    save_settings(
        window._settings_path,
        {"warehouses": [{"name": "New", "prefix": "C999"}], "label_sizes": []},
    )

    class FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window_module, "SettingsWindow", FakeSettingsDialog)

    window._open_settings()

    warehouse_names = [
        window.inventory_panel.warehouse_combo.itemText(i)
        for i in range(window.inventory_panel.warehouse_combo.count())
    ]
    assert warehouse_names == ["New"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main_window.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute 'tabs'`

- [ ] **Step 3: Implement**

Replace `app/ui/main_window.py`:
```python
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.core.config import default_settings_path, load_settings
from app.ui.mode_inventory_panel import InventoryModePanel
from app.ui.mode_positions_panel import PositionsModePanel
from app.ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Barcode Label Generator")
        self.resize(900, 600)

        self._settings_path = default_settings_path()
        self._settings = load_settings(self._settings_path)

        self.positions_panel = PositionsModePanel(self._settings)
        self.inventory_panel = InventoryModePanel(self._settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.positions_panel, "Positions")
        self.tabs.addTab(self.inventory_panel, "Inventory")
        self.setCentralWidget(self.tabs)

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        self.menuBar().addAction(settings_action)

    def _open_settings(self) -> None:
        dialog = SettingsWindow(self._settings, self._settings_path, parent=self)
        if dialog.exec():
            self._settings = load_settings(self._settings_path)
            self.positions_panel.refresh_from_settings(self._settings)
            self.inventory_panel.refresh_from_settings(self._settings)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main_window.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/main_window.py tests/test_main_window.py
git commit -m "feat: host Positions and Inventory panels in a tab widget"
```

---

## Task 8: Full regression check

No file changes — catches integration issues across Tasks 1-7 before
calling Phase 3 done.

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest -v`
Expected: every test across the whole repo passes, including all prior
phases' tests and this phase's new tests (Tasks 1-7 above).

- [ ] **Step 2: Run the linter**

Run: `ruff check .`
Expected: no errors (CI's `lint` job runs this same command).

- [ ] **Step 3: Manual smoke test (do this once, in the session that executes this plan)**

Run: `python -m app.main`.
1. Confirm the main window now shows two tabs, "Positions" and "Inventory",
   and the Positions tab still behaves exactly as before (Phase 1/2
   regression check).
2. Switch to the Inventory tab. Pick a warehouse and label size.
3. Click "Import CSV...", pick a small CSV with columns
   `SKU,Name,Position,Batch,Expiry` and a few rows — include one SKU
   repeated with two different `Position` values (e.g. `H011A` and
   `H014B`), one row with a blank SKU, and one row with a malformed
   Position value (e.g. `??`).
4. Map the columns; confirm on import the table shows only the valid rows
   (both positions for the repeated SKU as separate rows), all checked, and
   the result label reports the skipped-row count.
5. Uncheck one row, click "Select none" then "Select all" to confirm the
   bulk toggles work, then leave one or two rows checked.
6. Click "Print"; confirm it produces a PDF/print job containing only the
   checked rows' labels (SKU QR + text on top, divider, position QR +
   caption below), and that `audit_log.csv` gained one `inventory` row with
   the correct count.

This step is GUI-only and isn't covered by the automated tests above.

---

## Plan self-review notes

- **Spec coverage:** Design doc §3 (CSV shape, one row per SKU-position
  pair) and §6 (skip-and-continue rules) are covered by
  `items_from_csv_rows` (Task 3). §4 (label layout) is covered by
  `render_inventory_label` (Task 4). §5 (barcode content: SKU QR with no
  prefix, position QR with the hidden-prefix rule) is covered by Task 6's
  `print_checked_items`, which builds `f"{warehouse_prefix}{item.position_code}"`
  only for the position QR, never the SKU QR. §7 (inline selectable table,
  select all/none) is covered by Task 5. §8 (audit log, `mode="inventory"`,
  first..last description) is covered by Task 6. §9's module breakdown maps
  1:1 onto Tasks 1-7. §11 (out of scope: grouping same-SKU rows, editing
  text, QR configuration) is intentionally not implemented anywhere in this
  plan.
- **Backward compatibility:** Task 2 adds `parse_position_code` without
  touching `format_position_code` or `generate_position_codes` — Mode 2.1's
  existing tests in `tests/test_position_generator.py` and
  `tests/test_mode_positions_panel.py` are required to keep passing
  unmodified (verified in Task 2 Step 4 and again in Task 8 Step 1). Task 7
  intentionally changes `MainWindow`'s central-widget shape (a tab
  container instead of the bare Positions panel) — this is a real,
  deliberate behavior change from adding the second mode, not an oversight,
  and the affected test is updated in the same task rather than left
  broken.
- **Type/interface consistency:** `items_from_csv_rows` (Task 3) returns
  `(list[InventoryItem], list[int])`; `load_items` (Task 5) destructures it
  the same way. `render_inventory_label`'s parameter order
  `(sku_data, text, position_data, width_mm, height_mm, dpi)` (Task 4) is
  called positionally in that exact order from `print_checked_items`
  (Task 6). `checked_items() -> list[InventoryItem]` (Task 5) is consumed
  directly by `print_checked_items` (Task 6) with no adapter needed.
  `INVENTORY_CSV_FIELDS` (Task 3) is passed straight into `CsvImportDialog`
  (Task 5), matching its existing `fields: list[tuple[str, str]]` signature
  unchanged from the CSV-infrastructure phase.
- **Out of scope for this phase, by design:** Modes 2.3/2.4 (future
  roadmap phases); named CSV-mapping presets; grouping/collapsing same-SKU
  rows in the table; in-app editing of imported text fields; QR
  error-correction/box-size configuration — all per design doc §11.
