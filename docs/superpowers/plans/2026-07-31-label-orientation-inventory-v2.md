# Label Orientation, Cyrillic Support & Inventory Label v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Landscape/Portrait orientation to both panels, Cyrillic text support, a combined-column CSV format for Expiry/Batch, a redesigned four-corner Inventory label (separate SKU/Expiry/Batch/Position QR codes, Client name, generation date), and a bigger CSV import dialog.

**Architecture:** Same layering as the rest of the app — pure logic in `app/core/` (`label_renderer.py` gains `apply_orientation` and a rewritten `render_inventory_label`; a new `app/core/fonts.py` centralizes bundled-font loading; `inventory_import.py` gains a `client` field and combined-column splitting), Qt panels in `app/ui/` wire the new Orientation combo and pass the new fields through, and two new binary font assets ship under `app/assets/fonts/`.

**Tech Stack:** Python 3.11+, Pillow (`ImageFont.truetype`), `qrcode`, PySide6, pytest. No new pip dependencies — DejaVu fonts are bundled binary assets, not a package.

## Global Constraints

- The application and all code/comments must be in English.
- Must run locally on Windows 10/11 and Ubuntu 25+, packaged standalone via
  PyInstaller — no dependency on OS-installed fonts, so Cyrillic support
  requires bundling font files inside the repo/package.
- No new dependencies in `requirements.txt`.
- Orientation defaults to Landscape each session; not persisted to
  `settings.json`.
- Combined Expiry/Batch CSV column order is `expiry/batch` (Expiry first).
- Generation date format is `DDMMYYYY`, computed by the caller at print
  time (never read from the CSV, never computed inside the renderer).
- Inventory label sizing formula: SKU QR side = 50% of
  `min(width_px, height_px)`; Expiry/Batch/Position QR side = 25% of it.
  Same formula at every label size and orientation, no shape-specific
  branching.
- Position QR still encodes `{warehouse_prefix}{position_code}` (hidden
  prefix rule from mode-2.2, unchanged); its caption shows the unprefixed
  `position_code` and sits beside the QR, not underneath — the one
  exception to "caption underneath" for the other three chips.
- Minimum usable middle-text-column width is 10mm; below that, Expiry and
  Batch chips are dropped *together* (not one at a time — they share a
  fixed-width column, so dropping only one never frees width, only
  height). SKU and Position chips are never dropped.

Full design rationale:
`docs/superpowers/specs/2026-07-31-label-orientation-inventory-v2-design.md`,
`docs/superpowers/specs/2026-07-31-mode-2-2-inventory-design.md`, and
`docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md`.

---

## Task 1: Bundle Cyrillic-capable fonts (`app/core/fonts.py`)

**Files:**
- Create: `app/assets/fonts/DejaVuSans.ttf`
- Create: `app/assets/fonts/DejaVuSans-Bold.ttf`
- Create: `app/core/fonts.py`
- Test: `tests/test_fonts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont`
  — used by `label_renderer.py` in Tasks 3 and 6.

- [ ] **Step 1: Copy the font files into the repo**

```bash
mkdir -p app/assets/fonts
cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf app/assets/fonts/
cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf app/assets/fonts/
```

(DejaVu Sans is Bitstream Vera License, permissive; covers Latin + Cyrillic.)

- [ ] **Step 2: Write the failing test**

Create `tests/test_fonts.py`:

```python
from app.core.fonts import load_font


def test_load_font_returns_requested_size():
    font = load_font(20)
    assert font.size == 20


def test_load_font_bold_uses_a_different_file_than_regular():
    regular = load_font(20)
    bold = load_font(20, bold=True)
    assert regular.path != bold.path


def test_load_font_renders_cyrillic_glyphs():
    font = load_font(20)
    mask = font.getmask("Привет")
    assert mask.getbbox() is not None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_fonts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.fonts'`

- [ ] **Step 4: Implement**

Create `app/core/fonts.py`:

```python
from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_fonts.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add app/assets/fonts/DejaVuSans.ttf app/assets/fonts/DejaVuSans-Bold.ttf app/core/fonts.py tests/test_fonts.py
git commit -m "feat: bundle Cyrillic-capable fonts for label rendering"
```

