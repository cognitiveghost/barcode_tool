# Inventory Label v3 — Fixed Format, Layout Fix, Print/CSV Bugfixes — Design

Status: Approved (brainstorming stage, incl. hand-drawn mockup). No code written yet.
Parent designs:
`docs/superpowers/specs/2026-07-31-mode-2-2-inventory-design.md`,
`docs/superpowers/specs/2026-07-31-label-orientation-inventory-v2-design.md`
(this spec supersedes that doc's §2 "Orientation" for the Inventory panel only —
Positions panel orientation is unaffected — and rewrites §4 "Inventory label
redesign" in full. §§1, 3, 5-11 of the v2 doc are unaffected.)

Trigger: test prints of PR #4 (screenshots) showed unreadable text, missing
sections, a paper-clipping bug on landscape prints, and a Cyrillic Client
field silently coming out blank.

## 1. Purpose

Fix the Inventory label so a real 100×150mm thermal label prints correctly
and legibly, and remove the size/orientation choices that were causing more
harm than value.

## 2. Fixed format — remove Label size / Orientation from the Inventory panel

The Inventory panel only ever needs one physical format. Both
`label_size_combo` and `orientation_combo` are removed from
`InventoryModePanel` (form rows, widgets, and the `apply_orientation` call).
Two new module constants in `mode_inventory_panel.py` replace them:

```python
INVENTORY_LABEL_WIDTH_MM = 150
INVENTORY_LABEL_HEIGHT_MM = 100
```

`print_checked_items` uses these directly instead of reading
`label_size_combo.currentData()` / `orientation_combo.currentText()`. The
"No label size selected" validation error goes away — there's nothing left
to misconfigure.

The Positions panel (Mode 2.1) keeps its own `label_size_combo` and
`orientation_combo`, entirely unaffected — this change is scoped to
`mode_inventory_panel.py` only.

## 3. Root-cause bugfix: landscape paper gets clipped to portrait

**Symptom** (screenshot 3): a label rendered in landscape (150×100) prints
as if the physical page were still portrait, cutting off content.

**Root cause**: `print_service.print_labels` builds a custom
`QPageSize(QSizeF(width_mm, height_mm))` and never calls
`printer.setPageOrientation(...)`. `QPrinter`'s orientation defaults to
`QPageLayout.Orientation.Portrait` regardless of the aspect ratio of the
custom size handed to `setPageSize` — so a 150×100 (wide) page is silently
re-normalized toward a portrait shape by Qt's print pipeline, clipping
whatever was drawn assuming the full 150×100 canvas.

**Fix**, in `print_labels` (`app/core/print_service.py`), right after
`setPageSize`:

```python
orientation = (
    QPageLayout.Orientation.Landscape
    if width_mm > height_mm
    else QPageLayout.Orientation.Portrait
)
printer.setPageOrientation(orientation)
```

This is in the shared function used by both panels, so Mode 2.1's Portrait
label sizes get the same correctness fix at no extra cost — not new scope,
just not artificially avoided.

## 4. Root-cause bugfix: Cyrillic Client field comes out blank

**Symptom**: a CSV with a Cyrillic client name imports successfully (other
fields populate fine), but the Client column is empty.

**Root cause**: `csv_import.read_csv` opens the file with a hardcoded
`encoding="utf-8"`. Stock/ERP exports with Cyrillic content are commonly
saved as `cp1251` (legacy Windows Cyrillic) or UTF-8 with a leading BOM
(`utf-8-sig`) — Excel's "CSV UTF-8" export option adds a BOM, and Python's
strict `utf-8` codec either raises `UnicodeDecodeError` on `cp1251` bytes or
leaves a stray `﻿` glued to the first header name, both of which break
mapping-by-name for whichever field lands on the affected bytes.

**Fix**, in `read_csv` (`app/core/csv_import.py`): try `utf-8-sig` first
(transparently handles both plain UTF-8 and BOM'd UTF-8 — the common case),
falling back to `cp1251` if decoding fails:

```python
def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1251")
    all_rows = list(csv.reader(text.splitlines()))
    ...
```

No new dependency — both codecs are in the stdlib. Scope stays narrow: two
encodings that cover "modern Excel export" and "legacy Cyrillic export",
not a general charset-detection library.

## 5. Inventory label layout — three-column grid

Confirmed via hand-drawn mockup. Canvas is always 150×100mm (§2). A 5mm
margin runs around the whole label (no drawn outer border — just breathing
room from the physical edge); the layout below is placed inside that
margin. Divider lines (bold, ~3px) separate the three columns; a third
divider splits the middle column only (it does not cross into the QR
columns on either side).

```
┌─────────────┬───────────────────────────────┬─────────────┐
│ [SKU QR]    │ PRODUCT NAME                  │ [Expiry QR] │
│             │ Expiry: 2027-03-01             │             │
│ SKU-1200    │ Batch: 4471                    │ 2027-03-01  │
│             │ SKU: SKU-1200                  │             │
│             │ Position: H011A                │             │
│             ├───────────────────────────────┤             │
│  H011A      │        Acme Corp                │  4471       │
│ [Pos QR]    │                    31072026     │ [Batch QR]  │
└─────────────┴───────────────────────────────┴─────────────┘
```

- **Left column** (~32% of content width): SKU QR pinned to the top of the
  column, its bold caption (raw SKU) directly below it. Position QR pinned
  to the bottom of the column, its bold caption (plain `position_code`, no
  warehouse prefix — unchanged hidden-prefix rule) directly above it. Both
  captions face inward toward the vertical middle of the column. SKU and
  Position QR/caption pairs are never omitted (SKU and position code are
  always present — validated at import).
- **Right column** (~17% of content width, smaller QRs — secondary,
  scan-optional): Expiry QR pinned top with its caption below; Batch QR
  pinned bottom with its caption above. Either pair is omitted entirely
  when its underlying value is empty (unchanged omit-if-blank philosophy),
  freeing that corner rather than leaving a broken/empty QR.
- **Middle column**, split by one horizontal divider:
  - Top half: a plain, clearly legible text list, one item per line —
    product name as a bold title line (no label prefix), then
    `Expiry: {value}`, `Batch: {value}`, `SKU: {value}`,
    `Position: {position_code}`. Any line is omitted if its value is empty
    (name/expiry/batch can be blank; SKU/position never are).
  - Bottom half: Client name, centered. Generation date (`DDMMYYYY`,
    caller-supplied, unchanged from v2) in small text, bottom-right corner
    of this zone — not the label's absolute corner, so it never collides
    with the Batch QR in the right column.
- Font sizes for the text list and captions are sized generously relative
  to their zone (roughly matching the mockup's proportions) — this is a
  fixed single canvas size now, so there's no need for a formula that
  adapts to arbitrary label dimensions; exact mm/pt numbers are tuned by
  rendering and visually inspecting the debug PDF (§6) rather than derived
  analytically up front.
- The `_MIN_MIDDLE_WIDTH_MM` chip-dropping-together logic from v2 is
  deleted — it existed to handle small/narrow canvases that no longer
  exist now that the size is fixed at 150×100. Expiry/Batch are dropped
  individually (per §5's per-field blank rule), never as a pair for width
  reasons.

**`render_inventory_label` signature is unchanged** from v2 — same
parameters (`sku, name, client, batch, expiry, position_code, position_data,
generated_date, width_mm, height_mm, dpi`) — this is an internal rewrite of
the drawing logic, not an interface change. The function stays a generic
pure renderer (still takes `width_mm`/`height_mm`); the Inventory panel is
just the only caller, and it now always passes 150/100.

## 6. Debug PDF — always saved alongside the audit log

Every `print_checked_items()` call — whether or not it also goes to a
physical printer — additionally writes a PDF copy of the batch into the
shared folder, next to `audit_log.csv`:

```python
shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
debug_pdf_path = Path(shared_folder) / f"inventory_label_preview_{datetime.now():%Y%m%d_%H%M%S}.pdf"
print_labels(images, width_mm=..., height_mm=..., output_pdf_path=debug_pdf_path)
```

This is in addition to the existing `print_labels(..., printer_name=...,
output_pdf_path=output_pdf_path)` call — that call's behavior (real print,
or an explicit caller-supplied PDF path) is unchanged. The debug copy always
happens regardless, timestamped so repeated test batches don't overwrite
each other and so it's obvious which file is the latest. This directly
enables checking real print output without consuming physical labels, and
is how this fix itself gets visually verified during implementation.

## 7. Module breakdown

```
core/
  csv_import.py       ~ read_csv: utf-8-sig then cp1251 fallback (§4)
  print_service.py    ~ print_labels: explicit setPageOrientation (§3)
  label_renderer.py   ~ render_inventory_label: rewritten drawing logic for
                        the three-column grid (§5); _MIN_MIDDLE_WIDTH_MM and
                        the chip-dropping-together branch deleted
ui/
  mode_inventory_panel.py — label_size_combo + orientation_combo removed;
                             INVENTORY_LABEL_WIDTH_MM/HEIGHT_MM constants;
                             print_checked_items always writes a timestamped
                             debug PDF to the shared folder (§6)
```

No new dependencies.

## 8. Testing approach

- `tests/test_csv_import.py` — `read_csv` decodes a `cp1251`-encoded file
  with Cyrillic content; decodes a UTF-8-with-BOM file without a stray
  `﻿` on the first header; existing plain-UTF-8 tests keep passing.
- `tests/test_print_service.py` — `print_labels` sets Landscape orientation
  when `width_mm > height_mm`, Portrait otherwise (assert via
  `printer.pageLayout().orientation()` captured before `painter.end()`, or
  by checking the produced PDF's page is wider than tall for a 150×100
  call — whichever is reliably assertable against a real `QPrinter`).
- `tests/test_label_renderer.py` — replace the four-corner-specific tests
  (drop-secondary-chips-on-narrow-canvas, the multi-size parametrization)
  with tests against the fixed 150×100 shape: all three columns present;
  Expiry/Batch chip individually omitted when blank; Position caption never
  includes the warehouse prefix while the QR data does; renders without
  raising when name/client/batch/expiry are all blank.
- `tests/test_mode_inventory_panel.py` — remove
  `test_orientation_defaults_to_landscape`,
  `test_print_checked_items_uses_portrait_dimensions`,
  `test_refresh_from_settings_rebuilds_combos`'s label-size-combo assertion,
  and `test_print_checked_items_raises_without_label_size` (nothing left to
  misconfigure). Add: `print_checked_items` always writes a timestamped PDF
  into `shared_folder` in addition to the normal print call; the debug PDF
  is written even when `output_pdf_path` is also explicitly passed.

## 9. Explicitly out of scope

- Any label size other than 150×100 for Inventory — this is now a fixed
  format, not a configurable one.
- Cleaning up old `inventory_label_preview_*.pdf` files from the shared
  folder — no retention/cleanup policy for now; revisit if the folder
  actually becomes cluttered in practice.
- General charset auto-detection (e.g. `chardet`/`charset-normalizer`) —
  two explicit fallback encodings cover the known real-world case.
- Changing Mode 2.1 (Positions panel)'s own size/orientation UI — it keeps
  its combos; only the shared print-orientation bugfix is common code.
