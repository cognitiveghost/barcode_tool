# Task 1: Thermal-safe presets + stabilisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every solid black fill from the shipped thermal presets, guard that with an `app/core` black-area check, and fix the seven verified stabilisation bugs.

**Architecture:** A Pillow-only `find_black_block` scans a render made with code `<img>`s hidden; a test runs it over every shipped thermal preset. Bug fixes stay in their current modules; the two mode panels get a small `ModePanel` base for their shared render/refresh code.

**Tech Stack:** Python 3.11+, PySide6, WeasyPrint via blabel, pypdfium2, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-task1-thermal-safe-stabilisation-design.md` (read it; section numbers below refer to it). Parent: `docs/superpowers/specs/2026-10-28-thermal-templates-builder-updates-design.md`, Task 1.

## Global Constraints

- Thermal presets: no `background: #000` anywhere in their CSS; no solid bar thicker than 0.5 mm; lines are 0.3 mm (outlines 0.3–0.5 mm). Barcodes/QRs are the only dense black.
- Black block = 24×24 dots (3 mm at 203 dpi), fully black, code images ignored.
- `MAX_LABELS_PER_RENDER = 2000`, `CONFIRM_LABELS_ABOVE = 300`.
- No new dependencies (no numpy).
- Every command runs from the worktree root with `QT_QPA_PLATFORM=offscreen` and `.venv/bin/python`.
- Never run the whole suite in one process (WeasyPrint/Pango segfault). The full gate is the CI split:
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -k test_shipped_default_actually_applies_the_bundled_font
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -k "not test_shipped_default_actually_applies_the_bundled_font"
  .venv/bin/ruff check .
  ```
  If the second command segfaults late, rerun it with `-p no:cacheprovider tests/<file>` per file to confirm each file passes alone, and report that.
- Error types: anything the print path raises for the operator to see must be `OSError` or `ValueError` (that is what `PrintPreviewDialog` catches).
- Commit after each task; messages end with the `Co-Authored-By` line the runner gives.

## Review Focus

1. Shared `settings.json` becomes unreadable **between** launch and a Settings save → the save must not write empty warehouses/mappings. Test: `test_save_shared_settings_seeds_from_settings_when_shared_file_is_corrupt` (Task 5).
2. Printer named in Settings was uninstalled → print fails with `OSError`, and the audit row says `failed`, never `printed`. Tests in Tasks 3 and 4.
3. The audit write itself fails while recording a failed print → the operator still sees the original print error. Test: `test_failed_audit_write_does_not_mask_the_print_error` (Task 4).
4. Exactly 2000 vs 2001 labels, exactly 300 vs 301 → 2000 renders, 2001 refuses before rendering; 300 renders without asking, 301 asks. Tests in Task 8.
5. Very short field values push `fit_font` to its maximum size, the thickest strokes → still no 3 mm black block. The short record in Task 2's test.

---

### Task 1: Black-area check in `app/core`

**Files:**
- Modify: `app/core/template_renderer.py` (`render_records` at ~:131; add two functions + one constant)
- Create: `tests/test_black_area.py`

**Interfaces:**
- Produces:
  - `BLACK_BLOCK_PX: int = 24`
  - `render_records(preset, records, dpi=DEFAULT_DPI, *, hide_codes: bool = False) -> list[Image.Image]`
  - `find_black_block(image: Image.Image, size_px: int = BLACK_BLOCK_PX) -> tuple[int, int] | None` (top-left x, y in label pixels; ±1 px)
  - `find_thermal_black_block(preset: TemplatePreset, records: list[dict]) -> tuple[int, int, int] | None` (`(record_index, x, y)`)

- [ ] **Step 1: Write the failing tests** in `tests/test_black_area.py`:

```python
from PIL import Image, ImageDraw
from app.core.template_renderer import find_black_block

def _label_with_square(w, h, x=100, y=50, size=(1218, 812)):
    img = Image.new("1", size, 1)
    ImageDraw.Draw(img).rectangle((x, y, x + w - 1, y + h - 1), fill=0)
    return img

def test_finds_a_24_dot_square():
    found = find_black_block(_label_with_square(24, 24))
    assert found is not None and abs(found[0] - 100) <= 1 and abs(found[1] - 50) <= 1

def test_ignores_a_square_one_dot_short_either_way():
    assert find_black_block(_label_with_square(23, 24)) is None
    assert find_black_block(_label_with_square(24, 23)) is None

