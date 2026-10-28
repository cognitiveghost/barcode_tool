# Barcode Tool: thermal-safe templates, template builder, A4 review sheet, releases + updater

Date: 2026-10-28. Brainstormed with the owner; each decision is marked **(owner)** or **(Claude's call)**.

## Why

- Labels with solid black areas leave burnt residue on the head of the warehouse's
  Citizen CL-E300 (203 dpi), which then has to be cleaned. **(owner)** Every shipped label
  template has large fills today: the inverted position bar in `positions/default`
  (144×26 mm), seven black caption chips plus two 0.9 mm dividers in `inventory/default`.
- New label kinds keep coming up (product barcode labels, pallet labels, other sizes).
  The owner wants to make them inside the app instead of hand-writing HTML/CSS. **(owner)**
- The A4 inventory export wastes paper (about 10 rows per page because of 20 mm QRs)
  and is hard to find your way around. **(owner)**
- The app has no version and no updater. Releases are cut by hand-pushing a tag. The owner
  wants the same release button + in-app update flow as Fulfilment and Packer. **(owner)**
- The code review found a handful of real bugs (listed in Task 1).

## Goals

1. No solid fills on any thermal label, shipped or user-made.
2. A drag-on-canvas template builder that saves reusable presets for any label size.
3. A compact, configurable A4 review sheet meant to be used next to a scanner.
4. One-click releases and in-app updates (Windows).
5. The verified bugs fixed.

## Non-goals / anti-goals

- No Linux build any more: all warehouse PCs are Windows. **(owner)**
- No translation/BG localisation (not asked for).
- No full `shared/` sync from Fulfilment (its `shared/` holds theme, web tier and navrail, which
  this app does not use). **(Claude's call)**
- Anti-goal: a builder that lets someone reintroduce a black block. The builder has **no fill
  option at all**.
- Anti-goal: over-planned work. The owner asked for **few, dense tasks**. **(owner)**

## Constraints

- Rendering pipeline stays as is: Jinja HTML/CSS → blabel/WeasyPrint PDF → pdfium raster at
  203 dpi → threshold to 1-bit (`app/core/template_renderer.py:131-154`). The builder's preview
  uses this same render, so what you see is what the head prints.
- Presets live in `<shared folder>/templates/<mode>/<preset>/` (`template.html`, `style.css`,
  `meta.json`). App-owned folders are rewritten on every launch (`templates/examples/README.txt`).
- Tests: WeasyPrint/Pango segfaults late in a single-process run. Keep the split CI run
  (`.github/workflows/ci.yml`) and run with `QT_QPA_PLATFORM=offscreen`.
- The repo is public, so the updater's unauthenticated GitHub API call works.

---

## Task 1: Stop the head damage, plus stabilisation

### Thermal-safe shipped templates
Rule for every thermal preset: no `background:#000` areas and no solid bars thicker than 0.5 mm.
Emphasis comes only from size, weight and outlines (0.3–0.5 mm). Barcodes and QRs are the
only dense black.
- `positions/default`: the position code stays the largest element, black text on white
  inside a 0.5 mm outline. The inverted bar goes.
- `inventory/default`: the chips become small bold uppercase captions with a 0.3 mm underline
  or outline. The dividers become 0.3 mm rules.
- `qr-sku-68x38mm`: already clean, no change.
- Design the new layouts **using only what Task 4's builder model can express** (absolute-mm
  text with bold/uppercase/size/align, Code128, QR, outline boxes, 0.3–0.5 mm lines), because
  Task 4 regenerates these same presets from `layout.json`. Draw an underline as a `line`
  element, not as CSS text decoration. **(Claude's call)**
- `inventory-table/a4-table` is rendered for an office printer, so it is out of scope here (Task 3 redoes it).
- Add a test that renders each shipped thermal preset with sample data and fails if any
  ≥ 3×3 mm block (24×24 dots at 203 dpi) is fully black, ignoring barcode/QR images.
  How to detect that is the builder's choice (for example, render with the code `<img>`s blanked
  and scan the bitmap). Put the check in `app/core` as a plain function (not a test helper)
  because Task 4's Save calls it too. This guards Tasks 1 and 4.

### Bug fixes (verified against the code)
- `app/core/print_service.py:48`: check `printer.isValid()` and `painter.begin()`/`isActive()`.
  Raise on failure so a wrong printer is never logged as printed.
- `app/core/print_batch.py:87-119`: when printing fails midway, still write an audit row for
  what was sent, flagged as partial/failed.
- `app/ui/mode_positions_panel.py:367`: take the warehouse from when the labels were generated,
  not the combo box at print time.
- `app/core/config.py:117-120` + `app/ui/settings_window.py:233-237`: a corrupt shared
  `settings.json` must not be silently reset. Show an error and keep the file (rename it to
  `.corrupt-<timestamp>`). Saving shared keys should re-read the shared file and write only the
  keys this dialog changed, so an edit from another PC isn't lost. "Changed" means different
  from a snapshot taken when the dialog opened. If both PCs changed the same key, last write wins:
  only one or two admins edit settings. **(Claude's call)**
- `app/core/inventory_import.py:68-70`: in the combined Exp/Bat column, a value that is
  only a full date (`2026/08/02`, `02.08.2026`, ISO) is all expiry, not split into expiry + batch.
  Split on the last `/` only when the left side is a valid date and the right side is not.
- Batch size: one cap on the total labels per render (records × copies-per-record), in both
  modes, at 2,000, with a clear message. Above 300, ask for confirmation first. **(Claude's call;
  both numbers are constants that are easy to tune)**
- Tidy: merge the duplicated `_render_with_progress` and `refresh_from_settings` between the
  two mode panels, merge the duplicated `send_to_printer` call in `print_batch.py:71-86`,
  and remove dead `self.items` (`mode_inventory_panel.py:90,194`).

## Task 2: Release button + in-app updater (Windows only)

Copy the Fulfilment/Packer pattern, scaled down.
- **Release workflow:** `workflow_dispatch` on `main` with a `bump` input (patch/minor/major).
  `scripts/release_version.py` (copy from `shopify-fulfillment-tool/scripts/release_version.py`)
  computes the next tag and stamps `app/__init__.py`'s `__version__ = "dev"`. The workflow runs
  the split test suite, does the Windows PyInstaller `--onedir` build, writes
  `BarcodeTool-<ver>.zip` + `.sha256`, then `gh release create`. Reference:
  `shopify-fulfillment-tool/.github/workflows/build_release.yml`.
- Remove the Linux build and the `release: published` trigger from `release.yml`, and rewrite
  `RELEASING.md`. CI keeps Linux tests, since they're cheap and catch logic bugs.
- Existing tags are `alpha-0.0.x`. `release_version.py`'s regex ignores them and starts from
  `0.0.0`, so the first release is run with `bump=minor` and becomes `0.1.0`. The workflow needs
  `permissions: contents: write`. Local settings live in `~/.barcode_tool/` and templates in
  the shared folder, so the folder swap touches no user data. Machines on alpha builds have no updater and need **one manual install** of 0.1.0.
  After that, updates arrive through the app.
- **Updater:** vendor only what the update path needs from Fulfilment's `shared/`
  (`updater.py`, `update_flow.py`, `relaunch.py`, plus a minimal `i18n` shim with `_`/`N_`
  as identity functions) into `app/vendor/updater/`, or wherever fits. Record the source commit in a
  `SYNCED_FROM` line. Keep the same behaviour: check `releases/latest` on start
  (skip in dev builds), require the zip and the `.sha256`, verify, extract, and swap the folder
  after the app exits via the `.cmd` helper, then restart (ADR
  `shopify-fulfillment-tool/docs/adr/0022-updates-swap-the-app-folder-after-exit.md`).
  App-specific values: repo `cognitiveghost/barcode_tool`, asset prefix `BarcodeTool-`,
  exe `BarcodeTool.exe`.
- UI: show the version in the window title or About, add a "Check for updates" action, and show a
  non-blocking prompt when an update exists. The Fulfilment UI's look is not required.
- The builder may sync more of `shared/` if vendoring turns out to drag in half of it. If so,
  note why in the PR.

## Task 3: A4 review sheet (scanner companion)

Replaces the shipped `inventory-table/a4-table` preset and its export flow.
- **Two views, picked at export:** *By position* (sorted by position, with the SKUs under each)
  and *By SKU* (sorted by SKU, with the positions under each). **(owner: "position table, sku table")**
- **Column picker** at export: #, SKU, Name, Client, Batch, Expiry, Qty, SKU QR, Position QR.
  Any column can be hidden, Qty included. **(owner)** The last choice is remembered per view in local
  settings. **(Claude's call)**
- **Codes stay, but small:** 12 mm QR (office laser, scanner-readable). Both code columns are
  kept because sometimes the real item or position can't be scanned. **(owner)**
- **Paper and navigation (Claude's call):** tight rows (~13–14 mm with a QR, ~6 mm
  without), a group header row per position/SKU, light zebra striping, `page x of y` and the
  export date in the footer, the table header repeated on each page, and groups not split across pages
  when they fit on one. Target: ≥ 18 rows/page with QRs, ≥ 35 without. A two-column layout
  is optional for the builder to add if it's cheap.
- It stays a native vector PDF (current behaviour), not a raster.
- Keep the existing path (`render_table_pdf`, `template_renderer.py:157`, Jinja preset in
  `inventory-table/`). Pass `view` and `columns` into the template context, and do the sorting and
  grouping in Python, so the template stays a dumb loop. The new shipped preset replaces
  `a4-table` (app-owned, so it's rewritten on launch). If a remembered table preset no longer exists,
  fall back to the shipped one. **(Claude's call)**

## Task 4: Template builder (drag on canvas) + new presets

**(owner: option B, drag on canvas; used a few times a year by the owner/an admin)**

### Data model
A builder preset is a folder with `layout.json` plus the generated `template.html`,
`style.css` and `meta.json`, so the existing renderer and preset discovery keep working
unchanged. `layout.json` holds:
- `name`, `mode` (positions / inventory), `width_mm`, `height_mm`
- `elements[]`, each with `type`, `x_mm`, `y_mm`, `w_mm`, `h_mm` and per-type props:
  - `text`: `content` (fixed text with `{field}` placeholders, e.g. `{sku} / {batch}`),
    font auto-fit max/min mm, single-line or wrap, bold, align
  - `barcode`: `field`, Code128
  - `qr`: `field`
  - `box`: outline 0.3–0.5 mm
  - `line`: horizontal or vertical, 0.3–0.5 mm

  Fills don't exist in the model.
- The available `{field}`s are the mode's record keys (`templates/examples/README.txt`). Field
  pickers offer only that mode's keys, and an empty value renders blank (current behaviour). The
  text element also has an `uppercase` prop.
- Save runs Task 1's black-area check on the preview render. It warns but still lets you save,
  since stacked lines are the only way to make a block and that is deliberate.
- Generation reuses `label_tools.fit_font` / `fit_font_block` / `barcode` / `qr_code` and the
  absolute-mm CSS pattern of the current presets.

Hand-written presets (no `layout.json`) keep working and show in the dropdown, but can't be
opened in the builder.

### UI
- Opened from the template picker in each mode: **New…**, **Edit…** (builder presets only),
  **Duplicate…**.
- Left: a palette (Text, Barcode, QR, Box, Line). Centre: a canvas at true aspect ratio with a
  1 mm snap grid, where you drag to move and pull handles to resize. Right: the properties of the
  selected element. Top: name, mode, size (a list of common sizes plus custom W×H mm).
- **Preview** toggle: renders the real 203 dpi bitmap with sample data (the first imported row if
  there is one, otherwise placeholder values), so the result looks exactly like the print.
- **Save** writes the folder to `<shared folder>/templates/<mode>/<slug>/`. Saving over an
  app-owned name is refused (it would be wiped on the next launch), so the user picks another name.
- Delete key, arrow-key nudge (0.5 mm), undo for the last action at least. **(Claude's call;
  multi-level undo is fine if cheap)**

### Presets shipped as builder layouts (app-owned)
Rebuild the shipped thermal presets as `layout.json` so they can be duplicated in the builder:
- `positions/default` and `inventory/default` (the thermal-safe versions from Task 1)
- `inventory/qr-sku-68x38mm`
- **New `inventory/product-68x38`:** product name on top (bold, auto-fit, up to 2 lines),
  Code128 of `sku` in the middle, `sku` as text underneath. **(owner)**
- **New `inventory/pallet-150x100`:** a starting point for the owner to adjust. SKU large, name,
  qty, batch, expiry, position QR + text, date. **(Claude's call; the owner had no fixed
  content and will edit it in the builder)**

### One label per unit
In Inventory mode, a checkbox **"One label per unit (Qty)"** prints each row `quantity` times
instead of once. It's meant for product labels. Off by default and remembered in local settings.
Qty is already validated as a positive whole number on import (blank = 1). The total is subject to
Task 1's 2,000-label cap.
**(Claude's call)**

---

## Order and dev-runner

Four dev-runner tasks in the `barcode_tool` section, run in order: 1 → 2 → 3 → 4. Task 1
first because it stops the head damage. Task 2 next, so that later work reaches the PCs through the
updater. Task 4 is the largest. If its plan passes ~25 edits per step, Stage A splits it into
"model + generation + presets" and "canvas UI" itself.

## Left to the builder

The exact layouts of the thermal-safe presets, within the rule above. Element and property
widget choices. Where the vendored updater lives. The black-block detection method. Whether the
A4 sheet gets a two-column layout. Undo depth.
