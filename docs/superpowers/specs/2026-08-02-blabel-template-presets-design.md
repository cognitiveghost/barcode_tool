# Design: HTML/CSS template presets via blabel

## Context

Label layouts are currently hand-coded in `app/core/label_renderer.py` as PIL
`ImageDraw` calls with pixel math derived from proportions of the canvas
(`content_height * 0.42`, etc.). This is especially painful for the mode 2.2
inventory label (dual-QR, three-column layout): the geometry is brittle,
scaling barcodes/QR codes to the label size is manual arithmetic, and tuning
the layout requires editing Python through an LLM rather than iterating
visually.

This design replaces the hand-coded renderer with HTML/CSS templates
rendered through [blabel](https://github.com/Edinburgh-Genome-Foundry/blabel)
(Jinja2 + WeasyPrint). The user designs and iterates on templates directly as
HTML/CSS files; the app's job shrinks to: collect data, discover template
presets, feed records through blabel, and rasterize the result into the same
`PIL.Image` objects the rest of the app already prints.

This is a general redesign covering all label-producing modes (2.1 positions,
2.2 inventory, and future 2.3 product / 2.4 free-text), not a one-off patch
to the inventory label.

## Goals

- Let the user design label layouts as HTML/CSS, independent of app code.
- Fix barcode/QR scaling-to-label-size via CSS instead of manual pixel math.
- Support multiple named presets per mode, selectable in the UI.
- Keep the existing print pipeline (`print_service.py`, `zpl_print_service.py`,
  audit log, PDF archive/debug-preview) completely unchanged — it already
  operates on `list[PIL.Image]` and stays that way.

## Non-goals

- No in-app live-preview window. The existing debug/archive PDF that both
  panels already write on every Print/Generate run doubles as the preview
  loop once it's driven by the new renderer.
- No orientation auto-swap for template-driven labels (see below).
- No visual template editor — templates are edited as files.

## Dependency decision

blabel pulls in WeasyPrint, which on Windows requires a one-time GTK3
runtime install (system installer with native Pango/Cairo/GDK-Pixbuf DLLs) —
not just a pip package. Confirmed acceptable: this is an internal tool
deployed to a handful of known Win10/11 machines, so a one-time setup step
per machine is fine. `blabel + WeasyPrint` is used as-is, no alternate
render backend (e.g. QtWebEngine).

New dependencies: `blabel`, `pypdfium2` (pure-wheel PDF rasterizer, no native
runtime). `python-barcode`, `qrcode`, `Pillow` stay in `requirements.txt`
(transitive blabel deps / still used for rasterization). `zebrafy` stays —
it still converts the final `PIL.Image` to ZPL raster for the raw-ZPL print
path.

## Architecture

The current pipeline is: `render_label()` / `render_inventory_label()` →
`PIL.Image` → either `QPrinter` paint (driver print / PDF output) or
`zebrafy` raster (raw ZPL). Both consumers only care about the final
`PIL.Image` list — that boundary is untouched.

New module `app/core/template_renderer.py` replaces
`app/core/label_renderer.py` and `app/core/barcode_engine.py`:

```python
@dataclass
class TemplatePreset:
    name: str
    mode: str
    width_mm: float
    height_mm: float
    template_path: Path
    stylesheet_path: Path

def list_presets(shared_folder: Path, mode: str) -> list[TemplatePreset]: ...

def render_records(
    preset: TemplatePreset,
    records: list[dict],
    dpi: int = 203,
) -> list[Image.Image]: ...
```

`render_records`:
1. `blabel.LabelWriter(preset.template_path, default_stylesheets=(preset.stylesheet_path,), items_per_page=1)`
   — `items_per_page=1` is blabel's own default: one record renders as one
   PDF page, matching the app's existing "one image per label" model exactly.
2. `pdf_bytes = writer.write_labels(records, target="@memory")` — blabel/
   WeasyPrint return PDF bytes directly, no temp files.
3. Rasterize each PDF page to a `PIL.Image` at `dpi` via `pypdfium2`
   (`PdfDocument(pdf_bytes)`, `page.render(scale=dpi/72).to_pil()`).

Barcodes/QR codes are generated inside the template via blabel's built-in
`label_tools` Jinja global — `label_tools.qr_code(data)` and
`label_tools.barcode(data, barcode_class="code128")` — both return
ready-to-use `data:image/png;base64,...` URIs. This is why
`app/core/barcode_engine.py` is deleted rather than wrapped: blabel already
provides the same functionality (python-barcode/qrcode under the hood).

Physical label size is owned by the template: `style.css` declares
`@page { size: <width_mm>mm <height_mm>mm; margin: 0 }` matching the
preset's `meta.json`. Scaling of barcode/QR images inside the label is
ordinary CSS (`object-fit: contain`, flex/grid sizing) — this is what
resolves the "scaling barcode to label size" complaint.

## Template preset structure

Presets live in the same shared folder already used for the audit log and
printed-PDF archive (`settings["shared_folder"]`), so all users pointed at
the same shared folder automatically see the same presets — no per-machine
file distribution needed.

```
<shared_folder>/templates/
  positions/
    default/
      template.html
      style.css
      meta.json        # {"name": "Default 100x150", "width_mm": 100, "height_mm": 150}
  inventory/
    default/
      template.html
      style.css
      meta.json
```

The `<mode>` subfolder (`positions`, `inventory`, later `product`,
`freetext`) determines which panel's preset combo lists the preset — no
separate `mode` field needed inside `meta.json`.

Adding a new preset = creating a new folder with these three files. No
registration step, no settings UI for template management (consistent with
how `label_sizes` already isn't editable in `SettingsWindow` today).

If `<shared_folder>/templates/<mode>/` doesn't exist or is empty, the app
seeds it by copying a minimal reference template shipped in the repo at
`app/templates/examples/<mode>/default/` — not a finished design, just
something that renders and demonstrates the available Jinja variables, so
a fresh shared folder never dead-ends with "no presets found."

## Data contract per mode

Records are plain dicts passed to `render_records`; these are the same
fields each panel already computes today, just handed to Jinja instead of
positional PIL-drawing arguments.

**positions (2.1):** `code`, `barcode_data` (warehouse-prefixed), `visible_text`
(code + user custom text), `warehouse_prefix`, `custom_text`

**inventory (2.2):** `sku`, `name`, `client`, `batch`, `expiry`,
`position_code`, `position_data` (warehouse-prefixed position code for the
position QR), `generated_date`

Example `inventory/default/template.html` (illustrative, not a final design
— the user designs the real layouts):

```html
<div class="label">
  <div class="qr-col">
    <img src="{{ label_tools.qr_code(sku) }}">
    <div class="caption">{{ sku }}</div>
  </div>
  <div class="mid-col">
    <div class="name">{{ name }}</div>
    {% if expiry %}<div>Expiry: {{ expiry }}</div>{% endif %}
    {% if batch %}<div>Batch: {{ batch }}</div>{% endif %}
  </div>
  <div class="qr-col">
    <img src="{{ label_tools.qr_code(position_data) }}">
    <div class="caption">{{ position_code }}</div>
  </div>
</div>
```

## UI changes

Both `PositionsModePanel` and `InventoryModePanel` replace `label_size_combo`
with a `preset_combo`, populated the same way `warehouse_combo` already is
(`refresh_from_settings()` → `list_presets(shared_folder, mode)`).

**Orientation combobox removed** from `PositionsModePanel`. It currently
just swaps width/height on the canvas, which works because the PIL layout
is trivial (centered barcode + text). Blindly swapping `@page` dimensions
for a hand-authored CSS layout (especially multi-column ones) would likely
break the layout rather than cleanly rotate it. If both a landscape and
portrait version of a label are needed, that's two presets, each with its
own layout tuned for its own orientation — consistent with "custom size" now
meaning "new preset folder."

**No new preview UI.** Both panels already write a debug/archive PDF to
`shared_folder` on every Generate/Print (`inventory_label_preview_*.pdf` in
`InventoryModePanel`, the `printed_pdfs/` archive in `PositionsModePanel`).
Once these are driven by `render_records`, that existing PDF becomes the
template iteration loop: edit `template.html`/`style.css` → Generate/Print
with test data → open the PDF that was already being written.

## Settings/config changes

`DEFAULT_SETTINGS["label_sizes"]` is removed from `app/core/config.py` — it
was never exposed in `SettingsWindow` anyway (just a static default list
consumed directly by the old `label_size_combo`). No other settings changes;
`shared_folder` already exists and is reused as the templates root.

## Migration & cleanup

Deleted:
- `app/core/label_renderer.py` (all pixel-math layout code)
- `app/core/barcode_engine.py` (superseded by blabel's `label_tools`)
- `label_sizes` key from `config.py`
- `tests/test_label_renderer.py`

Added:
- `app/core/template_renderer.py` (+ `tests/test_template_renderer.py`
  covering preset discovery from a temp shared folder, and `render_records`
  producing correctly-sized `PIL.Image`s from a fixture preset)
- `app/templates/examples/positions/default/`,
  `app/templates/examples/inventory/default/` (seed templates, checked into
  git)

Updated: `mode_positions_panel.py`, `mode_inventory_panel.py` (preset combo
instead of label-size combo, no orientation combo), `requirements.txt`
(`blabel`, `pypdfium2` added).

## Testing

- `test_template_renderer.py`: preset discovery (empty dir seeds examples;
  populated dir lists presets from `meta.json`), `render_records` output
  image count/dimensions against a small fixture template.
- Existing `test_mode_positions_panel.py` / `test_mode_inventory_panel.py`
  updated to drive the new preset-combo flow instead of label-size fixtures;
  print/audit-log/archive assertions unchanged since they operate on the
  same `list[Image.Image]` contract as before.