def test_finds_a_square_touching_the_label_edge():
    assert find_black_block(_label_with_square(24, 24, x=0, y=0)) is not None

def test_white_label_and_thin_long_line_are_clean():
    assert find_black_block(Image.new("1", (1218, 812), 1)) is None
    assert find_black_block(_label_with_square(1000, 4)) is None  # 0.5 mm line
```

Plus two render tests in the same file, using a temp copy of `EXAMPLES_ROOT / "positions" / "default"` (`shutil.copytree` into `tmp_path`, build a `TemplatePreset` the way `tests/test_template_renderer.py::_sample_preset` does, and reuse that file's `POSITION_RECORD` dict by importing it):
  - `test_thermal_check_ignores_barcodes`: write a `style.css` into the copy that is the shipped one with `.position-name`'s `background: #000; color: #fff;` removed, then `find_thermal_black_block(preset, [POSITION_RECORD]) is None` (the 136×39 mm barcode alone would fail if it were scanned).
  - `test_thermal_check_catches_the_old_inverted_bar`: copy the preset and append this string constant to its `style.css`: `.position-name { left: 3mm; top: 71mm; width: 144mm; height: 26mm; background: #000; color: #fff; }` (the old inverted bar, frozen so the test survives Task 2). Assert the result is not `None` and `result[0] == 0`.

- [ ] **Step 2: Run them, expect ImportError/FAIL**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_black_area.py -v`

- [ ] **Step 3: Implement** in `app/core/template_renderer.py`:
  - `hide_codes=True` passes `extra_stylesheets=(weasyprint.CSS(string="img { visibility: hidden !important; }"),)` to `writer.write_labels(...)`; default behaviour unchanged.
  - `find_black_block`: the algorithm in spec §1 "Black-area check" (white padding of `size_px` with `ImageOps.expand`, `ImageFilter.MaxFilter(size_px - 1)` for even sizes then the 2×2 `ImageChops.lighter` of four 1-px-offset crops; `MaxFilter(size_px)` alone for odd sizes; `getextrema()[0] == 0` means found; map the first zero pixel back to label coordinates).
  - `find_thermal_black_block`: `render_records(preset, records, hide_codes=True)`, return the first hit as `(index, x, y)`.
  - Docstring on `find_black_block` says why it exists (thermal head residue on solid areas) and that Task 4's builder Save calls `find_thermal_black_block`.

- [ ] **Step 4: Run Task 1 tests, then `tests/test_template_renderer.py`, both PASS**

- [ ] **Step 5: Commit** `feat(core): add thermal black-area check`

---

### Task 2: Thermal-safe `positions/default` and `inventory/default`

**Files:**
- Modify: `app/templates/examples/positions/default/style.css` (`.position-name` block at the end)
- Modify: `app/templates/examples/inventory/default/template.html`, `.../inventory/default/style.css`
- Create: `tests/test_thermal_safe.py`

**Interfaces:**
- Consumes: `find_thermal_black_block(preset, records)` (Task 1), `EXAMPLES_ROOT`, `TemplatePreset`.

- [ ] **Step 1: Write the failing test** `tests/test_thermal_safe.py`:
  - Parametrize over every directory in `EXAMPLES_ROOT / "positions"` and `EXAMPLES_ROOT / "inventory"` that has a `meta.json` (discovered at collection time, ids = `"<mode>/<folder>"`). Build `TemplatePreset` directly from the example folder (name/size from `meta.json`, no `list_presets`, no seeding).
  - Records per mode, two each: realistic (`POSITION_RECORD` / `INVENTORY_RECORD` imported from `tests/test_template_renderer.py`) and short (`{**POSITION_RECORD, "visible_text": "A-1", "user_text": "W"}`; `{**INVENTORY_RECORD, "sku": "W8", "name": "M", "client": "W", "batch": "8", "expiry": "8", "position_code": "H-1"}`).
  - `test_shipped_thermal_preset_has_no_black_block`: `assert find_thermal_black_block(preset, records) is None`, failure message naming the preset folder and the returned `(record, x, y)` converted to mm (`px / 203 * 25.4`).
  - `test_shipped_thermal_css_has_no_black_background`: for the same folders, `"background: #000"` and `"background:#000"` not in `style.css`.

- [ ] **Step 2: Run, expect FAIL** for `positions/default` and `inventory/default`; `inventory/qr-sku-68x38mm` passes.

- [ ] **Step 3: Edit the presets** exactly as spec §1 says:
  - `positions/default`: `.position-name` drops `background`/`color: #fff`, gains `border: 0.5mm solid #000;`, color black; comment says "outlined" instead of "inverted".
  - `inventory/default`: `.chip`/`chip-*` → `.caption`/`caption-*` in both files (same boxes and font sizes, no background, `color: #000`); add one `<div class="caption-rule caption-rule-…">` per caption (6) with `position:absolute; height:0; border-top:0.3mm solid #000;` at the caption's `left`/`width` and `top = caption top + height`; `.divider` becomes `width:0; border-left:0.3mm solid #000;` (drop `width:0.9mm` and the background); `.note-rule` becomes `height:0; border-top:0.3mm solid #000;` (drop background). Update the "inverted bar" CSS comment.
  - Keep the `APP-OWNED FILE` headers.

