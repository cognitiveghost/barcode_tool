# Task 1: thermal-safe shipped templates + stabilisation fixes

Date: 2026-10-28. Detail design for **Task 1** of
`2026-10-28-thermal-templates-builder-updates-design.md` (the parent spec, owner-approved).
The parent spec's goals, anti-goals and constraints apply unchanged. This document pins down
what the parent left to the builder and records what the code actually does today.
Decisions here are **(Claude's call)** unless marked **(parent spec)**.

One PR. Tests run split as CI does (`.github/workflows/ci.yml`) with `QT_QPA_PLATFORM=offscreen`.

## 1. Thermal-safe shipped presets

Rule **(parent spec)**: no `background:#000` areas, no solid bar thicker than 0.5 mm. Emphasis
comes only from size, weight and 0.3–0.5 mm outlines. Barcodes and QRs are the only dense black.
Layouts must stay expressible in Task 4's builder model: absolute-mm text (bold, uppercase, size,
align), Code128, QR, outline box, 0.3–0.5 mm horizontal/vertical line.

Line convention for both presets: draw every line as a zero-width (vertical) or zero-height
(horizontal) absolutely positioned `div` with a `border-left`/`border-top` of 0.3 mm, never as a
`background:#000` box. That leaves no `background: #000` anywhere in thermal preset CSS.

### `positions/default` (150×100)
Only `.position-name` changes. Same box (`left:3mm; top:71mm; width:144mm; height:26mm`), drop
`background:#000` and `color:#fff`, add `border: 0.5mm solid #000`, text black. Keep bold, the
1 mm letter spacing and the `fit_font(visible_text, 136, 18, letter_spacing_mm=1)` call.
Update the CSS comment ("inverted so it reads across the aisle") to say outlined.
Builder equivalent: box + text on the same rectangle. `.user-text` and `.barcode-zone` stay.

### `inventory/default` (150×100)
- Every `.chip` becomes a caption: same position, size and font size as today, no background,
  black bold uppercase text, letter spacing 0.35 mm, centred. Rename the class to `.caption`
  (and `chip-*` to `caption-*`) so no stale "chip" naming survives.
- Under each caption, a 0.3 mm horizontal line (`.caption-rule`) spanning the caption's width,
  with its top at the caption's bottom edge (caption `top + height`).
- `.divider-v1` / `.divider-v2`: same `left`/`top`/`height`, now a 0.3 mm line (`width:0;
  border-left:0.3mm solid #000`) instead of a 0.9 mm black box.
- `.note-rule` (0.25 mm `background:#000` today) becomes a 0.3 mm `border-top` line at the same
  positions, so the CSS has no black backgrounds left.
- Everything else (frame, QRs, values, notes box, date) is unchanged.

### `inventory/qr-sku-68x38mm`
No change **(parent spec)**. `inventory-table/a4-table` is out of scope (office printer, Task 3).

### Black-area check (`app/core/template_renderer.py`)
A plain function in `app/core`, because Task 4's Save calls it too **(parent spec)**.

- `render_records(preset, records, dpi=DEFAULT_DPI, *, hide_codes=False)`. With
  `hide_codes=True` it passes one extra stylesheet to `LabelWriter.write_labels`:
  `weasyprint.CSS(string="img { visibility: hidden !important; }")`. Every barcode and QR in
  the presets (and in Task 4's generated ones) is an `<img>`, and `visibility:hidden` keeps the
  layout identical while leaving the code area white.
- `find_black_block(image, size_px=BLACK_BLOCK_PX) -> tuple[int, int] | None` with
  `BLACK_BLOCK_PX = 24` (3 mm at 203 dpi). Returns the top-left pixel of some fully black
  `size_px × size_px` square, or `None`. Pillow only (no numpy in the repo):
  1. `grey = ImageOps.expand(image.convert("L"), border=size_px, fill=255)` (white padding, so
     Pillow's edge replication in rank filters can't fake a block at the label edge).
  2. For even `size_px` (the default), `m = grey.filter(ImageFilter.MaxFilter(size_px - 1))`;
     then a pixel of `combined = lighter(lighter(m[0:w-1,0:h-1], m[1:w,0:h-1]),
     lighter(m[0:w-1,1:h], m[1:w,1:h]))` (crops, `ImageChops.lighter`) is 0 exactly when a
     `size_px × size_px` window is all black. For odd `size_px`, `combined = MaxFilter(size_px)`
     result directly.
  3. If `combined.getextrema()[0] != 0` return `None`; else take the first zero pixel
     (e.g. `combined.point(lambda v: 255 if v == 0 else 0).getbbox()[:2]`) and convert from
     filter-centre coordinates back to the label's top-left corner (subtract the padding and the
     filter radius). Exact coordinates only feed the error message; ±1 px is fine.
  Measured: MaxFilter(23) on a 150×100 mm label takes ~0.6 s.