---

## Task 2: `apply_orientation` helper (`label_renderer.py`)

**Files:**
- Modify: `app/core/label_renderer.py`
- Test: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: nothing beyond stdlib.
- Produces: `apply_orientation(width_mm: float, height_mm: float, orientation: str) -> tuple[float, float]`
  — used by both panels in Tasks 4 and 7.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_label_renderer.py`:

```python
from app.core.label_renderer import apply_orientation


def test_apply_orientation_landscape_swaps_a_tall_size():
    assert apply_orientation(68, 100, "Landscape") == (100, 68)


def test_apply_orientation_portrait_swaps_a_wide_size():
    assert apply_orientation(150, 100, "Portrait") == (100, 150)


def test_apply_orientation_landscape_is_noop_when_already_wide():
    assert apply_orientation(150, 100, "Landscape") == (150, 100)


def test_apply_orientation_portrait_is_noop_when_already_tall():
    assert apply_orientation(100, 150, "Portrait") == (100, 150)


def test_apply_orientation_square_is_noop_either_way():
    assert apply_orientation(80, 80, "Landscape") == (80, 80)
    assert apply_orientation(80, 80, "Portrait") == (80, 80)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_renderer.py -v -k apply_orientation`
Expected: FAIL with `ImportError: cannot import name 'apply_orientation'`

- [ ] **Step 3: Implement**

Add to `app/core/label_renderer.py`, above `render_label`:

```python
def apply_orientation(width_mm: float, height_mm: float, orientation: str) -> tuple[float, float]:
    if orientation == "Portrait" and width_mm > height_mm:
        return height_mm, width_mm
    if orientation == "Landscape" and height_mm > width_mm:
        return height_mm, width_mm
    return width_mm, height_mm
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_label_renderer.py -v -k apply_orientation`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "feat: add apply_orientation for Landscape/Portrait label sizing"
```

---

## Task 3: `render_label` — Cyrillic font + centered content

**Files:**
- Modify: `app/core/label_renderer.py`
- Test: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: `load_font(size: int, bold: bool = False)` from Task 1.
- Produces: `render_label(...)` keeps its existing signature; callers are
  unaffected. Internal behavior change only (font + centering).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_label_renderer.py` (add `ImageChops` to the existing
`from PIL import ...` line):

```python
def test_render_label_renders_cyrillic_text_without_error():
    img = render_label("C001H029A", "Полка Н029А", width_mm=68, height_mm=38)
    assert isinstance(img, Image.Image)


def test_render_label_centers_content_vertically_on_a_tall_canvas():
    img = render_label("C001H029A", "H029A", width_mm=38, height_mm=90)
    # On a canvas much taller than the barcode+text block needs, centering
    # should leave roughly equal white margin above and below the content.
    # Checked empirically: pinned-to-top code gives top=8/bottom=497 here
    # (way off); centered code gives top=263/bottom=245 (close).
    bg = Image.new("RGB", img.size, "white")
    bbox = ImageChops.difference(img, bg).getbbox()
    top_margin = bbox[1]
    bottom_margin = img.height - bbox[3]
    assert abs(top_margin - bottom_margin) < img.height * 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_renderer.py -v -k "cyrillic or centers_content"`
Expected: `test_render_label_renders_cyrillic_text_without_error` PASSes even
before the fix (PIL's default font just renders tofu, no exception) —
that's fine, it's a regression guard, not a proof of correctness on its
own. `test_render_label_centers_content_vertically_on_a_tall_canvas` FAILs
(today's code pins content to the top: margins are 8 vs 497, nowhere near
equal).

- [ ] **Step 3: Implement**

Replace the top of `app/core/label_renderer.py`:

```python
from __future__ import annotations

from PIL import Image, ImageDraw

from app.core.barcode_engine import generate_barcode_image, generate_qr_image
from app.core.fonts import load_font