- [ ] **Step 4: Run** `tests/test_thermal_safe.py` and `tests/test_template_renderer.py` (scan tests included, but **not** together with the font test: use `-k "not test_shipped_default_actually_applies_the_bundled_font"`, then that test alone). All PASS.

- [ ] **Step 5: Save before/after PNGs** for the PR (not in the repo; put them in `/tmp/dr39-png/` and give the path in the task report): render each changed preset with `POSITION_RECORD`/`INVENTORY_RECORD` (`render_records(preset, [record])[0].save(...)`). For "before", write the files from `git show HEAD:<path>` (the commit before your edit) into a temp preset folder and render that. Do not use `git stash`.

- [ ] **Step 6: Commit** `fix(templates): remove solid black fills from thermal presets`

---

### Task 3: Printer validity check

**Files:**
- Modify: `app/core/print_service.py` (`print_labels`, ~:25-56; import `QPrinterInfo`)
- Test: `tests/test_print_service.py`

**Interfaces:**
- Produces: `print_labels(...)` raises `OSError` when the named printer is not installed, the printer is invalid, or `QPainter.begin` fails. Signature unchanged.

- [ ] **Step 1: Write the failing tests:**
  - `test_print_labels_raises_for_a_printer_that_is_not_installed`: `monkeypatch.setattr("app.core.print_service.QPrinterInfo.printerInfo", staticmethod(lambda name: QPrinterInfo()))`; `pytest.raises(OSError, match="not installed")` on `print_labels([img], 150, 100, printer_name="Gone")`.
  - `test_print_labels_raises_when_painting_cannot_start`: monkeypatch `QPainter.begin` (as imported in `app.core.print_service`) to return `False`; with `output_pdf_path=tmp_path / "x.pdf"`, `pytest.raises(OSError)`.
  - Existing PDF tests must keep passing (PDF output path skips the installed-printer check).

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement** per spec §2.1: installed check only when `printer_name` is set and no `output_pdf_path`; message `f"Printer '{printer_name}' is not installed on this PC - check Settings."`; then `if not printer.isValid(): raise OSError(...)`; `painter = QPainter()`, `if not painter.begin(printer): raise OSError(...)`; drawing loop in `try/finally: painter.end()`.

- [ ] **Step 4: Run** `tests/test_print_service.py`, PASS.

- [ ] **Step 5: Commit** `fix(print): refuse an invalid or missing printer`

---

### Task 4: Audit row on failed print + single send loop

**Files:**
- Modify: `app/core/audit_log.py` (`LOG_COLUMNS`, `append_print_log`)
- Modify: `app/core/print_batch.py` (`print_batch`, :67-130)
- Test: `tests/test_audit_log.py`, `tests/test_print_batch.py`

**Interfaces:**
- Produces: `LOG_COLUMNS` ends with `"status"`; `append_print_log(shared_folder, mode, warehouse_prefix, count, description, preset, printer, status: str = "printed") -> None`.