- `find_thermal_black_block(preset, records) -> tuple[int, int, int] | None`: renders with
  `hide_codes=True` and returns `(record_index, x, y)` of the first block, or `None`.

Test (`tests/test_thermal_safe.py`, new): for every preset folder under
`EXAMPLES_ROOT / "positions"` and `EXAMPLES_ROOT / "inventory"` (discovered, so Task 4's new
presets are covered automatically; `inventory-table` is not a thermal mode and is excluded),
`find_thermal_black_block` over two records per mode (one realistic, one with very short values
so `fit_font` picks its maximum size) returns `None`. Plus unit tests for `find_black_block`:
a 24×24 black square is found, 23×24 and 24×23 are not, a black square touching the image edge
is found, and an all-white image returns `None`. A regression check that the **old**
`positions/default` CSS (inverted bar) is caught is worth one test, using a temp copy of the
preset with `background:#000` restored.

The automated check is the parent spec's 3×3 mm block test only. The "no bar thicker than
0.5 mm" half of the rule is a design rule for the shipped CSS, held by the line convention above
and by review, not by a bitmap test. A thick bar (say 2 mm × 100 mm) would pass the test; Task 4's
builder can't make one because its lines max out at 0.5 mm. **(Claude's call)**

Before/after PNG renders of both presets go in the PR description.

## 2. Bug fixes

### 2.1 Printer validity (`app/core/print_service.py`, `print_labels`)
Today: `painter = QPainter(printer)` with no checks, and `painter.end()` not in `finally`.
- When `printer_name` is set and `QPrinterInfo.printerInfo(printer_name).isNull()`, raise
  `OSError(f"Printer '{printer_name}' is not installed on this PC - check Settings.")` before
  anything else.
- After configuring: `if not printer.isValid(): raise OSError(...)`.
- `painter = QPainter(); if not painter.begin(printer): raise OSError(...)`; the drawing loop goes
  in `try/finally: painter.end()`.
- `OSError` because `PrintPreviewDialog` already shows `OSError` as "Print failed"
  (`print_preview_dialog.py:146`); any other exception type would escape the slot.

### 2.2 Audit row on a failed print (`app/core/print_batch.py`, `app/core/audit_log.py`)
Today the audit row is written only after every send succeeds; a mid-batch failure leaves no row.
- `LOG_COLUMNS` gains a last column `status`; `append_print_log(..., status="printed")`.
  Appending at the end keeps older per-print files and an existing `audit_log.csv` readable
  (old rows simply have an empty `status`). `consolidate_audit_log` needs no change.
