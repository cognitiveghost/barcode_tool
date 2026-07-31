# Inventory Label v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Inventory label so it prints correctly and legibly on a
real 100x150mm thermal label — fixed 150x100 landscape format only, a
three-column layout with readable text sections, a Cyrillic-safe CSV
reader, a Qt print-orientation bugfix, and an always-on debug PDF next to
the audit log.

**Architecture:** Same layering as the rest of the app — pure logic changes
in `app/core/` (`csv_import.py` encoding fallback, `print_service.py`
orientation fix, `label_renderer.py`'s `render_inventory_label` rewritten
drawing logic), and the Qt panel in `app/ui/mode_inventory_panel.py` drops
its size/orientation combos in favor of two fixed constants and always
writes a debug PDF.

**Tech Stack:** Python 3.11+, Pillow, `qrcode`, PySide6, pytest. No new
dependencies — `utf-8-sig`/`cp1251` are stdlib codecs.

## Global Constraints

- The application and all code/comments must be in English.
- No new dependencies in `requirements.txt`.
- Inventory labels are always 150mm (width) x 100mm (height) — no
  configurable size or orientation for this panel.
- Mode 2.1 (Positions panel)'s own Label size / Orientation combos and
  behavior are unaffected by this plan.
- `render_inventory_label`'s parameter signature is unchanged from the
  current (v2) version — this plan rewrites its internal drawing logic
  only.
- Position QR still encodes `{warehouse_prefix}{position_code}`; its
  caption shows the unprefixed `position_code` — unchanged hidden-prefix
  rule.
- Generation date format is `DDMMYYYY`, computed by the caller at print
  time — unchanged from v2.

Full design rationale:
`docs/superpowers/specs/2026-07-31-inventory-label-v3-design.md`.

---

## Task 1: Cyrillic-safe CSV reading (`csv_import.py`)

**Files:**
- Modify: `app/core/csv_import.py` (`read_csv`, lines 7-12)
- Test: `tests/test_csv_import.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `read_csv(path: Path) -> tuple[list[str], list[list[str]]]` —
  same signature and return shape as today; only the decoding behavior
  changes. Used by `csv_import_dialog.py` (unchanged call site).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_csv_import.py`:

```python
def test_read_csv_decodes_cp1251_cyrillic_content(tmp_path):
    path = tmp_path / "cyrillic.csv"
    path.write_bytes("sku,client\r\nSKU1,Клиент\r\n".encode("cp1251"))

    header, rows = read_csv(path)

    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Клиент"]]


def test_read_csv_strips_utf8_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("﻿sku,client\r\nSKU1,Acme\r\n".encode("utf-8"))

    header, rows = read_csv(path)

    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Acme"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_csv_import.py -v -k "cp1251 or bom"`
Expected: `test_read_csv_decodes_cp1251_cyrillic_content` FAILs (today's
strict `utf-8` open raises `UnicodeDecodeError` on the cp1251 bytes).
`test_read_csv_strips_utf8_bom` FAILs because the header comes back as
`['﻿sku', 'client']` (the BOM glued to the first header name).

- [ ] **Step 3: Implement**

Replace `read_csv` in `app/core/csv_import.py`:

```python
from __future__ import annotations

import csv
import io
from pathlib import Path


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1251")
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        return [], []
    return all_rows[0], all_rows[1:]
```

