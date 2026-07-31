# Label Orientation, Cyrillic Support & Inventory Label v2 — Design

Status: Approved (brainstorming stage, incl. visual companion mockups). No code written yet.
Parent designs:
`docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md`,
`docs/superpowers/specs/2026-07-31-mode-2-2-inventory-design.md`
(this spec supersedes that doc's §4 "Label layout" and §5 "Barcode content" for
`render_inventory_label` — see §4 below. §§1-3, 6-11 of that doc are unaffected.)

## 1. Purpose

Six incremental improvements to the two existing panels (Positions, Inventory)
and the shared rendering/import core:

1. Landscape/Portrait orientation for both panels, with content that scales
   and centers itself to whatever canvas results.
2. CSV inventory imports where Batch and Expiry share a single column
   (`/`-separated) instead of two columns.
3. Cyrillic text support in rendered labels.
4. Inventory label's Position caption placement fix (folded into §4).
5. Inventory label redesign: separate QR codes for SKU, Expiry, Batch, and
   Position, a smart four-corner layout, plus Client name and a generation
   date footer.
6. A bigger, adaptive default size for the CSV import dialog.

## 2. Orientation (Positions + Inventory panels)

Each panel gets one new "Orientation" combo (Landscape / Portrait), next to
the existing Label size combo. Defaults to Landscape each session (matches
today's unswapped behavior); not persisted to settings.

```python
def apply_orientation(width_mm: float, height_mm: float, orientation: str) -> tuple[float, float]:
    if orientation == "Portrait" and width_mm > height_mm:
        return height_mm, width_mm
    if orientation == "Landscape" and height_mm > width_mm:
        return height_mm, width_mm
    return width_mm, height_mm
```

Picking an orientation swaps the selected label size's width/height before
rendering — no duplicate size presets in Settings. A square size (80×80mm)
is a no-op either way. Both panels call this before passing dimensions to
their render function.

**Positions label (`render_label`, Code128 barcode):** confirmed via mockup
— in Portrait the barcode scales down to fit the narrower width (no
rotation; simplest, and scanners already handle any rotation fine if a
future case needs it). The barcode+text block is centered as a unit both
horizontally *and* vertically in the canvas — today it's pinned to the top
(`canvas.paste(barcode_img, (barcode_x, 0))`), which left dead space at the
bottom on tall canvases. This is the "smart scaling and centering" from the
original ask.

**Inventory label (`render_inventory_label`):** orientation just changes
canvas width/height; the four-corner layout (§4) reflows against whatever
space results, using the same sizing formula regardless of shape.

## 3. Cyrillic support

`ImageFont.load_default()` is PIL's built-in bitmap font — it cannot render
Cyrillic (or most non-Latin scripts) at all; it silently produces tofu/blank
glyphs. Since the app ships as a PyInstaller standalone exe on Windows and
Ubuntu (parent design §"Packaging"), we can't rely on an OS-installed font
being present.

Bundle `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` under `app/assets/fonts/`
(Bitstream Vera License, permissive; full Latin + Cyrillic coverage;
confirmed present and usable on this dev machine). Both `render_label` and
`render_inventory_label` switch from `ImageFont.load_default()` to
`ImageFont.truetype()` loading these bundled files — regular weight for body
text, bold for the SKU and Position captions (§4). `font_size_for_height`
keeps its existing scaling formula.

## 4. Inventory label redesign (supersedes mode-2.2 spec §4-§5)

Locked in from mockup iteration. Reference canvas: 150×100mm (the built-in
"100x150mm" size in Landscape orientation, per §2's swap).

```
┌──────────────────────────────────────────────────────────┐
│ [SKU QR 50%]      Widget XL-200            [Exp QR 25%]   │
│  SKU-1200          Acme Corp                 2027-03      │
│                     Exp 2027-03 · Batch 4471               │
│                     SKU-1200                [Batch QR 25%] │
│                                                 4471       │
│ [Pos QR 25%] H011A                                         │
│                                                  31072026  │
└──────────────────────────────────────────────────────────┘
```

- **SKU QR**, top-left corner, bold caption (raw SKU) underneath.
- **Expiry QR** then **Batch QR**, stacked top-right corner, each with a
  regular-weight caption (the raw value) underneath.
- **Position QR**, bottom-left corner. Caption sits *beside* it (to the
  right), bold — the one exception to "caption underneath"; confirmed via
  mockup over the original "signed under QR" wording. Caption shows the
  plain position code (no warehouse prefix); the QR itself still encodes
  `{warehouse_prefix}{position_code}` (mode-2.2's hidden-prefix rule,
  unchanged).
- **Middle column**, starting at upper-middle: plain text, top to bottom —
  Product name, Client name, `Exp {expiry} · Batch {batch}`, SKU. Any line
  whose underlying value is empty is omitted (same principle as mode-2.2's
  original text-omission rule). If both expiry and batch are empty, that
  combined line is omitted entirely.
- **Generation date**, small text, bottom-right corner. Format `DDMMYYYY`,
  computed by the caller at print time (not read from the CSV) and passed
  in as an explicit parameter — keeps rendering deterministic/testable
  rather than calling `datetime.now()` inside the renderer.
- **Sizing formula**: SKU QR side = 50% of `min(width_px, height_px)`;
  Expiry/Batch/Position QR side = 25% of `min(width_px, height_px)`. Same
  formula at every label size and orientation — confirmed this produces
  identical absolute QR sizes on both the 150×100 and 100×100 reference
  mockups, which is why no shape-specific branching is needed.
- **Graceful degradation**: Expiry and Batch share one fixed-width column
  (they stack vertically within it), so dropping only one of them never
  frees any width — only dropping *both* does. If fitting the secondary
  column at its formula width would leave the middle text column narrower
  than 10mm, drop Expiry and Batch together, freeing the whole column. SKU
  and Position are never dropped — they anchor their own corners, not a
  shared column. This is in addition to (not instead of) the existing
  per-row rule that a chip is simply absent when its underlying CSV value
  is empty. 10mm is a starting point, not a measured legibility threshold —
  revisit if real small-label prints look wrong.

**New `render_inventory_label` signature** (breaking change from mode-2.2's
version — call sites and tests are updated together):

```python
def render_inventory_label(
    sku: str,
    name: str,
    client: str,
    batch: str,
    expiry: str,
    position_code: str,   # display text, no warehouse prefix
    position_data: str,   # QR content, with warehouse prefix
    generated_date: str,  # DDMMYYYY
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image
```

## 5. CSV inventory: combined Expiry/Batch column

Some stock exports put Expiry and Batch in one column as `expiry/batch`
(confirmed order: Expiry first). No new dialog UI — auto-detected from
content after mapping: if the mapped `expiry` value contains `/` and
`batch` is empty (or the mirror case), split on the first `/` and use the
two parts. Handles the common case (user maps only one of the two fields to
the combined column) without adding mapping-mode UI to `CsvImportDialog`.

```python
def _split_combined_expiry_batch(expiry: str, batch: str) -> tuple[str, str]:
    if not batch and "/" in expiry:
        parts = expiry.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    if not expiry and "/" in batch:
        parts = batch.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    return expiry, batch
```

Applied inside `items_from_csv_rows` after the existing per-field mapping,
before constructing each `InventoryItem`.

## 6. CSV inventory: Client field

Stock exports also carry the client's name. New optional field: added to
`INVENTORY_CSV_FIELDS` (`"client"`, "Client (optional)") and to
`InventoryItem` as `client: str`, defaulting to `""` like `batch`/`expiry`
when unmapped or blank. Feeds the middle-column "Client name" text line
(§4).

## 7. Adaptive CSV import dialog sizing

`CsvImportDialog` has no explicit size today, so Qt auto-sizes it to a tiny
default. Give it a sensible default (`resize(900, 600)` in `__init__`) and
set the preview table's horizontal header to stretch columns
(`QHeaderView.ResizeMode.Stretch`) so the mapped-column preview actually
uses the available width. The dialog remains user-resizable as before.

## 8. Module breakdown (additions/changes)

```
core/
  label_renderer.py     — + apply_orientation(width_mm, height_mm, orientation)
                           ~ render_label: bundled truetype font, content block
                             centered horizontally + vertically
                           ~ render_inventory_label: rewritten — four-corner
                             layout, new signature (§4)
  inventory_import.py   — + "client" field (INVENTORY_CSV_FIELDS, InventoryItem)
                           + _split_combined_expiry_batch, applied in
                             items_from_csv_rows
assets/
  fonts/DejaVuSans.ttf, DejaVuSans-Bold.ttf — new bundled binary assets

ui/
  mode_positions_panel.py — + Orientation combo (default Landscape); calls
                             apply_orientation before render_label
  mode_inventory_panel.py — + Orientation combo (same pattern); computes
                             generated_date (datetime.now, DDMMYYYY) once per
                             print batch; passes new structured fields to
                             render_inventory_label
  csv_import_dialog.py    — default size 900x600; preview table columns
                             stretch to fill width
```

No new dependencies — `qrcode`, `Pillow`, `PySide6` already cover
everything; the DejaVu fonts are bundled assets, not packages.

## 9. Testing approach

- `tests/test_label_renderer.py` — `apply_orientation`: all three cases
  (Landscape enforces width≥height, Portrait enforces height≥width, square
  is a no-op both ways). `render_label`: correct size post-swap, content
  block vertically+horizontally centered. Cyrillic text renders without
  raising and produces non-blank output (distinct from a blank-canvas
  control). `render_inventory_label`: all four corners present at the
  150×100 reference size; Expiry/Batch chips absent when the field is
  empty; Expiry/Batch chips dropped (not a crash) when the canvas is too
  small to fit them; existing parametrized built-in-sizes test updated to
  the new signature; Position QR still encodes the prefixed value while the
  caption shows the unprefixed code.
- `tests/test_inventory_import.py` — `_split_combined_expiry_batch`:
  Expiry/Batch order, mirror case, neither/both containing `/`; `client`
  field mapped and defaulted.
- `tests/test_mode_positions_panel.py` / `tests/test_mode_inventory_panel.py`
  — Orientation combo wiring: selecting Portrait produces swapped-dimension
  output images.
- `tests/test_csv_import_dialog.py` — dialog's initial size meets the new
  minimum.

## 10. Explicitly out of scope

- Persisting orientation choice across sessions — session-only, defaults to
  Landscape.
- Editable/reorderable label_sizes via Settings UI (pre-existing gap, not
  part of this ask).
- Any script beyond Latin + Cyrillic (DejaVuSans covers more than that, but
  no other script is a stated requirement).
- Making the four-corner Inventory layout user-configurable — it's a fixed
  algorithm.
- Remembering the CSV import dialog's resized size/position across
  sessions — just a bigger default.
- QR error-correction level or box-size tuning — unchanged from mode-2.2
  defaults.