- [ ] **Step 1: Write the failing tests:**
  - `test_audit_log.py::test_append_writes_status_column`: default call → last header cell `status`, row value `printed`; `status="failed"` → `failed`.
  - `test_print_batch.py::test_failure_after_one_of_three_copies_logs_a_failed_row`: fake `send_to_printer` that succeeds once then raises `OSError("jam")` (count calls); `print_batch(["a", "b"], ..., copies=3)` raises `OSError`; exactly one audit file under `<shared>/audit/`, row has `count == "2"` and `status == "failed"`.
  - `test_print_batch.py::test_single_copy_failure_logs_count_zero`: fake always raises → row `count == "0"`, `status == "failed"`, original exception re-raised.
  - `test_print_batch.py::test_failed_audit_write_does_not_mask_the_print_error`: fake send raises `OSError("jam")`; `monkeypatch.setattr("app.core.print_batch.append_print_log", <raises OSError("disk")>)`; `pytest.raises(OSError, match="jam")`.
  - Successful-print tests: assert `status == "printed"` in the existing `test_successful_print_archives_and_logs_with_no_warnings` row check (add the assertion).
  - Read audit rows with `csv.DictReader` over the single file in `audit/`.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement** per spec §2.2: one loop over `targets = [output_pdf_path] if output_pdf_path is not None else [None] * copies`, `sent += len(images)` after each successful send; `except Exception:` → `logger.exception(...)`, try `append_print_log(..., count=sent, status="failed")` catching and logging `OSError`, then `raise`. The archive and success audit path below stay as they are (success passes `status="printed"` explicitly or by default).

- [ ] **Step 4: Run** `tests/test_audit_log.py tests/test_print_batch.py tests/test_settings_window.py`, PASS (the consolidate test in settings_window must still pass).

- [ ] **Step 5: Commit** `fix(print): audit failed prints and merge the send loop`

---

### Task 5: Shared settings never silently reset

**Files:**
- Modify: `app/core/config.py` (`load_settings` :66-93, `sync_shared_settings` :113-124, `save_shared_settings` :127-144)
- Modify: `app/ui/settings_window.py` (`__init__` snapshot; `_save_and_close` :221-243)
- Modify: `app/ui/main_window.py` (:64-65, :125-126, :135-140)
- Modify: `app/ui/csv_import_dialog.py` (:259-268)
- Test: `tests/test_config.py`, `tests/test_settings_window.py`

**Interfaces:**
- Produces:
  - `sync_shared_settings(settings: dict, local_path: Path, on_recovery: Callable[[str], None] | None = None) -> dict`
  - `save_shared_settings(settings: dict, local_path: Path, keys: Iterable[str] = SHARED_SETTINGS_KEYS, on_recovery: Callable[[str], None] | None = None) -> None`
  - Quarantined file name: `<name>.corrupt-<YYYYmmdd-HHMMSS>` (local time).

- [ ] **Step 1: Write the failing tests** (`tests/test_config.py`):
  - Update `test_load_settings_recovers_from_corrupt_json` (:72-80): the kept file is the single match of `tmp_path.glob("settings.json.corrupt-*")`, content `"{not valid json"`.
  - `test_load_settings_never_overwrites_an_earlier_corrupt_copy`: create `settings.json.corrupt-20260101-000000` first, corrupt-load again → both corrupt files exist.
  - `test_sync_keeps_local_values_when_shared_file_is_corrupt`: shared `settings.json` = `"{oops"`; local settings with `warehouses=[{"name": "Main", "prefix": "C001"}]`; `sync_shared_settings(settings, local_path, on_recovery=messages.append)` → warehouses unchanged, `len(messages) == 1`, a `settings.json.corrupt-*` exists in the shared dir, the shared `settings.json` no longer exists.
  - `test_save_shared_settings_seeds_from_settings_when_shared_file_is_corrupt`: shared file `"{oops"`; `save_shared_settings({"shared_folder": ..., "warehouses": W, "csv_mappings": M}, local_path, keys=("warehouses",), on_recovery=messages.append)` → new shared file has **both** `W` and `M`, one message.
  - `test_save_shared_settings_writes_only_the_given_keys`: existing shared file with `warehouses=A, csv_mappings=M1`; call with settings `warehouses=B, csv_mappings=M2`, `keys=("warehouses",)` → file has `B` and `M1`.
  - `test_save_shared_settings_with_no_keys_leaves_the_file_alone`: `keys=()` on an existing file → content byte-identical.
  - Keep `test_save_shared_settings_only_touches_the_keys_it_is_given` and the no-op test passing unchanged (dicts that lack a key leave that key alone).
  - `tests/test_settings_window.py::test_unchanged_warehouses_are_not_written_to_the_shared_file`: shared file has warehouses `A`; open the dialog with settings whose warehouses are `A`, then (simulating another PC) rewrite the shared file with warehouses `B`; trigger `_save_and_close()` without edits → shared file still has `B`. Use the existing fixture style at :27-43.
  - `tests/test_settings_window.py::test_edited_warehouses_are_written_to_the_shared_file`: edit a warehouse in the dialog, save → shared file has the edit.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement** per spec §2.4:
  - `load_settings`: timestamped quarantine name; message unchanged in shape.
  - A private helper `_read_shared(path, on_recovery) -> dict | None` (None = file missing or quarantined) shared by sync and save is fine; don't add more.
  - `sync_shared_settings`: unreadable → keep `settings`'s own shared keys; missing → `save_shared_settings(settings, local_path)` (seed, as today).
  - `save_shared_settings`: base = current shared file, or (missing/unreadable) `{k: settings[k] for k in SHARED_SETTINGS_KEYS if k in settings}` over `_defaults()`; then `base[k] = settings[k]` for `k in keys if k in settings`; skip the write when the file exists and `keys` contributes nothing (keeps the byte-identical test true).
  - `SettingsWindow.__init__`: `self._warehouses_at_open = copy.deepcopy(settings.get("warehouses", []))`. `_save_and_close`: `keys = ("warehouses",) if full_settings["warehouses"] != self._warehouses_at_open else ()`; pass `full_settings`, `keys`, and `on_recovery=lambda m: QMessageBox.warning(self, "Settings problem", m)`.
  - `csv_import_dialog.accept`: `save_shared_settings(self._settings, default_settings_path(), keys=("csv_mappings",))`.
  - `main_window`: `on_recovery=self._warn_settings_recovered` on both `sync_shared_settings` calls and the post-dialog `load_settings`; box title `"Settings problem"`.