(`utf-8-sig` transparently handles both plain UTF-8 and UTF-8-with-BOM
files — the common modern Excel export. `cp1251` is the fallback for
legacy Cyrillic-locale exports that aren't valid UTF-8 at all.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_csv_import.py -v`
Expected: PASS for all tests, including every pre-existing test in this
file (plain UTF-8 files decode identically under `utf-8-sig`).

- [ ] **Step 5: Commit**

```bash
git add app/core/csv_import.py tests/test_csv_import.py
git commit -m "fix: read_csv falls back to cp1251 for non-UTF-8 Cyrillic exports"
```

---

## Task 2: Fix the landscape-paper-clipping bug (`print_service.py`)

**Files:**
- Modify: `app/core/print_service.py`
- Test: `tests/test_print_service.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_page_orientation(width_mm: float, height_mm: float) ->
  QPageLayout.Orientation` — new private helper. `print_labels(...)` keeps
  its existing signature; behavior changes only in that it now explicitly
  sets page orientation.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_print_service.py`:

```python
from PIL import Image
from PySide6.QtGui import QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from app.core.print_service import _page_orientation, print_labels


def _app():
    return QApplication.instance() or QApplication([])


def test_print_labels_writes_pdf_with_expected_page_count(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white") for _ in range(3)]
    output_path = tmp_path / "labels.pdf"

    print_labels(images, width_mm=68, height_mm=38, output_pdf_path=output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_page_orientation_landscape_for_wide_size():
    assert _page_orientation(150, 100) == QPageLayout.Orientation.Landscape


def test_page_orientation_portrait_for_tall_size():
    assert _page_orientation(100, 150) == QPageLayout.Orientation.Portrait


def test_page_orientation_portrait_for_square_size():
    assert _page_orientation(80, 80) == QPageLayout.Orientation.Portrait


def test_print_labels_applies_the_computed_page_orientation(monkeypatch, tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    output_path = tmp_path / "labels.pdf"
    seen = []
    original = QPrinter.setPageOrientation

    def _spy(self, orientation):
        seen.append(orientation)
        return original(self, orientation)

    monkeypatch.setattr(QPrinter, "setPageOrientation", _spy)

    print_labels(images, width_mm=150, height_mm=100, output_pdf_path=output_path)

    assert seen == [QPageLayout.Orientation.Landscape]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_print_service.py -v`
Expected: `test_page_orientation_landscape_for_wide_size` and its two
siblings FAIL with `ImportError: cannot import name '_page_orientation'`.
`test_print_labels_applies_the_computed_page_orientation` FAILs with
`seen == []` (nothing calls `setPageOrientation` today).

- [ ] **Step 3: Implement**

In `app/core/print_service.py`, add the helper and call it in
`print_labels` right after `setPageSize`:

```python
def _page_orientation(width_mm: float, height_mm: float) -> QPageLayout.Orientation:
    if width_mm > height_mm:
        return QPageLayout.Orientation.Landscape
    return QPageLayout.Orientation.Portrait


def print_labels(
    images: list[Image.Image],
    width_mm: float,
    height_mm: float,
    printer_name: str | None = None,
    output_pdf_path: Path | None = None,
) -> None:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter))
    printer.setPageOrientation(_page_orientation(width_mm, height_mm))
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    ...  # rest of the function (output format / painter loop) unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_print_service.py -v`
Expected: PASS for all five tests.

- [ ] **Step 5: Commit**

```bash
git add app/core/print_service.py tests/test_print_service.py
git commit -m "fix: explicitly set QPrinter page orientation to stop landscape clipping"
```

---

## Task 3: Three-column Inventory label layout (`label_renderer.py`)

**Files:**
- Modify: `app/core/label_renderer.py` (`render_inventory_label` and
  `_MIN_MIDDLE_WIDTH_MM`, lines 66-157)
- Test: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: `load_font` (existing), `mm_to_px`/`font_size_for_height`
  (existing), `generate_qr_image` (existing).
- Produces: `render_inventory_label(sku, name, client, batch, expiry,
  position_code, position_data, generated_date, width_mm, height_mm,
  dpi=203) -> Image.Image` — same signature as today. Used by
  `mode_inventory_panel.py` in Task 4.

- [ ] **Step 1: Replace the obsolete four-corner tests**

In `tests/test_label_renderer.py`, delete these two tests (they test
behavior that no longer exists once the canvas size is fixed):
`test_render_inventory_label_drops_secondary_chips_on_a_narrow_canvas`,
`test_render_inventory_label_composes_at_all_built_in_sizes`.

Replace the remaining `render_inventory_label` tests with:

```python
def test_render_inventory_label_returns_image_of_expected_size():
    img = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100, dpi=203,
    )
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(150, 203), mm_to_px(100, 203))


def test_render_inventory_label_omits_expiry_chip_when_expiry_empty():
    img_with = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    img_without = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    assert img_with.tobytes() != img_without.tobytes()


def test_render_inventory_label_omits_batch_chip_when_batch_empty():
    img_with = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    img_without = render_inventory_label(
        "SKU1", "Widget", "Acme", "", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    assert img_with.tobytes() != img_without.tobytes()


def test_render_inventory_label_renders_with_everything_optional_blank():
    img = render_inventory_label(
        "SKU1", "", "", "", "", "H011A", "C001H011A", "31072026",
        width_mm=150, height_mm=100,
    )
    assert isinstance(img, Image.Image)


def test_render_inventory_label_position_qr_uses_prefixed_data():
    img_a = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    img_b = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C002H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    assert img_a.tobytes() != img_b.tobytes()
```

- [ ] **Step 2: Run the tests to verify they fail/still pass appropriately**

Run: `pytest tests/test_label_renderer.py -v -k render_inventory_label`
Expected: all pass against the *old* implementation too (these tests don't
assert on layout positions, just presence/absence/difference), except the
two deleted ones are simply gone. This is expected — the tests are a
safety net for the rewrite in Step 3, not a red/green gate on their own.

- [ ] **Step 3: Implement the three-column layout**

Replace from `_MIN_MIDDLE_WIDTH_MM` to the end of
`app/core/label_renderer.py`:

```python
_MARGIN_MM = 5


def render_inventory_label(
    sku: str,
    name: str,
    client: str,
    batch: str,
    expiry: str,
    position_code: str,
    position_data: str,
    generated_date: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)
    canvas = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(canvas)

    margin = mm_to_px(_MARGIN_MM, dpi)
    content_x0, content_y0 = margin, margin
    content_width = width_px - 2 * margin
    content_height = height_px - 2 * margin

    primary_size = round(content_height * 0.42)   # SKU / Position QR side
    secondary_size = round(content_height * 0.30)  # Expiry / Batch QR side
    gap = max(2, round(content_height * 0.02))

    bold_font = load_font(font_size_for_height(primary_size), bold=True)
    caption_font = load_font(font_size_for_height(secondary_size))

    left_x = content_x0
    right_x = content_x0 + content_width - secondary_size
    divider_left = content_x0 + primary_size
    divider_right = right_x

    # SKU: top of the left column, bold caption below it.
    sku_qr = generate_qr_image(sku).resize((primary_size, primary_size))
    canvas.paste(sku_qr, (left_x, content_y0))
    draw.text((left_x, content_y0 + primary_size + gap), sku, fill="black", font=bold_font)

    # Position: bottom of the left column, bold caption above it.
    position_qr_y = content_y0 + content_height - primary_size
    position_bbox = draw.textbbox((0, 0), position_code, font=bold_font)
    position_caption_height = position_bbox[3] - position_bbox[1]
    draw.text(
        (left_x, position_qr_y - position_caption_height - gap),
        position_code,
        fill="black",
        font=bold_font,
    )
    position_qr = generate_qr_image(position_data).resize((primary_size, primary_size))
    canvas.paste(position_qr, (left_x, position_qr_y))

    # Expiry: top of the right column, caption below it. Omitted if blank.
    if expiry:
        expiry_qr = generate_qr_image(expiry).resize((secondary_size, secondary_size))
        canvas.paste(expiry_qr, (right_x, content_y0))
        draw.text(
            (right_x, content_y0 + secondary_size + gap), expiry, fill="black", font=caption_font
        )

    # Batch: bottom of the right column, caption above it. Omitted if blank.
    if batch:
        batch_qr_y = content_y0 + content_height - secondary_size
        batch_bbox = draw.textbbox((0, 0), batch, font=caption_font)
        batch_caption_height = batch_bbox[3] - batch_bbox[1]
        draw.text(
            (right_x, batch_qr_y - batch_caption_height - gap),
            batch,
            fill="black",
            font=caption_font,
        )
        batch_qr = generate_qr_image(batch).resize((secondary_size, secondary_size))
        canvas.paste(batch_qr, (right_x, batch_qr_y))

    # Divider lines: two verticals for the full content height, one
    # horizontal splitting the middle column only (not the QR columns).
    divider_width = 3
    mid_split_y = content_y0 + content_height // 2
    draw.line(
        [(divider_left, content_y0), (divider_left, content_y0 + content_height)],
        fill="black", width=divider_width,
    )
    draw.line(
        [(divider_right, content_y0), (divider_right, content_y0 + content_height)],
        fill="black", width=divider_width,
    )
    draw.line(
        [(divider_left, mid_split_y), (divider_right, mid_split_y)],
        fill="black", width=divider_width,
    )

    # Middle column, top half: plain readable field list.
    middle_x = divider_left + gap * 2
    middle_right = divider_right - gap * 2
    text_lines: list[tuple[str, object]] = []
    if name:
        text_lines.append((name, bold_font))
    for label, value in (
        ("Expiry", expiry),
        ("Batch", batch),
        ("SKU", sku),
        ("Position", position_code),
    ):
        if value:
            text_lines.append((f"{label}: {value}", caption_font))

    line_y = content_y0 + gap
    for line, font in text_lines:
        draw.text((middle_x, line_y), line, fill="black", font=font)
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_y += (line_bbox[3] - line_bbox[1]) + gap

    # Middle column, bottom half: Client name, centered.
    if client:
        client_bbox = draw.textbbox((0, 0), client, font=caption_font)
        client_width = client_bbox[2] - client_bbox[0]
        client_x = middle_x + max(0, (middle_right - middle_x - client_width) // 2)
        draw.text((client_x, mid_split_y + gap * 2), client, fill="black", font=caption_font)

    # Generation date: small text, bottom-right corner of the middle
    # column's bottom half (not the label's absolute corner, so it never
    # collides with the Batch QR in the right column).
    date_font = load_font(max(8, font_size_for_height(secondary_size) - 2))
    date_bbox = draw.textbbox((0, 0), generated_date, font=date_font)
    draw.text(
        (middle_right - date_bbox[2] - 2, content_y0 + content_height - date_bbox[3] - 2),
        generated_date,
        fill="black",
        font=date_font,
    )

    return canvas
```

- [ ] **Step 4: Run the automated tests to verify they pass**

Run: `pytest tests/test_label_renderer.py -v`
Expected: PASS for the entire file.

- [ ] **Step 5: Manually render and visually inspect a sample label**

Run this from the repo root (writes to the session scratchpad, not the
repo):

```bash
python -c "
from app.core.label_renderer import render_inventory_label
img = render_inventory_label(
    '01-FACE-1100', 'PurityX+ Cleaning Cream', 'Адмадерм ЕООД',
    '2934ODHE', '11032028', 'H224A', 'C001H224A', '31072026',
    width_mm=150, height_mm=100,
)
img.save('/tmp/claude-1000/-home-cognitiveghost-Desktop-barcode-tool/b0168748-0d55-432c-9ffb-9cc36d7c4326/scratchpad/inventory_label_preview.png')
"
```

Then view `.../scratchpad/inventory_label_preview.png` with the Read tool.
Check: SKU/Position QRs and captions in the left column, Expiry/Batch QRs
and captions in the right column, the five-line field list and centered
Cyrillic client name in the middle, no overlapping text, no text spilling
across a divider line. If something looks wrong (cramped, overlapping,
disproportionate), adjust the fractions (`0.42`, `0.30`, `0.02`) in Step 3
and re-render — this is expected tuning, not a sign the approach is wrong.

- [ ] **Step 6: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "feat: three-column Inventory label layout (SKU/Position + Expiry/Batch + text)"
```

---

## Task 4: Fixed 150x100 format + always-on debug PDF (`mode_inventory_panel.py`)

**Files:**
- Modify: `app/ui/mode_inventory_panel.py`
- Test: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: `render_inventory_label` (Task 3), `print_labels` (Task 2,
  unchanged signature).
- Produces: `INVENTORY_LABEL_WIDTH_MM = 150`, `INVENTORY_LABEL_HEIGHT_MM =
  100` module constants. `label_size_combo` and `orientation_combo` no
  longer exist on `InventoryModePanel`.

- [ ] **Step 1: Update the test fixtures and remove obsolete tests**

In `tests/test_mode_inventory_panel.py`, change the module-level `SETTINGS`
fixture:

```python
SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
}
```

Delete these tests entirely (they test combos/behavior that no longer
exists): `test_orientation_defaults_to_landscape`,
`test_print_checked_items_uses_portrait_dimensions`,
`test_print_checked_items_raises_without_label_size`.

Update `test_refresh_from_settings_rebuilds_combos` (drop the label-size
assertion, since there's no `label_size_combo` anymore):

```python
def test_refresh_from_settings_rebuilds_combos():
    _app()
    panel = InventoryModePanel(SETTINGS)

    panel.refresh_from_settings({"warehouses": [{"name": "Second", "prefix": "C002"}]})

    warehouse_names = [panel.warehouse_combo.itemText(i) for i in range(panel.warehouse_combo.count())]
    assert warehouse_names == ["Second"]
```

Update the two tests that build a `settings` dict referencing
`SETTINGS["label_sizes"]` (which no longer exists):
`test_print_checked_items_raises_without_warehouse` and
`test_print_button_click_without_warehouse_shows_warning` — both change
their `settings = {...}` line to just `settings = {"warehouses": []}`.

Update `test_audit_log_failure_reports_distinct_warning_after_successful_print`
— `print_labels` is now called twice per `print_checked_items` (real print
+ debug PDF), so its recording lambda accumulates two entries:

```python
    assert print_calls == [True, True]
```

Add two new tests:

```python
def test_print_checked_items_writes_a_timestamped_debug_pdf_next_to_the_audit_log(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items(output_pdf_path=tmp_path / "explicit.pdf")

    debug_pdfs = list(tmp_path.glob("inventory_label_preview_*.pdf"))
    assert len(debug_pdfs) == 1
    assert debug_pdfs[0].stat().st_size > 0


def test_print_checked_items_still_writes_debug_pdf_without_an_explicit_output_path(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items()

    debug_pdfs = list(tmp_path.glob("inventory_label_preview_*.pdf"))
    assert len(debug_pdfs) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: FAIL — `AttributeError` from tests no longer referencing
`label_size_combo`/`orientation_combo` correctly against the *old* code
(which still has them and still requires a label size), plus the two new
debug-pdf tests FAIL because no such file is written yet, plus the
`[True, True]` assertion FAILs (`print_labels` is only called once today).

- [ ] **Step 3: Implement**

In `app/ui/mode_inventory_panel.py`, change the import line:

```python
from app.core.label_renderer import render_inventory_label
```

(drop `apply_orientation` — no longer used in this file)

Add the fixed-size constants near `TABLE_COLUMNS`:

```python
TABLE_COLUMNS = ["", "SKU", "Name", "Client", "Position", "Batch", "Expiry"]

INVENTORY_LABEL_WIDTH_MM = 150
INVENTORY_LABEL_HEIGHT_MM = 100

_DESCRIPTION_SKU_LIMIT = 5
```

In `__init__`, remove the `label_size_combo` and `orientation_combo`
widgets entirely:

```python
        self.warehouse_combo = QComboBox()
        self.refresh_from_settings(settings)
```

(delete the `self.label_size_combo = QComboBox()` line, the
`self.orientation_combo = QComboBox()` + `.addItems(...)` lines)

Remove the corresponding form rows:

```python
        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
```

(delete the `form.addRow("Label size", ...)` and
`form.addRow("Orientation", ...)` lines)

Replace `refresh_from_settings`:

```python
    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])
```

Replace `print_checked_items`:

```python
    def print_checked_items(self, output_pdf_path: Path | None = None) -> None:
        checked = self.checked_items()
        if not checked:
            raise ValueError("Nothing to print - import a CSV and check at least one row")

        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            raise ValueError("No warehouse selected - add one in Settings first")

        generated_date = datetime.now(timezone.utc).astimezone().strftime("%d%m%Y")

        images = []
        for item in checked:
            image = render_inventory_label(
                item.sku,
                item.name,
                item.client,
                item.batch,
                item.expiry,
                item.position_code,
                f"{warehouse_prefix}{item.position_code}",
                generated_date,
                width_mm=INVENTORY_LABEL_WIDTH_MM,
                height_mm=INVENTORY_LABEL_HEIGHT_MM,
            )
            images.append(image)

        print_labels(
            images,
            width_mm=INVENTORY_LABEL_WIDTH_MM,
            height_mm=INVENTORY_LABEL_HEIGHT_MM,
            printer_name=self._settings.get("default_printer") or None,
            output_pdf_path=output_pdf_path,
        )

        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        debug_pdf_path = (
            Path(shared_folder) / f"inventory_label_preview_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        )
        print_labels(
            images,
            width_mm=INVENTORY_LABEL_WIDTH_MM,
            height_mm=INVENTORY_LABEL_HEIGHT_MM,
            output_pdf_path=debug_pdf_path,
        )

        log_path = Path(shared_folder) / "audit_log.csv"
        description = _describe_skus([item.sku for item in checked])
        try:
            append_print_log(
                log_path,
                mode="inventory",
                warehouse_prefix=warehouse_prefix,
                count=len(checked),
                description=description,
            )
        except OSError as error:
            raise AuditLogError(str(error)) from error
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: PASS for all tests.

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "feat: fix Inventory panel to 150x100 landscape, always save a debug PDF"
```

---

## Task 5: Full regression check and end-to-end visual verification

No new source files — catches integration issues across Tasks 1-4 and
gives a final human-eyeball check before calling this done, mirroring the
"generate a PDF instead of wasting paper" request that started this fix.

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest -v`
Expected: every test across the whole repo passes, including
`tests/test_mode_positions_panel.py` and `tests/test_main_window.py`
(unaffected by this plan, but must not have regressed).

- [ ] **Step 2: Run the linter**

Run: `ruff check .`
Expected: no errors.

- [ ] **Step 3: End-to-end manual check via the app's own debug PDF**

Run: `python -m app.main`.
1. Go to Settings, add a warehouse if none exists (e.g. prefix `C001`) and
   set `shared_folder` to a scratch directory you can inspect.
2. Switch to the Inventory tab. Confirm there is no Label size or
   Orientation control anymore — just Warehouse, Import CSV, the table,
   and Print.
3. Prepare a small CSV with columns `sku,name,client,batch,expiry,position_code`
   including one row with a Cyrillic client name (e.g. `Адмадерм ЕООД`),
   saved with Excel's "CSV UTF-8" export option (or plain UTF-8 — either
   should work now).
4. Import it, confirm the table's Client column shows the Cyrillic name
   correctly (not blank, not garbled).
5. Click Print. Confirm no crash, and that a new
   `inventory_label_preview_<timestamp>.pdf` appears in the shared folder
   next to `audit_log.csv`.
6. Open that PDF and confirm: the page is landscape-oriented (not clipped
   to portrait), the three-column layout matches Task 3's rendered
   preview, and the Cyrillic client name is legible.

This step is GUI-only and isn't covered by the automated tests above.

---

## Plan self-review notes

- **Spec coverage:** design doc §2 (fixed format, combos removed) is
  covered by Task 4. §3 (print orientation bugfix) is covered by Task 2.
  §4 (Cyrillic CSV bugfix) is covered by Task 1. §5 (three-column layout)
  is covered by Task 3. §6 (always-on debug PDF) is covered by Task 4's
  `print_checked_items` rewrite and its two new tests. §7's module
  breakdown maps 1:1 onto Tasks 1-4. §9 (out of scope: other label sizes,
  file cleanup, general charset detection, Mode 2.1 changes) is
  intentionally not implemented anywhere in this plan.
- **Backward compatibility:** Task 2's orientation fix is additive to the
  shared `print_labels` and was checked against Mode 2.1's existing usage
  pattern (same function, no signature change) — Positions panel tests are
  covered by Task 5 Step 1's full-suite run rather than a dedicated new
  test, since no Positions-panel-specific behavior changes.
- **Type/interface consistency:** `render_inventory_label`'s signature
  (Task 3) is called positionally in the same order from
  `print_checked_items` (Task 4) as it already was — no signature drift.
  `print_labels(images, width_mm, height_mm, printer_name=None,
  output_pdf_path=None)` (Task 2, unchanged signature) is called twice in
  Task 4 with consistent keyword usage. `_page_orientation` (Task 2) is
  private to `print_service.py` and not consumed elsewhere.
- **Known trade-off carried from the design doc:** the mm-based
  proportions in Task 3 (0.42 / 0.30 / 0.02 fractions) are a starting
  point, explicitly expected to be tuned during Task 3 Step 5's visual
  check — this is intentional, not a gap.
