# A4 Review Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the A4 inventory export with a compact review sheet: two views (by position / by SKU), a per-view remembered column picker, 12 mm QRs, ≥ 18 QR rows / ≥ 35 text rows per page.

**Architecture:** A pure module `app/core/review_sheet.py` sorts, merges and groups records into a template context. `render_table_pdf` passes that context to the Jinja preset `inventory-table/a4-table` (rewritten). A new `ExportSheetDialog` picks template, view and columns before the save dialog.

**Tech Stack:** Python 3, PySide6, Jinja2, WeasyPrint (via blabel), pypdfium2 + zxingcpp in tests.

**Spec:** `docs/superpowers/specs/2026-10-28-task3-a4-review-sheet-design.md` (read it first; layout **B** is the owner's pick: group key on every row, no group header rows).

## Global Constraints

- Always run tests with `QT_QPA_PLATFORM=offscreen`, one test file at a time: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/<file> -v`. The single-process full suite segfaults late (WeasyPrint/Pango); that is known, not your bug.
- No new dependency. No change to `render_records`, the thermal templates, or the Print button.
- Stays a native vector PDF (no rasterising in `render_table_pdf`).
- QR images are exactly `width: 12mm; height: 12mm`.
- No black-filled table header (`th` has no background).
- Template files keep the `APP-OWNED FILE` comment at the top (copy it from the current files).
- Column keys and labels, exactly: `num "#"`, `sku "SKU"`, `position "Position"`, `name "Name"`, `client "Client"`, `batch "Batch"`, `expiry "Expiry"`, `qty "Qty"`, `sku_qr "SKU QR"`, `position_qr "Position QR"`.
- View ids `"position"`, `"sku"`; labels `"By position"`, `"By SKU"`.
- QSettings keys: `inventory-table/last_template`, `inventory-table/view`, `inventory-table/columns/<view>` (comma-joined string, never a list).

## Review Focus

1. Blank optional fields: `client`, `batch`, `expiry` are often `""`. Two rows that differ only in qty must merge even with all three blank. Test in Task 1.
2. Mixed-case and numeric-run sorting: `H-9-A` before `H-10-A`, `sku-b` between `SKU-A` and `SKU-C`. Test in Task 1.
3. A user's copy of the old `a4-table` (uses `records` only) must still render after the context change. Test in Task 2.
4. Garbage in QSettings (an unknown view id, unknown column keys, an empty string) falls back to defaults and doesn't crash. Test in Task 3.
5. Cancel in the new dialog renders and writes nothing. Test in Task 4.

---

### Task 1: `review_sheet` data shaping

**Files:**
- Create: `app/core/review_sheet.py`
- Test: `tests/test_review_sheet.py` (create)

**Interfaces:**
- Produces:
  - `SHEET_COLUMNS: dict[str, str]` (ordered, keys/labels from Global Constraints)
  - `VIEWS: dict[str, str] = {"position": "By position", "sku": "By SKU"}`
  - `VIEW_KEY: dict[str, str] = {"position": "position", "sku": "sku"}`
  - `pickable_columns(view: str) -> list[str]`: `SHEET_COLUMNS` keys in order, minus `VIEW_KEY[view]`
  - `build_sheet(records: list[dict], view: str, columns: list[str] | None) -> dict` with keys `view, view_label, key_label, generated_date, columns, groups`
    - `columns`: `[{"key": k, "label": SHEET_COLUMNS[k]}]`, the requested keys that are in `pickable_columns(view)`, in `SHEET_COLUMNS` order; `None` = all pickable
    - `key_label`: `SHEET_COLUMNS[VIEW_KEY[view]]` ("Position" / "SKU")
    - `generated_date`: `records[0]["generated_date"]`, `""` when there are no records
    - `groups`: `[{"key": str, "summary": str, "rows": [row]}]`, where row = `{num, sku, position, position_data, name, client, batch, expiry, qty}` (`qty` int, `position` = the record's `position_code`, `num` = running 1..N over the whole sheet)
  - Input records are the dicts from `_record_for_item` (`app/ui/mode_inventory_panel.py:68`). `quantity` is a **str**.

- [ ] **Step 1: Write the failing tests** in `tests/test_review_sheet.py`. Use a helper `rec(sku, pos, qty="1", batch="", expiry="", client="", name="N")` that returns a record dict with `position_data=f"C001{pos}"` and `generated_date="2026/10/28"`. Tests:
  - `test_identical_rows_merge_and_sum_qty`: two `rec("A","H-001-A","3")` + `rec("A","H-001-A","4")` → one row, `qty == 7` (covers Review Focus 1: all optional fields blank).
  - `test_rows_with_different_batch_stay_separate`: same SKU/pos, batch `"B1"` vs `"B2"` → 2 rows.
  - `test_position_view_sorts_naturally_and_groups_by_position`: positions `H-10-A`, `H-9-A`, `H-9-A` (different SKUs `B`, `A`) → group keys `["H-9-A", "H-10-A"]`, first group's row skus `["A", "B"]`.
  - `test_sku_view_sorts_case_insensitively_and_groups_by_sku`: skus `SKU-C`, `sku-b`, `SKU-A` → group keys `["SKU-A", "sku-b", "SKU-C"]`.
  - `test_num_runs_across_groups`: 3 rows in 2 groups → nums `[1, 2, 3]` in output order.
  - `test_columns_follow_sheet_order_and_drop_unknown_and_view_key`: `build_sheet(recs, "position", ["qty", "sku", "bogus", "position", "num"])["columns"]` keys == `["num", "sku", "qty"]`.
  - `test_none_columns_means_all_pickable`: keys == `pickable_columns(view)` for both views; `"sku" not in pickable_columns("sku")`, `"position" not in pickable_columns("position")`.
  - `test_summary`: a 1-row group → `""`; a 3-row group with qty 1+2+3 and `qty` in columns → `"3 rows · qty 6"`; same without `qty` → `"3 rows"`.
  - `test_empty_records`: `build_sheet([], "position", None)` → `groups == []`, `generated_date == ""`.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_review_sheet.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement `app/core/review_sheet.py`.** Merge key `(sku, position_code, client, batch, expiry)` in a dict that keeps the first-seen order, summing `int(quantity)`. Natural sort key per field: `[int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", value)]`. Sort tuple: position view `(position, sku, batch, expiry)`, SKU view `(sku, position, batch, expiry)`. Then `itertools.groupby` on the view key's **raw value** (so `SKU-A` and `sku-a` stay two groups), assign `num`, build summaries. A short module docstring; no Qt imports.

- [ ] **Step 4: Run** the same command. Expected: all PASS.

- [ ] **Step 5: Commit** `git add app/core/review_sheet.py tests/test_review_sheet.py && git commit -m "feat: review sheet sorting, merging and grouping"`

---

### Task 2: Renderer + new shipped `a4-table` preset

**Files:**
- Modify: `app/core/template_renderer.py:211-223` (`render_table_pdf`)
- Rewrite: `app/templates/examples/inventory-table/a4-table/template.html`, `style.css`, `meta.json`
- Modify: `app/templates/examples/README.txt` (section "Inventory table reports (A4)", ~line 66)
- Test: `tests/test_template_renderer.py` (tests at ~360-430)

**Interfaces:**
- Consumes: `build_sheet`, `pickable_columns` from Task 1.
- Produces: `render_table_pdf(preset: TemplatePreset, records: list[dict], view: str = "position", columns: list[str] | None = None) -> bytes`. The template context is `**build_sheet(records, view, columns)` plus `records=records` and `label_tools=label_tools`.
- `meta.json`: `{"name": "A4 review sheet", "width_mm": 210, "height_mm": 297}`.

- [ ] **Step 1: Update and add tests** in `tests/test_template_renderer.py`:
  - Add a module helper `_a4_preset()` that returns the `TemplatePreset` the two existing tests build, with `name="A4 review sheet"`, and use it in both.
  - `test_list_presets_seeds_inventory_table_examples_too`: expect `["A4 review sheet"]`.
  - `test_render_table_pdf_puts_every_record_on_one_native_pdf`: unchanged assertions (1 page, zxing decodes `SKU-A, SKU-B, C001AAA, C001BBB` at 300 dpi), default view and columns.
  - Rewrite `test_render_table_pdf_merges_duplicate_sku_position_rows_and_totals_quantity` for the new rule: keep its 4 records (all with the same batch from `INVENTORY_RECORD`), render `view="sku"`, and assert from the page-1 text (`pdf[0].get_textpage().get_text_range()`) that `"3 rows" not in text`, `"2 rows · qty 12" in text` (SKU-100: 3+4 merged = 7, plus 5) and that `"H-011-A"` appears exactly once. Pick quantities so no digit string collides by chance, as the existing comment warns.
  - `test_render_table_pdf_density_with_qr_codes`: 60 records, one SKU per position (`sku=f"SKU-{i:03d}"`, `position_code=f"H-{i:03d}-A"`, `position_data=f"C001H{i:03d}A"`), all columns. Assert `text.count("SKU-") >= 18` on page 1 (the template must not print the SKU anywhere else on a page, e.g. not in the footer).
  - `test_render_table_pdf_density_without_qr_codes`: same records, `columns=["num","sku","name","client","batch","expiry","qty"]` → `text.count("SKU-") >= 35` on page 1.
  - `test_render_table_pdf_footer_has_page_x_of_y`: the 60-record QR render → page-1 text contains `"Page 1 of "` and `"2026/08/02"` (`INVENTORY_RECORD`'s date).
  - `test_render_table_pdf_hidden_qty_leaves_no_totals` : render `view="position"`, records with two SKUs in one position, `columns=["sku","name"]` → `"qty" not in text.lower()`.
  - `test_render_table_pdf_still_renders_an_old_records_only_template(tmp_path)` (Review Focus 3): write a `template.html` containing `{% for r in records %}<p>{{ r.sku }}</p>{% endfor %}` and an empty `style.css` (except `@page { size: A4; }`) in tmp_path → output PDF text contains both SKUs.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_template_renderer.py -v -k "table or inventory_table"`. Expected: the new/changed tests FAIL.

- [ ] **Step 3: Change `render_table_pdf`** to the signature above. Update its docstring: whole list at once, context from `build_sheet`, `records` kept for older copies of the preset.

- [ ] **Step 4: Write the template, CSS and meta.** The spec's "Rendering" section fixes the structure and every CSS value. In short:
  - `<h1>Inventory review · {{ view_label }} · {{ generated_date }}</h1>`.
  - `thead`: `<th class="c-key">{{ key_label }}</th>` + one `<th class="c-{{ c.key }}">` per column.
  - One `<tbody>` per group. Each row is `<tr class="first">` on the group's first row, else `<tr>`. The key cell `<td class="c-key">` shows `{{ group.key }}`; on the first row it adds `{% if group.summary %}<br><small>{{ group.summary }}</small>{% endif %}`. Then per column: `sku_qr` → `<img src="{{ label_tools.qr_code(row.sku) }}">`, `position_qr` → `qr_code(row.position_data)`, else `{{ row[c.key] }}`.
  - CSS from the spec, plus layout B: `tr.first td { border-top: 0.4mm solid #000; }`, `td.c-key { font-weight: 700; }`, `tr:not(.first) td.c-key { color: #888; font-weight: 400; }`, `tbody:nth-child(even) tr { background: #eee; }`, `small { font-size: 2.3mm; font-weight: 400; }`, `tr { break-inside: avoid; }`, and **no** `tbody` break rule. Keep the `"JetBrains Mono", monospace` font family.
  - Reference values (prototype, 8/8/10/8 mm margins, 2.8 mm text, 0.4 mm/1 mm padding): 20 QR rows and 54 text rows per page.

- [ ] **Step 5: Update `README.txt`.** Rewrite the "Inventory table reports (A4)" paragraph: rendered once per export; the context is `view`, `view_label`, `key_label`, `generated_date`, `columns` (list of `key`/`label`), `groups` (each with `key`, `summary`, `rows`; row fields `num, sku, position, position_data, name, client, batch, expiry, qty`), plus the raw `records` for older templates. Sorting, merging and grouping happen in the app. See the shipped "a4-table" preset ("A4 review sheet").

- [ ] **Step 6: Run** the Step 2 command, then the whole file: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_template_renderer.py -v`. Expected: all PASS. If a density test fails, adjust only padding, font sizes or margins, and keep the QR at 12 mm.

- [ ] **Step 7: Commit** `git add -A app/core/template_renderer.py app/templates/examples tests/test_template_renderer.py && git commit -m "feat: compact A4 review sheet preset with views and column choice"`

---

### Task 3: Export dialog

**Files:**
- Create: `app/ui/export_sheet_dialog.py`
- Test: `tests/test_export_sheet_dialog.py` (create)

**Interfaces:**
- Consumes: `SHEET_COLUMNS`, `VIEWS`, `VIEW_KEY`, `pickable_columns` (Task 1); `TemplatePreset` (`app/core/template_renderer.py`); `qsettings` (`app/core/config.py:178`, import it into this module as `from app.core.config import qsettings` so tests can patch `app.ui.export_sheet_dialog.qsettings`).
- Produces:
  - `SHIPPED_TABLE_PRESET = "A4 review sheet"`
  - `class ExportSheetDialog(QDialog)`: `__init__(self, presets: list[TemplatePreset], parent=None)`. Attributes the tests use: `template_combo: QComboBox` (item text = preset name, data = preset), `view_buttons: dict[str, QRadioButton]` (keyed by view id), `column_boxes: dict[str, QCheckBox]` (keyed by every `SHEET_COLUMNS` key), `ok_button: QPushButton` (from a `QDialogButtonBox`). Method `options(self) -> tuple[TemplatePreset, str, list[str]]`: the selected preset, view, and checked visible column keys in `SHEET_COLUMNS` order.
  - `ask_export_options(parent, presets: list[TemplatePreset]) -> tuple[TemplatePreset, str, list[str]] | None`: shows the dialog modally; returns `options()` on accept, `None` on cancel.

- [ ] **Step 1: Write the failing tests.** Add an autouse fixture that monkeypatches `app.ui.export_sheet_dialog.qsettings` to `lambda: store`, where `store = QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat)`, same as `tests/test_main_window.py:40`. Also add `_app()` as in `tests/test_mode_inventory_panel.py:24`. Build presets with `TemplatePreset(name=..., mode="inventory-table", width_mm=210, height_mm=297, template_path=Path("t"), stylesheet_path=Path("s"))`. Tests:
  - `test_defaults_position_view_all_columns`: fresh store → `options()[1] == "position"`, `options()[2] == pickable_columns("position")`; `column_boxes["position"].isHidden()`.
  - `test_switching_view_hides_that_views_key`: click `view_buttons["sku"]` → `column_boxes["sku"].isHidden()` and `not column_boxes["position"].isHidden()`; `options()[2] == pickable_columns("sku")`.
  - `test_columns_are_remembered_per_view`: uncheck `qty` in position view, check `sku` view, uncheck `name`, `accept()`. A new dialog opens in `sku` with `name` unchecked; switch to `position` and `qty` is unchecked there too.
  - `test_nothing_written_on_cancel`: change something, `reject()` → `store.allKeys() == []`.
  - `test_ok_disabled_when_no_column_checked`: uncheck every visible box → `not ok_button.isEnabled()`; check one → enabled.
  - `test_template_falls_back_to_shipped_when_remembered_is_gone`: presets `["Custom", "A4 review sheet"]`, store `inventory-table/last_template = "Deleted"` → `template_combo.currentText() == "A4 review sheet"`; remembered `"Custom"` → `"Custom"`.
  - `test_garbage_settings_fall_back_to_defaults` (Review Focus 4): store `view="bogus"`, `columns/position="bogus,,qty"` → view `"position"`, columns `["qty"]`; store `columns/position=""` → all pickable.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_export_sheet_dialog.py -v`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement the dialog.** The window title is "Export A4 review sheet". Use a `QFormLayout` with Template (combo), View (two radios in a row) and Columns (checkboxes in a `QGridLayout`, 2 columns), then the OK/Cancel button box. Keep a `dict[view, set[str]]` of the checked columns, loaded from settings at construction. On a view toggle, save the visible boxes into the old view's set, load the new view's, and hide `VIEW_KEY[view]`'s box. A stored column string parses as `[k for k in s.split(",") if k in pickable_columns(view)]`; an empty result means all pickable. Save all four keys on accept only (override `accept()`).

- [ ] **Step 4: Run** the same command. Expected: all PASS.

- [ ] **Step 5: Commit** `git add app/ui/export_sheet_dialog.py tests/test_export_sheet_dialog.py && git commit -m "feat: export dialog with view and per-view column picker"`

---

### Task 4: Wire the dialog into the inventory panel

**Files:**
- Modify: `app/ui/mode_inventory_panel.py:338-375` (`_on_export_table_clicked`) and its imports
- Test: `tests/test_mode_inventory_panel.py` (export tests at ~770-860)

**Interfaces:**
- Consumes: `ask_export_options` (Task 3), `render_table_pdf(preset, records, view=..., columns=...)` (Task 2).

- [ ] **Step 1: Update and add tests.**
  - A real modal dialog would hang the test run. Add an **autouse** fixture to the file that monkeypatches `app.ui.mode_inventory_panel.ask_export_options` to `lambda parent, presets: (presets[0], "position", ["sku"])`; individual tests override it. Change the existing `render_table_pdf` lambdas to `lambda preset, records, **kw: ...`.
  - `test_export_table_passes_view_and_columns_to_renderer`: patched dialog returns `(presets[0], "sku", ["position", "qty"])` → the recorded kwargs are `{"view": "sku", "columns": ["position", "qty"]}`.
  - `test_export_table_cancel_in_dialog_renders_nothing` (Review Focus 5): dialog returns `None` → `getSaveFileName` is never called (patch it to record calls), the renderer is never called, and no file is written.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_mode_inventory_panel.py -v -k export`. Expected: the new tests FAIL.

- [ ] **Step 3: Edit `_on_export_table_clicked`.** After the existing "no presets" check and before `QFileDialog.getSaveFileName`, call `ask_export_options(self, table_presets)` and return on `None`. Render with `render_table_pdf(preset, records, view=view, columns=columns)`, using the preset the dialog returned instead of `table_presets[0]`. Leave everything else in the method alone.

- [ ] **Step 4: Run** the Step 2 command, then `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_mode_inventory_panel.py -v`. Expected: all PASS.

- [ ] **Step 5: Final check.** Run each changed test file on its own: `test_review_sheet.py`, `test_template_renderer.py`, `test_export_sheet_dialog.py`, `test_mode_inventory_panel.py`. Then run the CI split from `.github/workflows/ci.yml`: `pytest -v -k "not test_shipped_default_actually_applies_the_bundled_font"` and `pytest -v -k test_shipped_default_actually_applies_the_bundled_font`. Expected: all PASS.

- [ ] **Step 6: Commit** `git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py && git commit -m "feat: pick view and columns before exporting the A4 sheet"`