- [ ] **Step 4: Run** `tests/test_config.py tests/test_settings_window.py tests/test_main_window.py tests/test_csv_import_dialog.py`, PASS.

- [ ] **Step 5: Commit** `fix(settings): keep a corrupt shared settings file and never write empties`

---

### Task 6: Bare date in the combined Exp/Bat column

**Files:**
- Modify: `app/core/inventory_import.py` (:55-73; add `_split_expiry_batch` and a module-level format tuple; update the comment block)
- Test: `tests/test_inventory_import.py`

**Interfaces:**
- Produces: `_split_expiry_batch(value: str) -> tuple[str, str]` (private; called where `expiry == batch`).

- [ ] **Step 1: Write the failing test** as one parametrized test calling `items_from_csv_rows` the way the existing :128-160 tests do, with expiry and batch both set to the value:

| value | expiry | batch |
|---|---|---|
| `2026/08/02` | `2026/08/02` | `` |
| `02.08.2026` | `02.08.2026` | `` |
| `2026-08-02` | `2026-08-02` | `` |
| `08/2027` | `08/2027` | `` |
| `ABC/123` | `ABC/123` | `` |
| `2027-03/4471` | `2027-03` | `4471` |
| `2026/08/02/LOT9` | `2026/08/02` | `LOT9` |
| `1-Jan` | `1-Jan` | `` |

- [ ] **Step 2: Run, expect FAIL** on the first, fourth and fifth rows.

- [ ] **Step 3: Implement** the three-rule split in spec §2.5 with formats `("%Y/%m/%d", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%Y/%m", "%Y-%m", "%m/%Y", "%m.%Y")` via `datetime.strptime` inside `try/except ValueError`.

- [ ] **Step 4: Run** `tests/test_inventory_import.py`, all PASS (old cases included).

- [ ] **Step 5: Commit** `fix(import): keep a bare date whole in the combined Exp/Bat column`

---

### Task 7: Warehouse snapshot at generation + dead `self.items`

**Files:**
- Modify: `app/ui/mode_positions_panel.py` (`_render_labels` ~:256-290, `print_current_labels` ~:360-382, `__init__` where `generated_codes` is initialised)
- Modify: `app/ui/mode_inventory_panel.py` (:90, :194)
- Test: `tests/test_mode_positions_panel.py`, `tests/test_mode_inventory_panel.py` (:201, :222)

**Interfaces:**
- Produces: `PositionsModePanel._generated_warehouse: str | None`.

