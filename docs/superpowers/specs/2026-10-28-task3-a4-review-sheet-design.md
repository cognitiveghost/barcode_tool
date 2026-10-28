# Task 3: A4 review sheet (by position / by SKU, column picker, compact)

Date: 2026-10-28. Refines **Task 3** of
`docs/superpowers/specs/2026-10-28-thermal-templates-builder-updates-design.md` (the parent spec;
its goals, owner decisions and constraints still apply). Classification: **bounded**. Each decision
here is marked **(owner)** (from the parent spec or the approval round) or **(Claude's call)**.

## Why

The A4 inventory export fits ~10 rows a page (20 mm QRs, 2.5 mm cell padding, black header)
and has one fixed layout. The sheet is used next to a scanner in the office: you find a position
or a SKU on paper and scan its code when the real item or shelf label can't be scanned. **(owner)**

## What exists today (verified)

- `InventoryModePanel._on_export_table_clicked` (`app/ui/mode_inventory_panel.py:338`) builds one
  record per checked row with `_record_for_item` (fields `sku, name, client, batch, expiry,
  position_code, position_data, generated_date, quantity` — quantity is a **str**) and renders
  `list_presets(shared, "inventory-table")[0]` with `render_table_pdf(preset, records)`.
- `render_table_pdf` (`app/core/template_renderer.py:211`) renders the Jinja template with
  `records` and `label_tools`, then WeasyPrint → native vector PDF.
- The shipped preset `app/templates/examples/inventory-table/a4-table/` groups by SKU and merges
  duplicate (SKU, position) rows **inside Jinja** (`groupby`, rowspans).
- There is no template picker for table presets and no column choice.
- Remembered UI state uses `qsettings()` (`app/core/config.py:178`), e.g. `mode_panel.py:48` stores
  `<mode>/last_template` by preset name and falls back when the name is gone.

## Goals

1. Two views, picked at export: **By position** (sorted by position, its SKUs in the rows) and
   **By SKU** (sorted by SKU, its positions in the rows). **(owner)**
2. A column picker; any column can be hidden, Qty and both QRs included. **(owner)** The choice is
   remembered per view on this PC. **(Claude's call, parent spec)**
3. 12 mm QRs, both kept (SKU QR and Position QR). **(owner)**
4. Density: **≥ 18 rows per page with QRs, ≥ 35 without**, whatever the grouping (a warehouse
   where most positions hold one SKU must still hit it). **(Claude's call, parent spec)**
5. Findable: page `x of y` and the export date in the footer, table header repeated per page,
   groups visually obvious. **(Claude's call, parent spec)**

## Non-goals

- No two-column layout (the parent spec left it optional; 20 rows/page already beats the target).
- No change to the thermal label pipeline, `render_records`, or the Print button.
- No new dependency.

## Design

### Grouping layout (changes one parent-spec call; owner picked B)

The parent spec said "a group header row per position/SKU". The prototype render (two sample pages
sent with the approval round) measured it:

| Layout | QR rows/page, 3 SKUs per position | QR rows/page, 1 SKU per position | no-QR rows/page |
|---|---|---|---|
| A. group header row (parent spec) | 18 | **14** | 26–39 |
| B. key on every row, group start = heavy rule (recommended) | 20 | 20 | 54 |

Layout A misses the target whenever groups are small, because every 1-row group pays a ~5 mm header.
**Layout B (owner, approval round):** the group key (position in *By position*, SKU in
*By SKU*) is a fixed first column on every row. On a group's first row it is bold, with a small
second line `3 rows · qty 12` when the group has more than one row (`· qty` only when the Qty
column is shown). On the following rows it is grey. A group starts with a 0.4 mm black rule, and
groups alternate white / light grey (`#eee`) — that is the zebra, per group rather than per row.
Because every row carries its own key and codes, a group may break across a page; only single rows
are kept whole (`tr { break-inside: avoid }`), no `tbody` avoid, so pages fill to the bottom.

Layout A is rejected; do not build group header rows.

### Columns

One ordered column list (key → header label), defined once in Python:

`num "#"`, `sku "SKU"`, `position "Position"`, `name "Name"`, `client "Client"`, `batch "Batch"`,
`expiry "Expiry"`, `qty "Qty"`, `sku_qr "SKU QR"`, `position_qr "Position QR"`.

- The picker for a view offers every column **except that view's key** (the key is the fixed first
  column): *By position* offers `#, SKU, Name, Client, Batch, Expiry, Qty, SKU QR, Position QR`
  (exactly the owner's list); *By SKU* offers the same with `Position` in place of `SKU`.
  **(Claude's call)**
- Defaults on first use: all offered columns on. At least one must be on (OK disabled otherwise).
- Hiding Qty also hides the qty in the group summary — a blind count must not leak the number.
  **(Claude's call)**
- `#` is a running row number 1…N over the whole sheet, after sorting. **(Claude's call)**
- Column order on paper is the list order above, not click order.

### Data shaping (Python, so the template stays a dumb loop) **(owner, parent spec)**

New pure module `app/core/review_sheet.py`, no Qt:

- `SHEET_COLUMNS: dict[str, str]` (above), `VIEWS = {"position": "By position", "sku": "By SKU"}`,
  `VIEW_KEY = {"position": "position", "sku": "sku"}`.
- `pickable_columns(view) -> list[str]`: `SHEET_COLUMNS` keys minus `VIEW_KEY[view]`.
- `build_sheet(records, view, columns) -> dict` returns the template context:
  - `view`, `view_label` ("By position"), `key_label` ("Position" / "SKU"), `generated_date`
    (from the first record, `""` when empty);
  - `columns`: `[{"key", "label"}]` for the requested keys that are pickable for the view, in
    `SHEET_COLUMNS` order (unknown keys dropped; `None` means all pickable);
  - `groups`: `[{"key", "summary", "rows"}]`.
- **Merging:** records identical on `(sku, position_code, client, batch, expiry)` become one row with
  `qty` = the int sum; `name` and `position_data` from the first. Rows that differ in batch, expiry or
  client stay separate. **(Claude's call — today's sheet merges on SKU + position only, which would
  hide a second batch now that Batch is a column.)**
- **Sorting:** natural order (digit runs compared as numbers, case-insensitive) on
  position view `(position_code, sku, batch, expiry)`, SKU view `(sku, position_code, batch, expiry)`.
  Groups are consecutive runs of the same key in that order.
- **Row dict:** `num, sku, position (= position_code), position_data, name, client, batch, expiry, qty`.
- **summary:** `""` for a 1-row group; else `"{n} rows · qty {total}"`, or `"{n} rows"` when `qty`
  is not among the columns.

### Rendering

- `render_table_pdf(preset, records, view="position", columns=None)` renders the template with
  `**build_sheet(records, view, columns)`, plus `records=records` (so a user's copy of the old
  `a4-table` keeps rendering) and `label_tools`. Still a native vector PDF. **(owner, parent spec)**
- The shipped preset keeps the folder name **`inventory-table/a4-table`** (app-owned, rewritten on
  launch, so existing shared folders get the new files and no stale folder is left behind);
  `meta.json` name becomes **"A4 review sheet"**. **(Claude's call)**
- Template: `<h1>` = `Inventory review · {{ view_label }} · {{ generated_date }}`; `thead` = key
  column + chosen columns; one `<tbody>` per group; a cell is `<img>` of
  `label_tools.qr_code(row.sku)` / `qr_code(row.position_data)` for the QR columns, else
  `{{ row[col.key] }}`.
- CSS (measured in the prototype, 20 QR rows / 54 text rows on a page):
  - `@page { size: A4; margin: 8mm 8mm 10mm 8mm; }` with `@bottom-left { content: string(title) }`
    and `@bottom-right { content: "Page " counter(page) " of " counter(pages) }`, 2.6 mm text;
    `h1 { font-size: 3.6mm; string-set: title content(); }`.
  - `table { width: 100%; border-collapse: collapse; font-size: 2.8mm }`,
    `thead { display: table-header-group }`, `th, td { padding: 0.4mm 1mm; border-bottom: 0.15mm solid #999 }`,
    `th` 2.5 mm uppercase with a 0.3 mm black bottom rule — **no black header fill** (toner).
  - QR cells `width: 13mm; padding: 0.3mm`, `img { width: 12mm; height: 12mm; display: block }`.
  - `#` and Qty right-aligned, 10 mm.
- Long text (names) wraps; it only makes that row taller.

### Export dialog

New `app/ui/export_sheet_dialog.py`, `ExportSheetDialog(QDialog)`, opened by the existing
"Export table (PDF)..." button after its current checks and before the save-file dialog:

- **Template** combo: the `inventory-table` presets by name. Remembered as
  `inventory-table/last_template`; if that name no longer exists, select "A4 review sheet", else the
  first. **(Claude's call, parent spec)**
- **View**: two radio buttons, *By position* / *By SKU*; last view remembered as
  `inventory-table/view` (default `position`).
- **Columns**: one checkbox per `SHEET_COLUMNS` key; the current view's key checkbox is hidden.
  Switching view swaps in that view's remembered set. Stored per view as
  `inventory-table/columns/<view>`, a comma-joined string (QSettings turns one-item lists into a
  plain string on some backends, so do not store a list). Unknown stored keys are ignored.
- OK / Cancel. OK is disabled when no visible column is checked. Settings are written on OK only.
- A module function `ask_export_options(parent, presets) -> tuple[TemplatePreset, str, list[str]] | None`
  wraps the dialog, so panel tests monkeypatch it the way they patch `QFileDialog.getSaveFileName`.

Panel flow becomes: checks (rows, warehouse, presets) → `ask_export_options` (None → stop) →
save dialog → `render_table_pdf(preset, records, view=view, columns=columns)`.

### Docs

`app/templates/examples/README.txt`, section "Inventory table reports (A4)": the template now gets
`view, view_label, key_label, generated_date, columns, groups` (and still `records`); describe the
row fields and point at the shipped "a4-table" preset.

## Testing

- `tests/test_review_sheet.py` (pure, fast): merge rule (same batch merges and sums, other batch
  stays), natural sort in both views, grouping, running `#`, column filtering/order/unknown keys and
  the view key never offered, summary with and without qty.
- `tests/test_template_renderer.py`: update the two `a4-table` tests (preset name, merge assertion
  per the new rule); QR decode at 300 dpi still finds every SKU and position payload; **density**:
  60 records, 1 SKU per position, all columns → page 1 holds ≥ 18 rows; QR columns off → ≥ 35.
  Count rows from page-1 text (pdfium text page), as the prototype did.
- `tests/test_export_sheet_dialog.py`: defaults, per-view memory round-trip through `qsettings()`,
  view key hidden, OK disabled with nothing checked, template fallback when the remembered name is gone.
  Isolate `qsettings()` per test as `tests/test_main_window.py:40` does: a throwaway
  `QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat)` monkeypatched onto
  `app.ui.export_sheet_dialog.qsettings`.
- `tests/test_mode_inventory_panel.py`: existing export tests patch `ask_export_options` and accept
  the new `render_table_pdf` kwargs; one new test checks view and columns reach the renderer and
  that Cancel in the dialog renders nothing.
- Run as CI does (split, `QT_QPA_PLATFORM=offscreen`); the single-process suite segfaults late.

## Left to the builder

Widget layout of the dialog, exact grey values, the wording of the summary line, test helper names.