- In `print_batch`, track `sent` = labels in fully completed sends. On an exception from the send
  loop: write an audit row with `status="failed"` and `count=sent` (labels confirmed sent before
  the failing send; the failing send itself may have printed some pages, which the operator must
  check), swallow and log an `OSError` from that audit write so it never masks the print error,
  then re-raise the original exception. On success, `status="printed"` as today.
  The unit is labels (images × completed sends), matching today's `total_count`. On the driver
  path one send is one spool job for the whole batch, so a single-copy failure records
  `count=0, status=failed`: the row proves the attempt happened and the operator checks the
  printer. Spooling is **not** split per label to get a finer count. **(Claude's call)**
- Raw ZPL needs no extra check: `print_labels_zpl` opens the named printer per label and raises
  `pywintypes.error` on an unknown or failed one, which `PrintPreviewDialog` already reports, and
  the failed-row path above catches any `Exception`, so it is audited as failed too.
- **Tidy (parent spec)**: the two `send_to_printer` calls at `print_batch.py:71-86` are one
  branch (export vs `copies` physical sends). Merge into one loop over
  `targets = [output_pdf_path] if output_pdf_path is not None else [None] * copies`, which is
  also what makes `sent` easy to count.

### 2.3 Warehouse snapshot (`app/ui/mode_positions_panel.py`)
`_render_labels` reads the warehouse at generation (`:258`); `print_current_labels` re-reads the
combo at print (`:367`), so the audit row can name a different warehouse than the barcodes.
Store `self._generated_warehouse = warehouse_prefix` next to `generated_codes` /
`_generated_preset` and use it in `print_current_labels`. Inventory mode renders at print time
from one read, so it has no such gap.

### 2.4 Shared settings (`app/core/config.py`, `app/ui/settings_window.py`,
`app/ui/main_window.py`, `app/ui/csv_import_dialog.py`)
Today: `load_settings` renames a corrupt file to `<name>.corrupt` (overwriting any earlier one)
and returns defaults. `sync_shared_settings` calls it without `on_recovery`, so a corrupt shared
file silently overlays `warehouses: []` and `csv_mappings: {}` onto this PC, and the next settings
save writes those empties back for everyone. The dialog always sends `warehouses`, even unchanged.

- **Quarantine name**: `load_settings` renames to
  `<name>.corrupt-<YYYYmmdd-HHMMSS>` (local time) so a second incident never overwrites the first.
- **Sync**: `sync_shared_settings(settings, local_path, on_recovery=None)`. If the shared file
  is unreadable: quarantine it, call `on_recovery(message)`, and **keep this PC's own values**
  for the shared keys (no overlay). The message says the shared settings were moved aside, names
  the kept file, and says this PC's own warehouses/CSV mappings stay in use. With the file gone,
  the existing "no shared file yet: seed it from this PC" path rewrites it on the next launch or
  save, which is the recovery.
- **Save**: `save_shared_settings(settings, local_path, keys=SHARED_SETTINGS_KEYS,
  on_recovery=None)` writes `settings[k]` for each `k` in `keys` over the shared file's current
  content. If the shared file is missing or unreadable (quarantined + `on_recovery`), it starts
  from `settings` for **all** shared keys instead of from empty defaults, so a save never writes
  empties. `settings` must carry `shared_folder` (it locates the file). The seed call inside
  `sync_shared_settings` becomes `save_shared_settings(settings, local_path)`.
- **Dialog**: `SettingsWindow.__init__` snapshots `copy.deepcopy(settings["warehouses"])`.
  `_save_and_close` passes `keys=("warehouses",)` only when the edited list differs from the
  snapshot, else `keys=()`, and passes an `on_recovery` that shows a warning. Last write wins per
  key if two PCs changed the same key **(parent spec)**.
- **CSV import dialog** (`csv_import_dialog.py:262-268`): call
  `save_shared_settings(self._settings, default_settings_path(), keys=("csv_mappings",))`.
- **Main window**: pass `on_recovery=self._warn_settings_recovered` to both
  `sync_shared_settings` calls (startup `:66` and after the dialog `:138`) and to the
  post-dialog `load_settings`. Retitle the box from "Settings reset" to "Settings problem",
  since a shared-file incident no longer resets anything.