- [ ] **Step 1: Write the failing test** `test_print_uses_the_warehouse_from_generation`: settings with two warehouses (`C001`, `C002`); generate with `C001` selected; switch the combo to `C002`; monkeypatch `app.ui.mode_positions_panel.print_batch` to capture kwargs; `print_current_labels()` → captured `warehouse_prefix == "C001"`.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**: set `self._generated_warehouse = warehouse_prefix` with the other `generated_*` fields; use it in `print_current_labels`. Delete `self.items` at both inventory sites; change the two test reads to `panel.checked_items()` (or the table's `rowCount()`, whichever matches what each test means).

- [ ] **Step 4: Run** both panel test files, PASS.

- [ ] **Step 5: Commit** `fix(positions): print with the warehouse the labels were generated for`

---

### Task 8: `ModePanel` base + 2,000-label cap

**Files:**
- Create: `app/ui/mode_panel.py`
- Modify: `app/ui/mode_positions_panel.py` (drop `LARGE_BATCH_THRESHOLD`, `_RENDER_CHUNK_SIZE`, `_ESTIMATED_SECONDS_PER_LABEL`, `refresh_from_settings`, `_warn_no_presets`, `_show_status`, `_on_preset_selected` if identical-but-key, `_render_with_progress`; the class now subclasses `ModePanel`)
- Modify: `app/ui/mode_inventory_panel.py` (same removals; `_on_print_clicked` early cap check; `print_checked_items`)
- Test: `tests/test_mode_positions_panel.py`, `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: `render_records` (unchanged default call).
- Produces, in `app/ui/mode_panel.py`:
  - `MAX_LABELS_PER_RENDER = 2000`, `CONFIRM_LABELS_ABOVE = 300`
  - `def check_label_count(count: int) -> None` — raises `ValueError(f"{count} labels is more than the {MAX_LABELS_PER_RENDER} allowed in one batch - split it into smaller batches.")` when `count > MAX_LABELS_PER_RENDER`.
  - `class ModePanel(QWidget)` with class attributes `MODE: str`, `LARGE_BATCH_TITLE: str`, `CANCELLED: type[Exception]`, and methods `refresh_from_settings(settings)`, `_warn_no_presets(shared_folder)`, `_show_status(message)`, `render_labels(preset, records) -> list[Image.Image]` (check → confirm above 300 → chunked progress render; plain `render_records` at ≤ 300).
  - Positions: `MODE = "positions"`, `LARGE_BATCH_TITLE = "Generate a large batch?"`, `CANCELLED = GenerationCancelled`. Inventory: `"inventory"`, `"Print a large batch?"`, `PrintCancelled`. The question body keeps today's wording; the verb comes from a class attribute `LARGE_BATCH_VERB` (`"Generate"` / `"Print"`) if the two bodies differ.

- [ ] **Step 1: Write the failing tests:**
  - `test_mode_panel` cases inside the positions test file (no new file needed): `check_label_count(2000)` passes, `check_label_count(2001)` raises `ValueError` matching `"2001 labels"`.
  - Positions: generating 2001 codes (e.g. corridor range sized to 2001, or call `_render_labels` with 2001 codes) → `ValueError`, and `render_records` (monkeypatched to count calls) is never called. 300 codes → `QMessageBox.question` (monkeypatched to record) not called; 301 → called once.
  - Inventory: `_on_print_clicked` with 2001 checked items → a warning box (captured via the existing `QMessageBox.warning` monkeypatch style) and `PrintPreviewDialog` is never constructed (monkeypatch it in `app.ui.mode_inventory_panel` to fail the test if called).
  - Update the existing large-batch tests (positions :660 uses 250 codes; inventory :860-895) to exceed 300.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement** `app/ui/mode_panel.py` by moving the existing bodies (positions :155-189 and :292-320 are the source; the QSettings key becomes `f"{self.MODE}/last_template"`, `list_presets(folder, self.MODE)`), then make both panels subclass it, call `self.render_labels(...)` where they called `render_records`/`_render_with_progress`, and add `check_label_count(len(checked))` to `_on_print_clicked` (warning title `"Print failed"`, return) before the preview opens. Positions' existing `ValueError` handlers already show the message.

- [ ] **Step 4: Run** both panel test files and `tests/test_main_window.py`, PASS.

- [ ] **Step 5: Commit** `refactor(ui): share panel render/refresh code and cap batches at 2,000`

---

### Task 9: Full gate

- [ ] **Step 1:** Run the three commands in Global Constraints. All pass, ruff clean.
- [ ] **Step 2:** `grep -rn "background: *#000" app/templates/examples/positions app/templates/examples/inventory` → no output.
- [ ] **Step 3:** If anything was fixed here, commit `chore: fix gate`.
