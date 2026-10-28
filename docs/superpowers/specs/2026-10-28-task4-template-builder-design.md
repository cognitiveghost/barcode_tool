# Task 4: Template builder (drag on canvas) + product & pallet presets

Date: 2026-10-28. Refines **Task 4** of
`docs/superpowers/specs/2026-10-28-thermal-templates-builder-updates-design.md` (the parent spec;
its goals, owner decisions and constraints still apply). Classification: **architectural** (a
new file format in a shared folder plus a new editor). Each decision is marked **(owner)** (from the
parent spec or the approval round) or **(Claude's call)**.

## Why

Making or changing a label today means hand-editing Jinja + CSS in the shared folder. The owner or
an admin does this a few times a year, so they need a visual editor that can only produce
thermal-safe labels (no fills), shows the real 203 dpi print, and needs no restart to use the result. **(owner)**

## What exists today (verified)

- `list_presets(shared, mode)` (`app/core/template_renderer.py:52`) lists
  `<shared>/templates/<mode>/*/meta.json`. A preset is `template.html` + `style.css` + `meta.json`
  (`{"name","width_mm","height_mm"}`). `render_records(preset, records)` renders each record to a
  bilevel 203 dpi PIL image through blabel/WeasyPrint. Jinja has **no autoescape**.
- `_seed_examples` (`template_renderer.py:102`) rewrites the shipped presets from
  `app/templates/examples/<mode>/<folder>/` into the shared folder, once per process per mode.
  It copies `SEEDED_FILES = ("template.html", "style.css", "meta.json")`. **App-owned** means a
  folder name that exists under `EXAMPLES_ROOT/<mode>/`.
- Task 1 left `find_thermal_black_block(preset, records)` (`template_renderer.py:198`). It returns
  `(record_index, x_px, y_px)` or `None`.
- `label_tools.fit_font` / `fit_font_block` / `barcode` / `qr_code` (`app/core/label_tools.py`).
- Picker: `ModePanel.refresh_from_settings` (`app/ui/mode_panel.py:37`) fills `preset_combo`
  (item text = meta name, item data = `TemplatePreset`) and reselects QSettings
  `<MODE>/last_template` (by name). `MainWindow` calls it after a settings save.
- Label cap: `check_label_count(n)` (`mode_panel.py:16`, 2,000) and `render_labels` (confirm > 300).
  Inventory print: `_on_print_clicked` (`mode_inventory_panel.py:252`) and `print_checked_items`
  (`:299`) both build one record per `checked_items()` entry. `InventoryItem.quantity` is an `int`
  ≥ 1; the record's `"quantity"` is its string.
- Existing tests guard the shipped presets by **meta name** and scanning: "Default 150x100mm"
  (both modes) and "QR-SKU 68x38mm" (`tests/test_template_renderer.py:285-386`), plus
  `tests/test_thermal_safe.py` (no ≥ 3×3 mm black block in any shipped thermal preset).

## Goals

1. A `layout.json` model that can express only thermal-safe things: text, Code128, QR, outline
   boxes, 0.3–0.5 mm lines. **(owner)**
2. Generate `template.html` / `style.css` / `meta.json` from it, so the renderer, discovery and
   printing are unchanged. **(owner)**
3. A drag-on-canvas editor with a real-print preview and save into the shared folder. **(owner)**
4. The shipped thermal presets rebuilt as layouts, plus two new ones. **(owner)**
5. "One label per unit (Qty)" in Inventory mode. **(owner / parent spec)**

Non-goals: editing hand-written presets in the builder, fills or images, rotation, fonts other
than the bundled JetBrains Mono, a layout-format version field, changing the A4 table preset.
Anti-goal: a builder that can save something the renderer then fails on, or that silently
overwrites an app-owned folder.

## Data model: `layout.json` **(owner, details Claude's call)**

```json
{
  "name": "Product 68x38mm",
  "mode": "inventory",
  "width_mm": 68,
  "height_mm": 38,
  "elements": [
    {"type": "text", "x_mm": 2, "y_mm": 2, "w_mm": 64, "h_mm": 12,
     "content": "{name}", "max_mm": 5, "min_mm": 2, "wrap": true,
     "bold": true, "uppercase": false, "align": "center", "letter_spacing_mm": 0},
    {"type": "barcode", "x_mm": 4, "y_mm": 15, "w_mm": 60, "h_mm": 14, "field": "sku"},
    {"type": "qr",      "x_mm": 0, "y_mm": 0, "w_mm": 20, "h_mm": 20, "field": "position_data"},
    {"type": "box",     "x_mm": 1.5, "y_mm": 1.5, "w_mm": 65, "h_mm": 35, "thickness_mm": 0.4},
    {"type": "line",    "x_mm": 2, "y_mm": 30, "w_mm": 64, "h_mm": 0,
     "orientation": "h", "thickness_mm": 0.3}
  ]
}
```

- `mode` is `positions` or `inventory`. Elements draw in list order (later on top).
- `text.content` is fixed text with `{field}` placeholders (e.g. `{sku} / {batch}`). Every
  placeholder must be a key of the mode. `wrap: false` is single-line, auto-fit with `fit_font`.
  `wrap: true` wraps, auto-fit with `fit_font_block`. `align` is `left|center|right`. Text is
  always **vertically centred** in its box. `letter_spacing_mm` (default 0) is an addition: the
  current presets use letter-spacing on their captions and SKU, and dropping it would visibly
  change them. **(Claude's call)**
- `barcode` is always Code128 (`label_tools.barcode`). `qr` uses `label_tools.qr_code`. Both take
  one `field` from the mode's keys. An empty value renders nothing, as today.
- `box` is an outline only. `line` uses `orientation` `h` (length `w_mm`, `h_mm` 0) or `v` (length
  `h_mm`, `w_mm` 0). `thickness_mm` is clamped to 0.3–0.5 for both.
- There is no fill property anywhere, so a solid block can only come from stacking lines, which the
  black-area check catches on Save.
- **Mode keys and sample data** live in one dict, `SAMPLE_RECORDS[mode]`, in the new
  `app/core/layout_builder.py`. Its keys are the mode's fields, in the README's order (positions:
  `code, barcode_data, visible_text, warehouse_prefix, user_text`; inventory: `sku, name, client,
  batch, expiry, position_code, position_data, generated_date, quantity`). Its values are the
  placeholder sample. **(Claude's call)**
- Loading is tolerant: missing optional props get defaults. A `layout.json` that fails validation
  (unknown type or field, bad numbers, wrong mode) raises `ValueError` with a readable message. The
  picker still lists it (discovery reads only `meta.json`), and Edit/Duplicate show the error.

## Generation **(owner: reuse label_tools and the absolute-mm pattern)**

`generate(layout) -> {"template.html": str, "style.css": str, "meta.json": str}`, deterministic,
so the committed shipped files can be compared to it byte for byte.

- `meta.json`: `{"name", "width_mm", "height_mm"}`.
- `style.css`: `@page { size: Wmm Hmm; margin: 0; }`, the same `.label` block as the current
  presets, and one rule per element, `.e<index>`, with `left/top/width/height` in mm. Elements are
  `position: absolute; box-sizing: border-box; display: flex; overflow: hidden`. Text gets
  `align-items: center`, `justify-content` + `text-align` from `align`, `font-weight: 700` when bold,
  `text-transform: uppercase`, `letter-spacing`, and `white-space: nowrap; line-height: 1` or
  `line-height: 1.25; word-wrap: break-word`. Codes get `img { width: 100%; height: 100% }`. Boxes
  get `border: Tmm solid #000`. Lines get `border-top` or `border-left` on a zero-height or zero-width
  element. There is never a `background` other than `#fff` on `.label`.
- `template.html`: one `<div class="label">` with a div per element.
  - Text: `{% set t%N %}…{% endset %}`, where literal segments are emitted as Jinja string literals
    (`{{ "…" }}`, JSON-quoted) and placeholders as `{{ field }}`. Then
    `<div class="el eN" style="font-size: {{ label_tools.fit_font(tN, W-1, max, min, letter_spacing_mm=ls) }}mm">{{ tN|e }}</div>`
    (or `fit_font_block(tN, W-1, H-0.5, max, min)` for wrap). The single-line max is capped at
    `h_mm`. Literal quoting makes user text Jinja-safe, and `|e` makes record values HTML-safe. That
    is new for builder presets only. **(Claude's call)**
  - Codes: `{% if field %}<img src="{{ label_tools.barcode(field) }}">{% endif %}` (or `qr_code`).
  - Box/line: an empty div.
- Both files start with one header comment: generated from `layout.json` by the template
  builder; edit it in the app; hand edits are lost on the next Save; folders named like a shipped
  preset are app-owned and rewritten on launch.

## Shipped presets as layouts **(owner)**

Each shipped thermal preset folder gets a `layout.json`, and its three files become the committed
output of `generate`. A test fails if they differ. `python -m app.core.layout_builder` regenerates
every shipped preset. Folder names and meta names stay as they are, so the existing tests and the
remembered `last_template` keep working.

- `positions/default`, "Default 150x100mm": the Task 1 layout, re-expressed. Outlined boxes become
  `box` + `text`, and captions with rules become `text` + `line`.
- `inventory/default`, "Default 150x100mm": the same treatment. The notes area becomes a box plus
  two lines, the empty `note-text` divs are dropped, and the description text is now vertically
  centred instead of top-aligned. **(Claude's call)**
- `inventory/qr-sku-68x38mm`, "QR-SKU 68x38mm": QR of `sku` plus a wrapped bold name.
- **New `inventory/product-68x38`, "Product 68x38mm"**: name at the top (bold, wrapped, auto-fit,
  ~2 lines, max 4.5 mm), Code128 of `sku` in the middle, and `sku` as a single-line bold text below.
  **(owner)**
- **New `inventory/pallet-150x100`, "Pallet 150x100mm"**: a starting point. A frame, a large
  single-line SKU across the top, name (wrapped), QTY / LOT / EXP text rows, a position QR +
  position text in the right column, and the date bottom-right. **(Claude's call; the owner will
  adjust it in the builder)**

`_seed_examples` also copies `layout.json` when the shipped folder has one (`inventory-table/a4-table`
does not). `README.txt` gains a short "Builder presets" section.

All five pass `test_thermal_safe.py` (it already parametrises over every shipped folder).

## Builder UI (`app/ui/template_builder.py`) **(owner: layout; Claude's call: details)**

Opened from a **Template ▾** tool button next to the template combo in both mode panels:
- **New…** starts an empty layout (150×100) in the panel's mode.
- **Edit…** opens the selected preset's `layout.json` and saves back into the same folder. It is
  enabled only for builder presets (folder has `layout.json`) that are not app-owned. **(Claude's
  call: an app-owned preset is changed by duplicating it)**
- **Duplicate…** opens a copy named "Copy of <name>" that saves to a new folder. It is enabled for
  any builder preset.

Window (`QDialog`, maximisable):
```
┌ Name [__________]  Mode: inventory   Size [68 × 38 mm ▾] W[68] H[38]  [Preview] [Undo] [Save] ┐
│ Palette  │                 canvas (QGraphicsView)                    │ Properties          │
│ Text     │   grey surround, white label at true aspect ratio,        │ X Y W H (mm, 0.5)   │
│ Barcode  │   faint 1 mm dot grid, 10 mm grid lines,                  │ + per-type fields   │
│ QR       │   dashed 1.25 mm thermal safe-margin guide                │ (field combos list  │
│ Box      │                                                           │  only mode keys)    │
│ Line     │                                                           │ [Delete]            │
└──────────┴───────────────────────────────────────────────────────────┴─────────────────────┘
```
- Mode is shown, not editable: it is the panel's mode (or the source preset's). **(Claude's call)**
- Sizes: 150×100, 100×150, 100×100, 100×50, 68×38, 58×40, 50×30, and Custom (W, H spin boxes,
  10–300 mm). Elements outside a smaller label are kept, and they clip. **(Claude's call)**
- Palette click adds the element at a default size near the top-left and selects it.
- The scene uses 1 unit = 1 mm. A drag moves an element and snaps it to 1 mm on release. A single
  bottom-right handle on the selected element resizes it (snap 1 mm, min 1 mm); on a line it changes
  only the length. Arrow keys nudge 0.5 mm, Delete removes. **(Claude's call: one handle is enough)**
- Elements are drawn as an approximation: text shows its `content` (placeholders visible) in the
  bundled font at its max size, clipped; barcode and QR show as hatched rectangles labelled with
  the field; box and line show at their thickness. The selection outline and handle use one accent
  colour, the only non-black colour on the label, so they never read as ink.
- Properties: X/Y/W/H, then per type. Text has a content line edit plus an "Insert field" combo,
  max/min mm, single-line/wrap, bold, uppercase, align, letter spacing. Barcode and QR have a field
  combo. Box has thickness. Line has orientation and thickness.
- **Undo**: multi-level. A list of JSON snapshots, one pushed per committed change; Ctrl+Z and
  the button pop it. **(Claude's call: it's cheap)**
- **Preview** (checkable): generates the files into a temp folder, renders the sample record with
  `render_records`, and shows the 203 dpi bitmap scaled over the label. Editing is disabled while
  it is on. Render errors (e.g. a barcode that can't encode the sample) show in a status line and
  untoggle Preview.
- Sample record: the panel passes `sample_record()`. Inventory: the first checked item, else the
  first row, as `_record_for_item(...)`. Positions: the first generated code's record. Missing
  keys and the no-data case fall back to `SAMPLE_RECORDS[mode]`.
- **Save**:
  1. Name required. New/Duplicate save to `slugify(name)` (lowercase, runs of non-alphanumerics →
     `-`). Edit always saves into the folder it opened, even when the name changes: no folder ever
     moves, so a rename can't overwrite or orphan anything. **(Claude's call)**
  2. Refused, with a message to pick another name, when the slug is app-owned (New/Duplicate), when
     New/Duplicate targets an existing folder, or when another preset of the mode (not the one being
     edited) already uses that display name.
  3. Validates the layout, then runs `find_thermal_black_block` on the sample render. A hit asks
     "Save anyway?" with the position in mm (the default button is Cancel). It checks the sample
     render only, the same image Preview shows. **(owner: warn, don't block, on the preview render)**
  4. Writes `layout.json` + generated files with `atomic_write_text` into
     `<shared>/templates/<mode>/<slug>/`, sets `<mode>/last_template` to the name, and the panel
     calls `refresh_from_settings` so the new preset is selected.
- Closing with unsaved changes asks to discard. **(Claude's call)**

## One label per unit (Qty) **(owner / parent spec)**

An Inventory-mode checkbox, **"One label per unit (Qty)"**, off by default, remembered in QSettings
`inventory/one_label_per_unit` (read with `type=bool`). When it is on, a helper
`_items_to_print()` returns each checked item repeated `item.quantity` times, in order. The
count check, the preview count, `render_page` and `print_checked_items` all use it. The
2,000 cap and the > 300 confirm apply to that total. The audit description is unchanged
(unique SKUs). Each copy is the same record, so a template that prints `{quantity}` shows the row's
total on every copy. Product labels don't print qty, so that is left as is. **(Claude's call)**

## Testing

- `tests/test_layout_builder.py` (pure): validation errors, placeholder → Jinja (literal with
  quotes and braces stays literal, a record value with `<` is escaped), the empty field gives no `<img>`,
  thickness clamping, deterministic output, `slugify`, app-owned detection, the save-target checks,
  and a generated product preset rendering + scanning (zxingcpp) the sku.
- Shipped presets: committed files == `generate(layout.json)` for each shipped folder; existing
  scan/name tests keep passing; the new `product-68x38` scans its Code128; `pallet-150x100` scans
  its position QR; `test_thermal_safe.py` covers all five.
- `tests/test_template_builder.py` (Qt offscreen, no qtbot, the repo's patterns): add from the palette,
  move + snap, nudge, resize, delete, undo, properties edit, preview produces a pixmap, Save
  writes the folder, Save refuses an app-owned name, a black-block layout prompts.
- Inventory panel: Qty expansion count + cap, and the setting is remembered.

## Left to the builder

Exact default element sizes, colours of the accent/grid, the precise coordinates of the rebuilt
`inventory/default` (match the current render as closely as the model allows), and widget
arrangement inside the properties panel.