### 2.5 Combined Exp/Bat column (`app/core/inventory_import.py:68-73`)
Today, when expiry and batch map to the same column, the value is split on the last `/`
whenever it has one, so the bare date `2026/08/02` becomes expiry `2026/08`, batch `02`.
New rule, as a small module-level function `_split_expiry_batch(value) -> (expiry, batch)`:
1. The whole value is a date → all expiry, batch empty.
2. Else, if it has a `/`, `left, right = value.rsplit("/", 1)`; when `left` is a date and
   `right` is not, return `(left.strip(), right.strip())`.
3. Else → all expiry, batch empty (today's behaviour for values with no `/`, e.g. `1-Jan`).

"A date" means `datetime.strptime` accepts it with one of these formats: full dates
`%Y/%m/%d`, `%Y-%m-%d`, `%d.%m.%Y`, `%d/%m/%Y`, `%d.%m.%y`; year-month `%Y/%m`, `%Y-%m`,
`%m/%Y`, `%m.%Y`. Year-month counts so that the existing `2027-03/4471` → `2027-03` / `4471`
case keeps working. Existing tests in `tests/test_inventory_import.py` (:103-160) must all still
pass; add `2026/08/02`, `02.08.2026`, `2026-08-02` → all expiry; `08/2027` → all expiry;
`ABC/123` → all expiry `ABC/123`, batch empty.

### 2.6 Label cap and confirmation (both panels)
Today both panels ask for confirmation above `LARGE_BATCH_THRESHOLD = 200` records and have no cap.
- Constants (one place, see 2.7): `MAX_LABELS_PER_RENDER = 2000`,
  `CONFIRM_LABELS_ABOVE = 300` **(parent spec)**. "Labels per render" = records rendered in one
  go (records × copies-per-record; copies-per-record is 1 until Task 4's per-unit option).
  Print-dialog copies repeat an already rendered batch and are not counted.
- Above the cap: `ValueError(f"{n} labels is more than the {MAX} allowed in one batch - split it into smaller batches.")`
  before any rendering. Positions: raised from `_render_labels`, shown by the existing
  `ValueError` handlers in `generate`/import. Inventory: checked in `_on_print_clicked` before
  the preview opens (warning box, return), and again in `print_checked_items`.
- Above 300: the existing Yes/No question and progress dialog, unchanged otherwise.

### 2.7 Panel de-duplication (parent spec tidy)
`_render_with_progress`, `refresh_from_settings` and `_warn_no_presets` are copy-pasted between
`mode_positions_panel.py` and `mode_inventory_panel.py`; they differ only in the mode string,
the QSettings key (`<mode>/last_template`), the prompt title ("Generate…" vs "Print a large
batch?") and the cancel exception (`GenerationCancelled` vs `PrintCancelled`).
New `app/ui/mode_panel.py` with `class ModePanel(QWidget)` holding those methods plus the two
constants from 2.6 and `_RENDER_CHUNK_SIZE`/`_ESTIMATED_SECONDS_PER_LABEL`. Subclasses set
class attributes `MODE`, `LARGE_BATCH_TITLE`, `CANCELLED` (exception class). The base's
`render_labels(preset, records)` does cap → confirm → chunked render with progress, or a plain
`render_records` at or below 300. `_show_status` (identical in both) and `_on_preset_selected`
(if it differs only by the QSettings key) move too. Each subclass's `__init__` calls
`super().__init__(parent)` and builds its own widgets as today; the base defines no UI.
Remove dead `self.items` (`mode_inventory_panel.py:90,194`); its two test reads
(`tests/test_mode_inventory_panel.py:201,222`) switch to `checked_items()` or the table.

## Testing notes for the builder
- WeasyPrint/Pango segfaults late in a single-process run. Run the suite split exactly like
  CI's Linux job; every test passes alone.
- Positions tests that push 250 codes to trigger the prompt (`test_mode_positions_panel.py:660`)
  need > 300 now.
- `QPrinterInfo` checks are testable by monkeypatching `QPrinterInfo.printerInfo` to return
  `QPrinterInfo()` (null).

## Out of scope
Everything in Tasks 2–4. No change to `qr-sku-68x38mm` or the A4 table. No cap on print-dialog
copies (noted for the owner).
