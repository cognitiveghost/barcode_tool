# Stabilization Patch Plan — 2026-08-02

Audit of `barcode_tool` at `ce31dcf` (branch `GUI-Impruvment`). 1428 LOC app code,
190 tests passing, 4 modes specified / 2 built.

**Scope decided with the user:**

| Decision | Choice |
|---|---|
| Modes | Stabilize 2.1 Positions + 2.2 Inventory only. No 2.3 / 2.4 this patch. |
| Preview | Preview shown in a dialog that offers **Print** or **Save as PDF**. |
| Generated files | One archive for both modes, with retention. |
| Concurrency | Real: several PCs may print at the same time. Locking + atomic writes required. |
| UI rework | Auto-caps, height checkbox removed, table/window sizing, CSV mapping recall. See [UI rework design](docs/2026-08-02-ui-rework-design.md). |

---

## Verdict

The core is better than it looks — the barcode/QR quiet-zone handling, the DPI
choice, the landscape double-flip fix, and the CSV-formula escaping are all
things a careless codebase gets wrong. The comments carry real reasoning.

What is missing is not cleverness, it is **the boring warehouse-app layer**:
nothing stops a bad label from being printed, nothing tells the operator what
went wrong, and the two mode panels have drifted into two different half-correct
implementations of the same job.

Three things make this not-yet-safe for a regular operator:

1. **Wrong labels print silently.** Five confirmed paths produce a label whose
   barcode does not match its text, or whose data has been mangled — with no
   warning. In a warehouse a wrong barcode is worse than no label.
2. **CSV import silently mis-reads common files.** A semicolon CSV (Excel's
   default in EU locales) parses as one column and imports as garbage. UTF-16
   (Excel "Unicode text") produces mojibake. No error either time.
3. **The operator is flying blind.** No preview, no live count, no reason for
   skipped rows, no log, unlabelled Settings fields, and a 26 000-label batch
   freezes the app with no progress or cancel.

---

## Phase 0 — Data integrity (blocks everything else)

These are the bugs that print a *wrong* label. All six reproduce; evidence
recorded below from the audit run.

### 0.1 Dates are shredded into batch numbers