MM_PER_INCH = 25.4
```

(This drops the `ImageFont` import — no longer used directly.)

Replace `render_label`:

```python
def render_label(
    barcode_data: str,
    visible_text: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)

    canvas = Image.new("RGB", (width_px, height_px), "white")

    barcode_img = generate_barcode_image(barcode_data)
    max_barcode_height = round(height_px * 0.7)
    scale = min(width_px / barcode_img.width, max_barcode_height / barcode_img.height, 1)
    barcode_img = barcode_img.resize(
        (round(barcode_img.width * scale), round(barcode_img.height * scale))
    )

    draw = ImageDraw.Draw(canvas)
    font = load_font(font_size_for_height(height_px))
    text_bbox = draw.textbbox((0, 0), visible_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    gap = 2
    block_height = barcode_img.height + gap + text_height
    block_top = max((height_px - block_height) // 2, 0)

    barcode_x = (width_px - barcode_img.width) // 2
    canvas.paste(barcode_img, (barcode_x, block_top))

    text_x = max((width_px - text_width) // 2, 0)
    text_y = block_top + barcode_img.height + gap
    draw.text((text_x, text_y), visible_text, fill="black", font=font)

    return canvas
```

`render_inventory_label` still lives below this in the file (untouched
until Task 6) — leave it in place for now.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_label_renderer.py -v`
Expected: PASS for all `render_label`-related tests (existing +
new). `render_inventory_label` tests still pass unchanged since that
function isn't touched yet.

- [ ] **Step 5: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "feat: Cyrillic font + centered content in render_label"
```

---

## Task 4: Positions panel — Orientation combo

**Files:**
- Modify: `app/ui/mode_positions_panel.py`
- Test: `tests/test_mode_positions_panel.py`

**Interfaces:**
- Consumes: `apply_orientation(width_mm, height_mm, orientation)` from
  Task 2.
- Produces: `PositionsModePanel.orientation_combo` (QComboBox, items
  `["Landscape", "Portrait"]`, default index 0).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mode_positions_panel.py` (add `from app.core.label_renderer import mm_to_px` to the imports):

```python
def test_orientation_defaults_to_landscape():
    _app()
    panel = PositionsModePanel(SETTINGS)
    assert panel.orientation_combo.currentText() == "Landscape"


def test_portrait_orientation_swaps_generated_label_dimensions():
    _app()
    panel = PositionsModePanel(SETTINGS)  # 68x38mm size
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.orientation_combo.setCurrentText("Portrait")

    results = panel.generate()

    _, image = results[0]
    assert image.size == (mm_to_px(38), mm_to_px(68))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mode_positions_panel.py -v -k orientation`
Expected: FAIL with `AttributeError: 'PositionsModePanel' object has no attribute 'orientation_combo'`

- [ ] **Step 3: Implement**

In `app/ui/mode_positions_panel.py`, add to the import line:

```python
from app.core.label_renderer import apply_orientation, render_label
```

In `__init__`, after `self.label_size_combo = QComboBox()` and its
`refresh_from_settings(settings)` call, add:

```python
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Landscape", "Portrait"])
```

In the `form` block, add a row for it (after the Label size row):

```python
        form.addRow("Label size", self.label_size_combo)
        form.addRow("Orientation", self.orientation_combo)
```

Replace `_render_labels`:

```python
    def _render_labels(self, codes: list[str]) -> list[tuple[str, Image.Image]]:
        warehouse_prefix = self.warehouse_combo.currentData() or ""
        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")
        width_mm, height_mm = apply_orientation(
            label_size["width_mm"], label_size["height_mm"], self.orientation_combo.currentText()
        )
        custom_text = self.custom_text_edit.text()

        results = []
        for code in codes:
            visible_text = f"{code} {custom_text}".strip()
            barcode_data = f"{warehouse_prefix}{code}"
            image = render_label(
                barcode_data,
                visible_text,
                width_mm=width_mm,
                height_mm=height_mm,
            )
            results.append((code, image))

        self.generated_codes = codes
        self.generated_labels = [image for _, image in results]
        self._generated_label_size = {"width_mm": width_mm, "height_mm": height_mm}
        return results
```

(`print_current_labels` is unchanged — it already only reads
`label_size["width_mm"]`/`["height_mm"]` from `self._generated_label_size`,
which now holds the already-swapped values.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: PASS for all tests, including the pre-existing
`test_print_uses_label_size_from_generate_time_not_live_combo`.

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py
git commit -m "feat: Landscape/Portrait orientation in the Positions panel"
```

---

## Task 5: Inventory CSV import — Client field + combined Expiry/Batch column

**Files:**
- Modify: `app/core/inventory_import.py`
- Test: `tests/test_inventory_import.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `InventoryItem.client: str` (defaults to `""`);
  `_split_combined_expiry_batch(expiry: str, batch: str) -> tuple[str, str]`
  used internally by `items_from_csv_rows`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_inventory_import.py` (add
`_split_combined_expiry_batch` to the existing import line):

```python
from app.core.inventory_import import (
    InventoryItem,
    _split_combined_expiry_batch,
    items_from_csv_rows,
)


def test_split_combined_expiry_batch_when_expiry_has_slash():
    assert _split_combined_expiry_batch("2027-03/4471", "") == ("2027-03", "4471")


def test_split_combined_expiry_batch_when_batch_has_slash():
    assert _split_combined_expiry_batch("", "2027-03/4471") == ("2027-03", "4471")


def test_split_combined_expiry_batch_noop_when_both_populated():
    assert _split_combined_expiry_batch("2027-03", "4471") == ("2027-03", "4471")


def test_split_combined_expiry_batch_noop_when_neither_has_slash():
    assert _split_combined_expiry_batch("", "") == ("", "")


def test_items_from_csv_rows_splits_combined_expiry_batch_column():
    rows = [{"sku": "SKU1", "position_code": "H011A", "expiry": "2027-03/4471"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].expiry == "2027-03"
    assert items[0].batch == "4471"


def test_items_from_csv_rows_splits_combined_column_mapped_to_batch_field():
    rows = [{"sku": "SKU1", "position_code": "H011A", "batch": "2027-03/4471"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].expiry == "2027-03"
    assert items[0].batch == "4471"


def test_items_from_csv_rows_leaves_separate_columns_untouched():
    rows = [{"sku": "SKU1", "position_code": "H011A", "expiry": "2027-03", "batch": "4471"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].expiry == "2027-03"
    assert items[0].batch == "4471"


def test_items_from_csv_rows_maps_client_field():
    rows = [{"sku": "SKU1", "position_code": "H011A", "client": "Acme Corp"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].client == "Acme Corp"


def test_items_from_csv_rows_client_defaults_empty():
    rows = [{"sku": "SKU1", "position_code": "H011A"}]

    items, _skipped = items_from_csv_rows(rows)

    assert items[0].client == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_inventory_import.py -v`
Expected: FAIL with `ImportError: cannot import name '_split_combined_expiry_batch'`

- [ ] **Step 3: Implement**

Replace `app/core/inventory_import.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.core.position_generator import format_position_code, parse_position_code

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


def _split_combined_expiry_batch(expiry: str, batch: str) -> tuple[str, str]:
    if not batch and "/" in expiry:
        parts = expiry.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    if not expiry and "/" in batch:
        parts = batch.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    return expiry, batch


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

            expiry, batch = _split_combined_expiry_batch(
                (row.get("expiry") or "").strip(),
                (row.get("batch") or "").strip(),
            )

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
        except ValueError:
            skipped_rows.append(row_number)
    return items, skipped_rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_inventory_import.py -v`
Expected: PASS for all tests, including the pre-existing ones (the
existing `test_items_from_csv_rows_builds_items_with_position_code_column`
still passes because `client` defaults to `""` and the row under test has
no `client` key).

- [ ] **Step 5: Commit**

```bash
git add app/core/inventory_import.py tests/test_inventory_import.py
git commit -m "feat: Client field and combined Expiry/Batch CSV column support"
```

---

## Task 6: `render_inventory_label` — four-corner layout rewrite

**Files:**
- Modify: `app/core/label_renderer.py`
- Test: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: `load_font` (Task 1), `mm_to_px`/`font_size_for_height`
  (existing), `generate_qr_image` (existing).
- Produces: new `render_inventory_label` signature:
  ```python
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
  ) -> Image.Image
  ```
  Used by `mode_inventory_panel.py` in Task 7. This is a breaking signature
  change from the mode-2.2 version — no other code in the repo calls it yet
  except the panel updated in Task 7 and the tests replaced in this task.

- [ ] **Step 1: Replace the old `render_inventory_label` tests**

In `tests/test_label_renderer.py`, delete these five tests (they use the
old signature and are superseded):
`test_render_inventory_label_returns_image_of_expected_size`,
`test_render_inventory_label_changes_with_sku_data`,
`test_render_inventory_label_changes_with_position_data`,
`test_render_inventory_label_changes_with_text`,
`test_render_inventory_label_composes_at_all_built_in_sizes`.

Replace them with:

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


def test_render_inventory_label_renders_with_everything_optional_blank():
    img = render_inventory_label(
        "SKU1", "", "", "", "", "H011A", "C001H011A", "31072026",
        width_mm=68, height_mm=38,
    )
    assert isinstance(img, Image.Image)


def test_render_inventory_label_drops_secondary_chips_on_a_narrow_canvas():
    # sku_size + secondary_size leaves < 10mm for the middle column here
    img = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=35, height_mm=100,
    )
    assert isinstance(img, Image.Image)  # must not raise


@pytest.mark.parametrize(
    ("width_mm", "height_mm"),
    [(150, 100), (68, 38), (80, 80)],
)
def test_render_inventory_label_composes_at_all_built_in_sizes(width_mm, height_mm):
    img = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=width_mm, height_mm=height_mm,
    )
    assert img.size == (mm_to_px(width_mm), mm_to_px(height_mm))


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

(`pytest` is already imported at the top of this file.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_label_renderer.py -v -k render_inventory_label`
Expected: FAIL — `TypeError: render_inventory_label() takes from 3 to 6
positional arguments but 8 were given` (old signature still in place).

- [ ] **Step 3: Implement**

Replace the `render_inventory_label` function in
`app/core/label_renderer.py` (everything from `def render_inventory_label`
to the end of the file) with:

```python
_MIN_MIDDLE_WIDTH_MM = 10


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

    short_side = min(width_px, height_px)
    sku_size = max(1, round(short_side * 0.5))
    secondary_size = max(1, round(short_side * 0.25))
    min_middle_width_px = mm_to_px(_MIN_MIDDLE_WIDTH_MM, dpi)

    secondary_chips = [value for value in (expiry, batch) if value]
    if secondary_chips and (width_px - sku_size - secondary_size) < min_middle_width_px:
        secondary_chips = []

    bold_size = font_size_for_height(sku_size)
    caption_size = font_size_for_height(secondary_size)
    bold_font = load_font(bold_size, bold=True)
    caption_font = load_font(caption_size)

    # SKU: top-left corner, bold caption underneath.
    sku_qr = generate_qr_image(sku).resize((sku_size, sku_size))
    canvas.paste(sku_qr, (0, 0))
    draw.text((0, sku_size + 2), sku, fill="black", font=bold_font)

    # Expiry then Batch: stacked top-right corner, each captioned underneath.
    right_x = width_px - secondary_size
    chip_y = 0
    for value in secondary_chips:
        chip_qr = generate_qr_image(value).resize((secondary_size, secondary_size))
        canvas.paste(chip_qr, (right_x, chip_y))
        draw.text((right_x, chip_y + secondary_size + 2), value, fill="black", font=caption_font)
        chip_y += secondary_size + caption_size + 6

    # Position: bottom-left corner, bold caption beside it (to the right).
    position_y = height_px - secondary_size
    position_qr = generate_qr_image(position_data).resize((secondary_size, secondary_size))
    canvas.paste(position_qr, (0, position_y))
    caption_bbox = draw.textbbox((0, 0), position_code, font=bold_font)
    caption_height = caption_bbox[3] - caption_bbox[1]
    draw.text(
        (secondary_size + 6, position_y + max(0, (secondary_size - caption_height) // 2)),
        position_code,
        fill="black",
        font=bold_font,
    )

    # Middle column: Product name / Client / Exp+Batch / SKU, from upper-middle.
    middle_x = sku_size + 6
    exp_batch_parts = [
        part
        for part in (f"Exp {expiry}" if expiry else "", f"Batch {batch}" if batch else "")
        if part
    ]
    text_lines = [line for line in (name, client, " · ".join(exp_batch_parts), sku) if line]
    line_y = 4
    for line in text_lines:
        draw.text((middle_x, line_y), line, fill="black", font=caption_font)
        line_bbox = draw.textbbox((0, 0), line, font=caption_font)
        line_y += (line_bbox[3] - line_bbox[1]) + 4

    # Generation date: small, bottom-right corner.
    date_font = load_font(max(8, caption_size - 2))
    date_bbox = draw.textbbox((0, 0), generated_date, font=date_font)
    date_width = date_bbox[2] - date_bbox[0]
    date_height = date_bbox[3] - date_bbox[1]
    draw.text(
        (width_px - date_width - 2, height_px - date_height - 2),
        generated_date,
        fill="black",
        font=date_font,
    )

    return canvas
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_label_renderer.py -v`
Expected: PASS for the entire file (both `render_label` and
`render_inventory_label` suites).

- [ ] **Step 5: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "feat: four-corner Inventory label layout (SKU/Expiry/Batch/Position QRs)"
```

---

## Task 7: Inventory panel — Client column, Orientation combo, new render call

**Files:**
- Modify: `app/ui/mode_inventory_panel.py`
- Test: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: `apply_orientation` (Task 2), `InventoryItem.client` (Task 5),
  new `render_inventory_label` signature (Task 6).
- Produces: `InventoryModePanel.orientation_combo`; `TABLE_COLUMNS` gains a
  `"Client"` entry.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mode_inventory_panel.py` (add `import re` and
`from PIL import Image` to the imports):

```python
def test_client_column_populated_from_item():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A", "client": "Acme Corp"}])

    client_column = TABLE_COLUMNS.index("Client")
    assert panel.items_table.item(0, client_column).text() == "Acme Corp"


def test_orientation_defaults_to_landscape():
    _app()
    panel = InventoryModePanel(SETTINGS)
    assert panel.orientation_combo.currentText() == "Landscape"


def test_print_checked_items_uses_portrait_dimensions(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)  # 68x38mm size
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])
    panel.orientation_combo.setCurrentText("Portrait")

    calls = []
    monkeypatch.setattr(
        "app.ui.mode_inventory_panel.print_labels",
        lambda *a, **k: calls.append(k),
    )

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    assert calls[0]["width_mm"] == 38
    assert calls[0]["height_mm"] == 68


def test_print_checked_items_passes_generated_date_in_ddmmyyyy_format(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    render_calls = []

    def _fake_render(*args, **kwargs):
        render_calls.append(args)
        return Image.new("RGB", (10, 10))

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_inventory_label", _fake_render)
    monkeypatch.setattr("app.ui.mode_inventory_panel.print_labels", lambda *a, **k: None)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    generated_date = render_calls[0][7]
    assert re.fullmatch(r"\d{8}", generated_date)


def test_print_checked_items_passes_structured_fields_to_renderer(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {
                "sku": "SKU1",
                "name": "Widget",
                "client": "Acme Corp",
                "batch": "4471",
                "expiry": "2027-03",
                "position_code": "H011A",
            }
        ]
    )

    render_calls = []

    def _fake_render(*args, **kwargs):
        render_calls.append(args)
        return Image.new("RGB", (10, 10))

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_inventory_label", _fake_render)
    monkeypatch.setattr("app.ui.mode_inventory_panel.print_labels", lambda *a, **k: None)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    sku, name, client, batch, expiry, position_code, position_data = render_calls[0][:7]
    assert (sku, name, client, batch, expiry, position_code) == (
        "SKU1", "Widget", "Acme Corp", "4471", "2027-03", "H011A",
    )
    assert position_data == "C001H011A"  # warehouse prefix + position_code
```

Also fix the pre-existing `test_data_cells_are_not_editable` test (the
new Client column shifts the column count from 6 to 7):

```python
def test_data_cells_are_not_editable():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    for column in range(1, len(TABLE_COLUMNS)):
        cell = panel.items_table.item(0, column)
        assert not (cell.flags() & Qt.ItemFlag.ItemIsEditable)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: FAIL — `AttributeError: 'InventoryModePanel' object has no
attribute 'orientation_combo'` (and related failures from the old
`render_inventory_label` call signature still being in place).

- [ ] **Step 3: Implement**

In `app/ui/mode_inventory_panel.py`, update the imports:

```python
from datetime import datetime
from pathlib import Path

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

from app.core.audit_log import append_print_log
from app.core.config import default_settings_path
from app.core.inventory_import import (
    INVENTORY_CSV_FIELDS,
    InventoryItem,
    items_from_csv_rows,
)
from app.core.label_renderer import apply_orientation, render_inventory_label
from app.core.print_service import print_labels
from app.ui.csv_import_dialog import CsvImportDialog

TABLE_COLUMNS = ["", "SKU", "Name", "Client", "Position", "Batch", "Expiry"]
```

In `__init__`, after the `label_size_combo` is set up via
`refresh_from_settings`, add:

```python
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Landscape", "Portrait"])
```

Add it to the form (after the Label size row):

```python
        form.addRow("Label size", self.label_size_combo)
        form.addRow("Orientation", self.orientation_combo)
```

Replace `_populate_table`:

```python
    def _populate_table(self, items: list[InventoryItem]) -> None:
        self.items_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.items_table.setItem(row_index, 0, check_item)

            values = [item.sku, item.name, item.client, item.position_code, item.batch, item.expiry]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row_index, column, cell)
```

Replace `print_checked_items`:

```python
    def print_checked_items(self, output_pdf_path: Path | None = None) -> None:
        checked = self.checked_items()
        if not checked:
            raise ValueError("Nothing to print - import a CSV and check at least one row")

        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")

        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            raise ValueError("No warehouse selected - add one in Settings first")

        width_mm, height_mm = apply_orientation(
            label_size["width_mm"], label_size["height_mm"], self.orientation_combo.currentText()
        )
        generated_date = datetime.now().strftime("%d%m%Y")

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
                width_mm=width_mm,
                height_mm=height_mm,
            )
            images.append(image)

        print_labels(
            images,
            width_mm=width_mm,
            height_mm=height_mm,
            printer_name=self._settings.get("default_printer") or None,
            output_pdf_path=output_pdf_path,
        )

        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
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
Expected: PASS for all tests, including
`test_load_items_populates_table` (column 1 is still SKU, unaffected by
the new Client column at index 3).

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "feat: Client column, orientation, and new label fields in Inventory panel"
```

---

## Task 8: Adaptive CSV import dialog sizing

**Files:**
- Modify: `app/ui/csv_import_dialog.py`
- Test: `tests/test_csv_import_dialog.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no new public interface — `CsvImportDialog` behaves the same,
  just opens bigger with stretched preview columns.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_csv_import_dialog.py` (add
`from PySide6.QtWidgets import QHeaderView` to the imports):

```python
def test_dialog_has_a_bigger_default_size():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert dialog.size().width() >= 900
    assert dialog.size().height() >= 600


def test_preview_table_columns_stretch_to_fill_width():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert (
        dialog.preview_table.horizontalHeader().sectionResizeMode(0)
        == QHeaderView.ResizeMode.Stretch
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_csv_import_dialog.py -v -k "bigger_default_size or stretch"`
Expected: FAIL — dialog's default size is Qt's auto-computed tiny size,
and the header's default resize mode isn't `Stretch`.

- [ ] **Step 3: Implement**

In `app/ui/csv_import_dialog.py`, add to the imports:

```python
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
```

At the end of `__init__` (after `layout.addWidget(buttons)`), add:

```python
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.resize(900, 600)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_csv_import_dialog.py -v`
Expected: PASS for all tests.

- [ ] **Step 5: Commit**

```bash
git add app/ui/csv_import_dialog.py tests/test_csv_import_dialog.py
git commit -m "feat: bigger, adaptive default size for the CSV import dialog"
```

---

## Final check

- [ ] Run the full suite: `pytest -v`
- [ ] Run lint: `ruff check .`
- [ ] Manually smoke-test both panels in the running app (see the `run`
  skill or `python -m app.main`): import a small Cyrillic-containing
  inventory CSV, toggle Portrait/Landscape on both panels, and print to a
  PDF file to visually confirm the four-corner Inventory layout and the
  centered Positions layout look right.