[app/core/inventory_import.py:30-37](app/core/inventory_import.py#L30-L37)

`_split_combined_expiry_batch` splits on the first `/` whenever the other field
is empty. Real expiry dates contain `/`:

```
_split_combined_expiry_batch("2026/08/02", "")  ->  ("2026", "08/02")
```

The item then prints `EXP 2026` and `LOT 08/02`, and the inventory template
QR-encodes both — so the scanner reads a batch number that never existed.
No row is skipped, no warning is shown.

**Fix (lazy):** only split when the *other* half doesn't look like a date
fragment. A date has 2+ separators or a 4-digit year part; require the split to
yield exactly two parts and the second not to be numeric-with-separator. Simpler
and safer: only split on an explicit combined separator that isn't `/` — or drop
the heuristic and add `expiry`/`batch` as two mappable columns (already are).
**Recommendation: delete the heuristic.** The CSV dialog already lets the user
map expiry and batch separately; guessing costs correctness for a case the
mapping UI solves properly. Keep a single test proving `2026/08/02` survives.

### 0.2 Positions CSV import prints any junk as a position label

[app/core/position_generator.py:60-77](app/core/position_generator.py#L60-L77)

`codes_from_csv_rows` accepts a `position_code` cell if it is merely ASCII —
it never calls `parse_position_code`:

```
codes_from_csv_rows([{"position_code": "N/A"}, {"position_code": "see note"}])
->  (['N/A', 'see note'], [])          # zero rows skipped
display_position_code("N/A")  ->  'N/A' # printed as-is
```

The inventory importer *does* validate the same field
([inventory_import.py:56](app/core/inventory_import.py#L56)). Two importers,
two rules, same concept.

**Fix:** call `parse_position_code` in `codes_from_csv_rows` too. One shared
validation path for a position code, wherever it enters the app.

### 0.3 `format_position_code` accepts a corridor that isn't a corridor

[app/core/position_generator.py:9-18](app/core/position_generator.py#L9-L18)

`corridor.isascii()` is true for `""`, `"AB"`, `"%"`:

```
format_position_code("",   "1")  ->  "001"
format_position_code("AB", "1")  ->  "AB001"
format_position_code("%",  "1")  ->  "%001"
```

The UI's one-letter validator hides this; CSV import walks straight through it.

**Fix:** require exactly one ASCII letter. The check belongs here, not in the
widget — the widget is one of three callers. Lands in the same edit as 0.7.

### 0.4 Height ranges span punctuation

[app/core/position_generator.py:41-51](app/core/position_generator.py#L41-L51)

Range is built with `chr(ord(from)..ord(to))` with no letter check:

```
generate_position_codes("H","1","1","A","z")
->  58 codes, including H001[, H001\, H001], H001^, H001_, H001`
```

**Fix:** with 0.7 uppercasing both ends first, this reduces to "both ends must be
`A`–`Z`"; iterate letters only. No same-case rule needed.

### 0.5 Positions mode prints without a warehouse prefix, silently

[app/ui/mode_positions_panel.py:181](app/ui/mode_positions_panel.py#L181)

`warehouse_prefix = self.warehouse_combo.currentData() or ""` — with no
warehouse configured (the **first-run state**), every barcode payload is the
bare position code. The spec is explicit that the payload must carry the
warehouse prefix (`C001H029A`). The label looks perfect and scans to the wrong
value in the WMS. Inventory mode raises "No warehouse selected"
([mode_inventory_panel.py:178-180](app/ui/mode_inventory_panel.py#L178-L180));
Positions does not.

**Fix:** same guard in Positions. Better — see Phase 2, one shared print entry
point so this can only be written once.

### 0.6 Nothing checks that `meta.json` agrees with the template's `@page`

`meta.json` gives `width_mm`/`height_mm` used for the page size
([print_service.py:38](app/core/print_service.py#L38)); the CSS `@page` gives
the render size. `README.txt` says they must match; no code enforces it. When
they disagree, `painter.drawPixmap(painter.viewport(), ...)`
([print_service.py:52-54](app/core/print_service.py#L52-L54)) stretches the
label to fit — **distorted bars, unscannable label, no error.** This is the
failure mode that will bite the moment the user copies `default/` and edits it,
which the README actively tells them to do.

**Fix:** in `render_records`, compare the rendered bitmap's aspect ratio against
`preset.width_mm/height_mm` and raise if it is off by more than ~1%. Cheap, and
it catches the mistake at generate time with the preset name in the message.

### 0.7 The barcode and the printed text disagree on letter case

[position_generator.py:108](app/core/position_generator.py#L108),
[mode_positions_panel.py:194-195](app/ui/mode_positions_panel.py#L194-L195),
[mode_inventory_panel.py:197-198](app/ui/mode_inventory_panel.py#L197-L198)

Only the *display* is uppercased. The payload carries whatever the operator typed:

```
generate_position_codes("h","1","1","a","a")  ->  ["h001a"]
barcode payload:  "Ch001a"
printed text:     "H-001-A"
```

The label reads `H-001-A` and scans as `Ch001a`. Same class as 0.1–0.5, and the
reason the operator asked for auto-caps in the first place — the request is a
symptom of this, not a preference.

**Fix:** uppercase in `format_position_code` and `parse_position_code`. Every
entry path (typed input, positions CSV, inventory CSV) already routes through
those two, so this is one edit, not five. 4.6's input mask is then an affordance,
not the correctness boundary.

**Migration:** payloads generated from lowercase input change from `Ch001a` to
`CH001A`. Labels already on shelves will not match newly printed ones. Uppercase
is what the spec requires (`C001H029A`) — note it in the release note.

---

## Phase 1 — Shared-folder safety (multi-user is real)

### 1.1 A corrupt `settings.json` bricks the app

[app/core/config.py:19-29](app/core/config.py#L19-L29)

`load_settings` does a bare `json.load` — malformed JSON raises before
`MainWindow` exists, so the operator gets a console traceback and no window.
`save_settings` writes in place, so a crash or a full disk mid-write *creates*
that malformed file.

**Fix:** atomic write (`Path.write_text` to `settings.json.tmp` + `os.replace`),
and on load, catch `(OSError, ValueError)` → fall back to defaults, rename the
bad file to `settings.json.corrupt`, and surface one warning in the UI. Also
merge over `DEFAULT_SETTINGS` so a file from an older build can't be missing a
key.

### 1.2 Template seeding truncates files other machines are reading

[app/core/template_renderer.py:91-96](app/core/template_renderer.py#L91-L96)

The comment already names the hazard, and `_write_if_changed` only removes the
*unchanged* case. A genuine content change still truncates-then-writes on a
share another PC may be reading — that PC gets a half-written `template.html`
and its preset silently vanishes from the dropdown (the `except` at
[:56](app/core/template_renderer.py#L56) swallows it).

**Fix:** same temp+`os.replace` helper as 1.1. One function, both callers.

### 1.3 Audit log has a known concurrency hole

[app/core/audit_log.py:29-32](app/core/audit_log.py#L29-L32) — already marked
`ponytail:`. With concurrent printing confirmed real, this is now in scope:
two machines can both see "file doesn't exist" and write two headers, or
interleave a row.

**Fix:** `portalocker`-style advisory lock is a new dependency; on a network
share `fcntl`/`msvcrt` locking is unreliable anyway. **Lazy, actually-correct
option:** stop appending to one shared file. Write one row per print as
`audit/<utc-timestamp>_<user>_<pid>.csv` (never contended), and add a
"Consolidate audit log" action in Settings that merges them into
`audit_log.csv` on demand. No locking, no lost rows, no new dependency.
If the user prefers a single always-current file, fall back to lock-with-retry
and accept the share's limitations — decide at implementation time, note both.

### 1.4 App launch blocks on the network share

[template_renderer.py:64-88](app/core/template_renderer.py#L64-L88) — `list_presets`
calls `_seed_examples`, which does `mkdir` + 4 × `read_text` + up to 4 ×
`write_text`, **per mode**. Both panels call it in `__init__`
([mode_positions_panel.py:85](app/ui/mode_positions_panel.py#L85),
[mode_inventory_panel.py:58](app/ui/mode_inventory_panel.py#L58)) and again on
every settings save. So: 8+ file operations against a possibly-offline SMB share
before the window appears, with no timeout. A slow share = an app that looks
hung on startup.

**Fix:** seed once per process, not per panel construction (module-level flag or
`functools.lru_cache` on the mode dir). Show the window first, populate preset
combos after, and surface share failures as a status-bar warning instead of an
empty dropdown.

### 1.5 No shared folder configured is an invisible state

Both panels fall back to `default_settings_path().parent` = `~/.barcode_tool`
([positions:122](app/ui/mode_positions_panel.py#L122),
[inventory:99](app/ui/mode_inventory_panel.py#L99)). Templates, audit log and
archives quietly land in the home directory, and on a multi-PC setup each
machine keeps its own invisible copy. Nothing tells the user.

**Fix:** first-run state shows a single banner — "No shared folder configured —
using local folder. Open Settings." Not a modal wizard; one dismissible bar.

---

## Phase 2 — One print pipeline (the refactor that deletes bugs)

This is the highest-value refactor in the patch. The two panels currently
implement the same post-print sequence differently, and each got a *different
half* of the error handling right:

| | Positions | Inventory |
|---|---|---|
| Warehouse required | **no** (0.5) | yes |
| PDF archive | `printed_pdfs/<ts>_<prefix>_<desc>.pdf` | `inventory_label_preview_<ts>.pdf` in the folder **root**, described in code as a debug file |
| Archive failure handled | `ArchiveError` → "printed but archive failed" | **unhandled** → generic "Print failed" *after* labels printed |
| Audit failure handled | **unhandled** → generic "Print failed" | `AuditLogError` → "printed but log failed" |

Both dialogs say "Do not reprint this batch" — good instinct, wired up in only
one direction each. `ArchiveError` and `AuditLogError` are also declared in UI
modules ([positions:45](app/ui/mode_positions_panel.py#L45),
[inventory:38](app/ui/mode_inventory_panel.py#L38)) for a core concern.

**Fix:** one `app/core/print_batch.py` with a single function:

```python
def print_batch(images, preset, settings, *, mode, warehouse_prefix,
                description, copies=1, output_pdf_path=None) -> BatchResult
```

It validates (warehouse present, preset present, non-empty batch), prints,
archives, appends the audit row, and returns a result object listing which
non-fatal steps failed. `ArchiveError`/`AuditLogError` move here. Both panels
call it and render `result.warnings` in one shared message box. The asymmetry
table above stops being possible to write.

**Also removed by this:** the duplicated `refresh_from_settings`, warehouse
combo, preset combo and shared-folder resolution in both panels. Extract
`shared_folder(settings) -> Path` into `config.py` (5 call sites today, all
repeating the same `or default_settings_path().parent` fallback).

### 2.1 Unified archive with retention

Per the decision: `shared/printed_pdfs/<YYYY-MM>/<utc-ts>_<mode>_<prefix>_<desc>.pdf`
for **both** modes. Delete the stray `inventory_label_preview_*.pdf` write
([mode_inventory_panel.py:213-223](app/ui/mode_inventory_panel.py#L213-L223))
— it is a debug artifact shipping to a production share.

Retention: `archive_retention_days` in settings (default 90, `0` = keep
forever). Prune on app start, best-effort, only inside `printed_pdfs/`, only
files matching the archive name pattern. Never a recursive delete of a
user-configured path — a wrong `shared_folder` must not be able to erase
anything the app didn't write.

Note the current double-write: `print_current_labels(output_pdf_path=...)`
renders the PDF **twice** ([positions:227](app/ui/mode_positions_panel.py#L227)
then [:259](app/ui/mode_positions_panel.py#L259)). With one pipeline, render
the PDF once and copy it to the archive.

---

## Phase 3 — CSV import that survives real files

### 3.1 Delimiter is hard-coded to comma

[app/core/csv_import.py:13](app/core/csv_import.py#L13)

```
"sku;name;position"  ->  header ['sku;name;position']     # one column
"sku\tname"          ->  header ['sku\tname']             # one column
```

Excel on a EU locale exports `;` by default. The user then sees one nonsense
entry in every mapping dropdown and — if they click OK anyway — imports rows of
empty strings and gets "No valid inventory rows found". Nothing mentions the
delimiter.

**Fix:** `csv.Sniffer().sniff(sample, delimiters=",;\t|")` with a comma
fallback; show the detected delimiter in the dialog with an override combo. Both
stdlib, ~10 lines.

### 3.2 UTF-16 becomes mojibake with no error

[csv_import.py:10-12](app/core/csv_import.py#L10-L12) tries `utf-8-sig` then
`cp1251`. Excel's "Unicode text" export is UTF-16LE, which *decodes* under
cp1251 rather than raising:

```
read_csv(utf16_file)[0]  ->  ['яюs\x00k\x00u\x00', '\x00n\x00a\x00m\x00e\x00']
```

**Fix:** BOM sniff first (`utf-8-sig`, `utf-16`, `utf-16le/be`), then cp1251,
then a hard error naming the file and the encodings tried. Add an encoding
override combo next to the delimiter one.

### 3.3 Duplicate header names silently unreachable

[csv_import.py:24-27](app/core/csv_import.py#L24-L27) maps by name via
`header.index(column)` — first match wins:

```
header ['code','name','code']  ->  mapping {'sku':'code'} always yields column 0
```

**Fix:** dropdown carries the column *index* as item data and displays
`name (col 3)` for duplicates; `apply_mapping` takes indexes.

### 3.4 Skipped rows: count only, no reason, no row numbers

Both importers already collect the skipped row numbers
([inventory_import.py:74](app/core/inventory_import.py#L74),
[position_generator.py:76](app/core/position_generator.py#L76)) — and both
throw away the *reason* (`except ValueError:` with no capture). The UI prints
`(3 rows skipped)`. An operator printing 97 of 100 labels cannot find out which
three items got no label. For inventory data that's a stock-accuracy problem,
not a cosmetic one.

**Fix:** return `list[SkippedRow(row_number, reason)]`; the result label becomes
a clickable "3 rows skipped — show details" opening a small table
(row, reason, raw values), with Copy to clipboard.

### 3.5 Mapping is re-done by hand on every import

[csv_import_dialog.py:37-42](app/ui/csv_import_dialog.py#L37-L42) — 9 dropdowns
for inventory, all defaulting to `-- none --`. A daily import of the same
export format means 9 manual selections every single time. There is also no
validation that the required field (`sku`) is mapped: OK stays enabled, and the
failure surfaces later as a generic "no valid rows".

**Fix:**
- Auto-map on load by normalized header match (`case`/`_`/space-insensitive,
  plus a small synonym table: `sku|article|code`, `position|pos|location`,
  `expiry|exp|best_before`, `batch|lot`).
- **Remember the mapping per mode, keyed by the header row** — same export
  tomorrow, zero clicks. Requested explicitly; promoted from a nice-to-have.
  New `csv_mappings` settings key holding
  `{mode: {header_signature: {field: column_index}}}`; signature is the ordered
  header row, stripped and lowercased, joined with `\x1f`; capped at 20
  signatures per mode, oldest evicted first.
  **Two hard dependencies:** 3.3 first (the stored value is a column *index* —
  storing names re-introduces the duplicate-header bug on every recall), and 1.1
  first (merge-over-defaults, or an older `settings.json` has no `csv_mappings`
  key and the recall path raises on first import).
  Named mapping profiles remain out of scope.
- Disable OK until required fields are mapped, with an inline reason.
- Preview shows 5 rows now ([:21](app/ui/csv_import_dialog.py#L21)); mark rows
  that *would be skipped* in the preview so the problem is visible before import.

---

## Phase 4 — UI/UX

### 4.1 Settings window has no field labels at all

[app/ui/settings_window.py:78-85](app/ui/settings_window.py#L78-L85)

```python
layout.addWidget(self.printer_combo)
layout.addWidget(self.print_mode_combo)
layout.addWidget(self.raw_zpl_target_edit)
layout.addWidget(self.warehouse_table)
```

Widgets are stacked bare into a `QVBoxLayout`. The operator sees a text box, two
unlabelled combos, another text box, and a table — and must guess which is the
printer and which is the ZPL target. This is the single most visible UI defect
in the app.

**Fix:** `QFormLayout` with labels, grouped in `QGroupBox`es (Storage / Printing
/ Warehouses), help text under the ZPL target, and validation on save:
non-empty warehouse name+prefix, no duplicate prefixes, `raw_zpl_target`
required when `print_mode == raw_zpl` (today an empty target reaches
`Path("").write_bytes` and surfaces as a cryptic OS error).

### 4.2 Preview + Print / Save as PDF dialog

Per the decision, **Print becomes a confirmation screen**, not an immediate
action:

- Rendered first label, with `< n / N >` paging through the batch.
- Batch summary: count, label size, template name, target printer, warehouse.
- **Print** (with a copies spinbox) and **Save as PDF...** as the two actions,
  Cancel as the third.
- For a large batch, render only the pages being viewed — do not pre-render 26k.

This one dialog covers the missing preview, the missing print confirmation, the
missing copies control, and the missing explicit PDF export, and it is shared by
both modes (it takes a batch + preset, nothing mode-specific).

### 4.3 Large batches freeze the app

`generate_position_codes("A","0","999","A","Z")` → **26 000 labels**, each a
WeasyPrint render, on the GUI thread. No count shown before the click, no
progress, no cancel; Qt reports "not responding".

**Fix, in order of value:**
1. **Live count** next to the range fields: "→ 62 labels" as the user types.
   Prevents most of the problem for free.
2. **Threshold confirm** above ~200 labels: "Generate 26 000 labels? This will
   take about N minutes."
3. **`QProgressDialog` with Cancel** around rendering, updating per label.
   Rendering already loops per record, so this is a callback, not a rewrite.
4. Keep it on the GUI thread with the progress dialog (simplest correct option).
   A worker thread only if the progress dialog proves too janky — note as the
   upgrade path.

### 4.4 Inventory table can't be worked with

[mode_inventory_panel.py:70-71](app/ui/mode_inventory_panel.py#L70-L71) — a
plain `QTableWidget`: no sorting, no filtering, no column stretch (the CSV
dialog sets `Stretch`, this one doesn't, so columns truncate), and no
selected-count readout. With 2000 SKUs, "Select all / Select none" plus
scrolling is the entire toolkit.

**Fix:** filter box over SKU/name/position, stretch the header, show
"N of M selected" live, and enable sorting — **but** `checked_items()` maps
table row → `self.items[row]`
([:143-149](app/ui/mode_inventory_panel.py#L143-L149)), so enabling sorting
today would print the wrong items. Store the item on the row
(`Qt.ItemDataRole.UserRole`) **in the same commit as** `setSortingEnabled(True)`,
never in a later one, with a test that sorts and then asserts `checked_items()`
still returns the checked items. Latent bug; fix it as part of this, not after.

### 4.5 Smaller comfort items

- Disable **Print** until there is something to print, and **Generate** until
  the range is valid — instead of an error dialog after the click
  ([positions:220](app/ui/mode_positions_panel.py#L220),
  [inventory:176](app/ui/mode_inventory_panel.py#L176)).
- Status bar for last action / warnings (currently `QMessageBox` for everything,
  including non-errors).
- Remember window geometry and last-used template per mode.
- Ctrl+P print, Ctrl+O import, Ctrl+, settings.
- Spec 3.1 also asks for themes and a modern minimal layout — a light/dark
  palette toggle is cheap once the layouts are `QFormLayout`/`QGroupBox`;
  keep it last, it is the only purely cosmetic item here.

### 4.6 Letter fields force uppercase as you type

[mode_positions_panel.py:36](app/ui/mode_positions_panel.py#L36),
[:66-67](app/ui/mode_positions_panel.py#L66-L67),
[:76-80](app/ui/mode_positions_panel.py#L76-L80)

Corridor and both height fields accept `[A-Za-z]`, so the operator can type a
lowercase corridor and — before 0.7 — print a mismatched label. Even after 0.7
fixes correctness, the field should show what will be printed.

**Fix:** `edit.setInputMask(">a")` on `corridor_edit`, `height_from_edit`,
`height_to_edit`. One optional ASCII letter, forced uppercase. Verified against
PySide6 in this venv: empty `text()` stays `""` (so the existing `text() or None`
logic is untouched), typing `h` yields `"H"`.

**Deletes:** `_LETTER_VALIDATOR`, three `setValidator` calls, three
`setMaxLength(1)` calls, and the two `QRegularExpression*` imports.

### 4.7 Delete the "Use height" checkbox

[mode_positions_panel.py:74](app/ui/mode_positions_panel.py#L74),
[:102](app/ui/mode_positions_panel.py#L102),
[:149-150](app/ui/mode_positions_panel.py#L149-L150)

The request was "typing a height letter should enable height automatically" —
which makes the checkbox derivable state that can only ever disagree with the
fields. Remove it and the branch in `generate()`; height applies iff
`height_from_edit.text()` is non-empty, and core already defaults `height_to` to
`height_from`. No test references `height_enabled_check`.

### 4.8 CSV import dialog is unusable at nine fields

[csv_import_dialog.py:44-58](app/ui/csv_import_dialog.py#L44-L58)

Two defects, both visible in the operator's screenshot of an inventory import:

- `QHeaderView.ResizeMode.Stretch` divides the width across nine columns, so
  every header truncates — `SKU (required)` renders as `KU (required`,
  `Expiry (optional)` as `xpiry (optiona`. The operator cannot tell which column
  is which in the preview they are meant to be checking.
- Nine mapping combos stacked in a `QVBoxLayout` above the table leave the
  preview clipped at the bottom of the dialog.

**Fix:** header `ResizeToContents` with `setStretchLastSection(False)` and
horizontal scrolling, so a column is never narrower than its own header; mapping
form and preview in a `QSplitter(Qt.Vertical)` so the operator can give the
preview real height; persist dialog geometry with the same `QSettings` helper as
4.5 (per-machine — geometry must not travel through the shared folder).

---

## Phase 5 — Observability

There is **no log file anywhere**. When an operator says "it didn't print",
nothing can be inspected — `QMessageBox` text is gone the moment it's dismissed.

**Fix:** `logging` with a `RotatingFileHandler` at
`shared/logs/<hostname>.log` (per-host file, so it is concurrency-safe by
construction like 1.3), plus a "Open log folder" action in Settings. Log
settings load, preset discovery failures (currently swallowed at
[template_renderer.py:56](app/core/template_renderer.py#L56)), every print with
its parameters, and every handled exception.

**Audit log gaps:** it records `count` and a description but not the template
preset, printer, or print mode — so "reprint exactly what was printed" is not
possible from the log. Positions collapses to `first..last`
([positions:237-240](app/ui/mode_positions_panel.py#L237-L240)), which for a
CSV import of scattered codes is not a reproducible description. Add the preset
name and printer; for CSV batches store the row count and source filename.

---

## Deletions and simplifications

- **`_split_combined_expiry_batch`** — delete (0.1). The mapping UI already
  solves this properly; the guess costs data correctness.
- **`inventory_label_preview_<ts>.pdf`** — delete the write (2.1). Debug
  artifact on a production share.
- **`ArchiveError` / `AuditLogError` in UI modules** — move to core (Phase 2).
- **Duplicated `refresh_from_settings` / warehouse combo / preset combo /
  shared-folder fallback** — collapse into `print_batch` + `config.shared_folder`
  (Phase 2). This is ~60 duplicated lines across the two panels.
- **`height_enabled_check`** — delete (4.7). Derivable from the height field.
- **`_LETTER_VALIDATOR` + `setMaxLength(1)` × 3** — delete (4.6). Replaced by
  one `setInputMask(">a")` per field.
- **`custom_text` passed twice** as both `user_text` and `custom_text`
  ([positions:196-198](app/ui/mode_positions_panel.py#L196-L198)) — pick one and
  document the record contract.
- **`notes` in the inventory template** ([template.html:23](app/templates/examples/inventory/default/template.html))
  is never supplied by the panel, so `{% if notes %}` is always false. Either
  add `notes` to the CSV fields or keep the ruled area as handwriting-only and
  drop the variable. Decide, don't leave it ambiguous.
- **`README.txt` should list the template record fields.** The user is told to
  copy and edit presets, but nothing documents which variables exist
  (`code`, `barcode_data`, `visible_text`, `user_text`, `warehouse_prefix`,
  `sku`, `name`, `client`, `batch`, `expiry`, `position_code`, `position_data`,
  `generated_date`) or the `label_tools` helpers. Cheapest reliability win in
  the whole patch.
- **`.gitignore`** — add `graphify-out/` and `.graphifyignore`.

---

## Non-goals for this patch

- Modes 2.3 (product barcode) and 2.4 (free-text / sequential) — deferred by
  decision. Note that Phase 2's `print_batch` + Phase 4.2's preview dialog are
  exactly the seams both modes will need, so this patch shortens them.
- User-configurable label size in the UI (spec 1) — presets cover it for now;
  revisit with 2.3.
- Named CSV mapping profiles — decided against; header-signature auto-recall
  covers the "same format every day" case with zero clicks (3.5). Revisit only
  if one mapping per header layout proves insufficient.
- A worker thread for rendering — progress dialog first (4.3).
- Barcode verification via the already-installed `zxing-cpp` (decode the
  rendered label and assert the payload round-trips). Genuinely valuable for a
  warehouse app and the dependency is already in `requirements.txt`, but it is
  net-new capability rather than stabilization. Strong candidate for the next
  patch.

---

## Suggested execution order

Phase 0 first — everything else is polish on top of a system that can print
wrong data. Phase 2 before Phase 4, because the preview dialog and the batch
guard both hang off the unified pipeline. Phase 3 is independent and can run in
parallel. Phase 5 is small and can land any time.

Two ordering constraints the UI rework adds, both easy to get wrong:

- **3.5 needs 3.3 and 1.1 first** — index-based mapping and merge-over-defaults.
- **4.4's `UserRole` fix ships in the same commit as `setSortingEnabled(True)`** —
  sorting first prints the wrong items.

| Phase | Rough size | Test strategy |
|---|---|---|
| 0 Data integrity | small, mostly core | one regression test per confirmed defect (all 6 repro cases above) |
| 1 Shared-folder safety | small–medium | atomic-write + corrupt-settings-recovery tests |
| 2 Print pipeline | medium, touches both panels | existing 190 tests are the safety net; assert warning surfacing both ways |
| 3 CSV import | medium | fixture files: `;`-delimited, tab, UTF-16, duplicate headers, junk rows |
| 4 UI/UX | largest | `pytest-qt`-style panel tests already exist; extend for enable/disable and preview |
| 5 Observability | small | one test that a print produces a log line |

Existing suite is 190 tests, all green at `ce31dcf` — verified before this audit.
