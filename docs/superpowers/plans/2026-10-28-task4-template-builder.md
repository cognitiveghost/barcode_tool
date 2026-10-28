# Template Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A drag-on-canvas label template builder that saves `layout.json` + generated `template.html`/`style.css`/`meta.json`, the shipped thermal presets rebuilt as layouts plus new product 68×38 and pallet 150×100 presets, and an Inventory "One label per unit (Qty)" checkbox.

**Architecture:** A pure module `app/core/layout_builder.py` validates layouts, generates the three preset files (so `template_renderer` is untouched apart from seeding `layout.json`), and handles save targets, sample renders and the black-area check. A `QDialog` in `app/ui/template_builder.py` edits a layout dict on a `QGraphicsScene` in mm units with a snapshot undo stack. `ModePanel` opens it from a "Template" menu button.

**Tech Stack:** Python 3.14, PySide6 (QGraphicsView), Jinja2 via blabel, WeasyPrint, pypdfium2, zxingcpp (tests only).

**Spec:** `docs/superpowers/specs/2026-10-28-task4-template-builder-design.md` (read it first; it is approved). Parent: `docs/superpowers/specs/2026-10-28-thermal-templates-builder-updates-design.md` → Task 4.

## Global Constraints

- Run tests one file at a time, always offscreen: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/<file> -v`. The single-process full suite segfaults late (WeasyPrint/Pango); that is known, not your bug. Lint: `.venv/bin/ruff check .`
- No new dependency. Do not change `render_records`, `render_table_pdf`, `find_black_block` or `find_thermal_black_block`.
- No fill anywhere in generated CSS: the only `background` is `#fff` on `.label`.
- Element types exactly `text`, `barcode`, `qr`, `box`, `line`. Modes exactly `positions`, `inventory`.
- Thickness of box and line clamped to 0.3–0.5 mm. Label size 10–300 mm per side.
- Snap 1 mm on drag/resize release; arrow-key nudge 0.5 mm.
- QSettings keys: `<mode>/last_template` (existing), `inventory/one_label_per_unit` (new, read with `type=bool`).
- Shipped folder names and meta names must not change: `positions/default` and `inventory/default` = "Default 150x100mm", `inventory/qr-sku-68x38mm` = "QR-SKU 68x38mm". New: `inventory/product-68x38` = "Product 68x38mm", `inventory/pallet-150x100` = "Pallet 150x100mm".
- Tests construct widgets with `QApplication.instance() or QApplication([])` (no qtbot) and must never open a real modal: monkeypatch `QMessageBox.*` / `exec`.
- UI copy is sentence case; buttons say what they do ("Save template", "Preview").

## Review Focus

1. A text `content` containing quotes, `{{`, `{%`, `<b>` or a `{unknown}` placeholder: literal text prints literally, `{unknown}` is refused by validation, a record value with `<` prints as `<`. Tests in Task 1.
2. Saving into an app-owned or already-existing folder, or with a display name another preset already uses, must be refused without writing anything; Edit with a changed name must still write into its own folder. Tests in Task 2.
3. A shipped preset's committed files drifting from `generate(layout.json)` (someone edits the CSS by hand). Test in Task 3.
4. One label per unit with qty 1,500 on two rows: the 2,000 cap must fire on the expanded total, before any render. Test in Task 4.
5. Preview of a layout whose barcode can't encode the sample (e.g. a Cyrillic `name` in a barcode): an error message in the status line, no crash, Preview untoggled. Test in Task 7.

---

### Task 1: Layout model and generator

**Files:**
- Create: `app/core/layout_builder.py`
- Test: `tests/test_layout_builder.py`

**Interfaces:**
- Produces:
  - `MODES = ("positions", "inventory")`, `ELEMENT_TYPES = ("text", "barcode", "qr", "box", "line")`
  - `SAMPLE_RECORDS: dict[str, dict[str, str]]`. Keys in this order, values exactly:
    positions `{"code": "H029A", "barcode_data": "C001H029A", "visible_text": "H-029-A", "warehouse_prefix": "C001", "user_text": "AISLE H"}`;
    inventory `{"sku": "SKU-12345", "name": "Sample product name 500 ml", "client": "Client Ltd", "batch": "B-240815", "expiry": "2027-05-31", "position_code": "H-029-A", "position_data": "C001H029A", "generated_date": "2026/10/28", "quantity": "3"}`
  - `mode_fields(mode: str) -> list[str]` = `list(SAMPLE_RECORDS[mode])`
  - `new_layout(mode: str) -> dict` → `{"name": "", "mode": mode, "width_mm": 150, "height_mm": 100, "elements": []}`
  - `default_element(type_: str, mode: str, x_mm: float = 2, y_mm: float = 2) -> dict` (full prop set, see Step 3)
  - `placeholders(content: str) -> list[str]` (regex `\{([a-z_]+)\}`, in order)
  - `normalise_layout(data: dict) -> dict` (new dict, defaults filled, validated; `ValueError` with a readable message)
  - `generate(layout: dict) -> dict[str, str]` with keys `"template.html"`, `"style.css"`, `"meta.json"`
  - `slugify(name: str) -> str`

- [ ] **Step 1: Write the failing tests** in `tests/test_layout_builder.py`:

```python
def test_normalise_fills_defaults_and_clamps_thickness():
    layout = normalise_layout({"name": "X", "mode": "inventory", "width_mm": 68, "height_mm": 38,
        "elements": [{"type": "box", "x_mm": 1, "y_mm": 1, "w_mm": 10, "h_mm": 10, "thickness_mm": 2},
                     {"type": "line", "x_mm": 1, "y_mm": 5, "w_mm": 20, "h_mm": 7, "orientation": "h", "thickness_mm": 0.1},
                     {"type": "text", "x_mm": 0, "y_mm": 0, "w_mm": 20, "h_mm": 5, "content": "{sku}"}]})
    box, line, text = layout["elements"]
    assert box["thickness_mm"] == 0.5 and line["thickness_mm"] == 0.3
    assert line["h_mm"] == 0                         # off-axis size forced to 0
    assert text["wrap"] is False and text["align"] == "left" and text["letter_spacing_mm"] == 0

@pytest.mark.parametrize("bad, message", [
    ({"mode": "pallets"}, "mode"),
    ({"width_mm": 5}, "width"),
    ({"elements": [{"type": "circle", "x_mm": 0, "y_mm": 0, "w_mm": 5, "h_mm": 5}]}, "circle"),
    ({"elements": [{"type": "qr", "x_mm": 0, "y_mm": 0, "w_mm": 5, "h_mm": 5, "field": "code"}]}, "code"),
    ({"elements": [{"type": "text", "x_mm": 0, "y_mm": 0, "w_mm": 5, "h_mm": 5, "content": "{skuu}"}]}, "skuu"),
    ({"elements": [{"type": "text", "x_mm": -1, "y_mm": 0, "w_mm": 5, "h_mm": 5, "content": "a"}]}, "x_mm"),
])
def test_normalise_rejects(bad, message):
    base = {"name": "X", "mode": "inventory", "width_mm": 68, "height_mm": 38, "elements": []}
    with pytest.raises(ValueError, match=message):
        normalise_layout({**base, **bad})

def test_literal_text_stays_literal_and_values_are_escaped(tmp_path):
    # generate into tmp_path, build a TemplatePreset, render with render_records is too coarse -
    # render the template string with jinja2 directly instead:
    files = generate(normalise_layout({... one text element, content: 'A "q" {{x}} {% y %} <b> {sku}' ...}))
    html = jinja2.Template(files["template.html"]).render(sku="<S>", label_tools=label_tools)
    assert '&#34;q&#34;' in html or '&quot;q&quot;' in html   # |e escapes quotes
    assert "{{x}}" in html and "{% y %}" in html and "&lt;b&gt;" in html and "&lt;S&gt;" in html

def test_empty_code_field_renders_no_img():
    files = generate(<layout with one qr on "batch">)
    assert "<img" not in jinja2.Template(files["template.html"]).render(batch="", label_tools=label_tools)

def test_generate_is_deterministic_and_has_no_fill():
    files = generate(layout); assert files == generate(layout)
    assert re.findall(r"background[^;]*;", files["style.css"]) == ["background: #fff;"]
    assert json.loads(files["meta.json"]) == {"name": "X", "width_mm": 68, "height_mm": 38}

def test_generated_preset_renders_and_scans(tmp_path):
    # barcode of sku + qr of position_data, written to tmp_path, rendered with render_records
    # at 203 dpi with SAMPLE_RECORDS["inventory"]; zxingcpp decodes {"SKU-12345", "C001H029A"}

@pytest.mark.parametrize("name, slug", [("Product 68x38mm", "product-68x38mm"), ("  Ünïcode / A  ", "ünïcode-a"), ("!!!", "")])
def test_slugify(name, slug): assert slugify(name) == slug
```

Fill in the `<...>` layouts concretely. Reuse the render/zxingcpp pattern of `tests/test_template_renderer.py:349`.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_layout_builder.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement `app/core/layout_builder.py`**

Defaults per type for `default_element` and for missing keys in `normalise_layout`:
- text: `w_mm 40, h_mm 8, content "Text", max_mm 5, min_mm 2, wrap False, bold False, uppercase False, align "left", letter_spacing_mm 0`
- barcode: `w_mm 50, h_mm 12, field` = `"barcode_data"` (positions) / `"sku"` (inventory)
- qr: `w_mm 20, h_mm 20, field` as barcode
- box: `w_mm 30, h_mm 20, thickness_mm 0.4`
- line: `w_mm 40, h_mm 0, orientation "h", thickness_mm 0.3`

Validation in `normalise_layout` (message names the offending key or value): `mode` in `MODES`; `width_mm`/`height_mm` numbers in 10–300; `name` a str (may be empty here); every element: `type` in `ELEMENT_TYPES`; `x_mm, y_mm` ≥ 0; non-line `w_mm, h_mm` ≥ 1; line: length on its axis ≥ 1, the other forced to 0, `orientation` in `h|v`; text: `content` str, every `placeholders()` entry in `mode_fields`, `0 < min_mm <= max_mm`, `align` in `left|center|right`, `letter_spacing_mm` ≥ 0; barcode/qr: `field` in `mode_fields`; thickness clamped. Unknown extra keys are dropped. Numbers stay int when given as int (so `meta.json` reads `150`, not `150.0`).

`slugify`: lowercase, `re.sub(r"[^\w]+", "-", s)` with `\w` minus `_` (treat `_` as a separator), strip `-`.

`generate`: exact format below. `_mm(v)` = `f"{v:g}mm"`. `HEADER` text (both files):
`GENERATED by the template builder from layout.json - edit this label in the app (Template > Edit...). Hand edits here are lost on the next Save. Folders named like a shipped preset are app-owned and rewritten on launch. See ../README.txt`

`style.css`:
```
/* HEADER */
@page { size: <W>mm <H>mm; margin: 0; }
html, body { margin: 0; padding: 0; }
.label { position: relative; box-sizing: border-box; width: <W>mm; height: <H>mm; background: #fff; color: #000; font-family: "JetBrains Mono", monospace; overflow: hidden; }
.el { position: absolute; box-sizing: border-box; display: flex; overflow: hidden; }
.el img { width: 100%; height: 100%; }
.e<i> { left: ..; top: ..; width: ..; height: ..; <type rules> }   one line per element
```
Type rules: text → `align-items: center; justify-content: flex-start|center|flex-end; text-align: left|center|right;` + `font-weight: 700;` if bold + `text-transform: uppercase;` if uppercase + `letter-spacing: <ls>mm;` if > 0 + single-line `white-space: nowrap; line-height: 1;` / wrap `line-height: 1.25; word-wrap: break-word;`. box → `border: <t>mm solid #000;`. line h → `height: 0; border-top: <t>mm solid #000;`, v → `width: 0; border-left: <t>mm solid #000;`. barcode/qr → none.

`template.html`: `{# HEADER #}`, then `<div class="label">`, one line per element, `</div>`.
- text i: `{% set t<i> %}` + segments + `{% endset %}<div class="el e<i>" style="font-size: {{ FIT }}mm">{{ t<i>|e }}</div>`. Literal segments → `{{ <json.dumps(seg, ensure_ascii=False)> }}`; placeholders → `{{ field }}`. FIT single-line: `label_tools.fit_font(t<i>, <w-1>, <min(max_mm, h_mm)>, <min_mm>, letter_spacing_mm=<ls>)`; wrap: `label_tools.fit_font_block(t<i>, <w-1>, <h-0.5>, <max_mm>, <min_mm>)`. Format numbers with `:g`.
- barcode/qr i: `<div class="el e<i>">{% if F %}<img src="{{ label_tools.barcode(F) }}">{% endif %}</div>` (`qr_code` for qr).
- box/line i: `<div class="el e<i>"></div>`.

`meta.json`: `json.dumps({"name": ..., "width_mm": ..., "height_mm": ...}, ensure_ascii=False)`.

- [ ] **Step 4: Run the tests** (same command). Expected: all PASS. Then `.venv/bin/ruff check .`.

- [ ] **Step 5: Commit** `git add app/core/layout_builder.py tests/test_layout_builder.py && git commit -m "feat: layout.json model and preset generator"`

---

### Task 2: Save targets, sample render, black check, seeding layout.json

**Files:**
- Modify: `app/core/layout_builder.py`
- Modify: `app/core/template_renderer.py:34` (`SEEDED_FILES`) and `_seed_examples` (`:102-128`)
- Test: `tests/test_layout_builder.py`, `tests/test_template_renderer.py`

**Interfaces:**
- Consumes: Task 1's `normalise_layout`, `generate`, `slugify`, `SAMPLE_RECORDS`; `template_renderer.EXAMPLES_ROOT`, `TemplatePreset`, `list_presets`, `render_records`, `find_thermal_black_block`; `config.atomic_write_text`.
- Produces:
  - `is_app_owned(mode: str, slug: str) -> bool` → `(EXAMPLES_ROOT / mode / slug).is_dir()`
  - `load_layout(folder: Path) -> dict` (reads `layout.json`, `normalise_layout`; JSON/OS errors re-raised as `ValueError`)
  - `check_save_target(shared_folder: Path, layout: dict, edit_folder: Path | None) -> Path` (raises `ValueError`)
  - `save_layout(layout: dict, folder: Path) -> None`
  - `sample_for(mode: str, record: dict | None) -> dict` = `{**SAMPLE_RECORDS[mode], **(record or {})}`
  - `render_sample(layout: dict, record: dict) -> PIL.Image.Image`
  - `black_block_mm(layout: dict, record: dict) -> tuple[float, float] | None`
  - `regenerate_shipped() -> list[Path]` + `if __name__ == "__main__": regenerate_shipped()`

- [ ] **Step 1: Write the failing tests**
  - `test_check_save_target_new_uses_slug(tmp_path)` → `tmp_path/"templates"/"inventory"/"my-label"` for name "My label".
  - `test_check_save_target_refuses_app_owned(tmp_path)`: name "Default" in inventory → `ValueError` matching `"built-in"`.
  - `test_check_save_target_refuses_existing_folder(tmp_path)`: pre-create `templates/inventory/my-label/` → `ValueError` matching `"already exists"`.
  - `test_check_save_target_refuses_duplicate_display_name(tmp_path)`: an existing preset folder `other/` whose meta name is "My label", saving New "My label!" (slug `my-label`, free) → `ValueError` matching `"already called"`.
  - `test_check_save_target_edit_keeps_folder_on_rename(tmp_path)`: `edit_folder = .../inventory/mine`, name "Renamed" → returns `edit_folder`; editing with its own current display name is allowed.
  - `test_check_save_target_refuses_edit_of_app_owned(tmp_path)`: `edit_folder=.../inventory/default` → `ValueError`.
  - `test_check_save_target_refuses_nameless(tmp_path)`: name `"!!!"` → `ValueError`.
  - `test_save_layout_then_list_presets_and_load_round_trip(tmp_path)`: after save, `list_presets(tmp_path, "inventory")` contains the name, and `load_layout(folder) == normalise_layout(layout)`; no `*.tmp` left.
  - `test_black_block_mm_flags_stacked_lines()`: 20 horizontal 0.5 mm lines at y = 10, 10.5, … on a 68×38 label → not `None`, and its x/y in mm are within the stacked area; a layout with one box → `None`.
  - `test_render_sample_size()`: 68×38 → image size ≈ `(round(68/25.4*203), round(38/25.4*203))` ±1.
  - In `tests/test_template_renderer.py`: `test_seeding_copies_layout_json_when_shipped(tmp_path)`: after `list_presets(tmp_path, "inventory")`, `templates/inventory/default/layout.json` exists (it will after Task 3; for now write the test against a monkeypatched `EXAMPLES_ROOT` containing a folder with a `layout.json`), and seeding a shipped folder without `layout.json` still works (`inventory-table/a4-table`).

- [ ] **Step 2: Run** `tests/test_layout_builder.py` and `tests/test_template_renderer.py`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**
  - `check_save_target` order: normalise; `slug = slugify(name)`; empty → `"Use at least one letter or digit in the name."`. Edit (`edit_folder` set): `is_app_owned(mode, edit_folder.name)` → refuse; target = `edit_folder`. New: `is_app_owned(mode, slug)` → `f'"{name}" is a built-in template name - pick another name.'`; `(mode_dir / slug).exists()` → `f'A template folder named "{slug}" already exists - pick another name.'`. Then for each `list_presets(shared_folder, mode)` with `p.name == name` and `p.template_path.parent.resolve() != target.resolve()` → `f'Another template is already called "{name}" - pick another name.'`.
  - `save_layout`: `atomic_write_text(folder / "layout.json", json.dumps(normalise_layout(layout), indent=2, ensure_ascii=False) + "\n")`, then each generated file.
  - `render_sample`: `tempfile.TemporaryDirectory()` → `save_layout` into it → `TemplatePreset(name, mode, w, h, dir/"template.html", dir/"style.css")` → `render_records(preset, [record])[0]`.
  - `black_block_mm`: same temp preset, `find_thermal_black_block(preset, [record])`, convert px to mm with `25.4 / 203`, round to 0.1.
  - `regenerate_shipped`: for each `EXAMPLES_ROOT/<mode>/*/layout.json` with mode in `MODES`, `save_layout(load_layout(folder), folder)`; return the folders.
  - `template_renderer`: `SEEDED_FILES = ("template.html", "style.css", "meta.json", "layout.json")` and in `_seed_examples` skip a filename whose source file doesn't exist.

- [ ] **Step 4: Run** both test files and ruff. Expected: PASS.

- [ ] **Step 5: Commit** `feat: builder save targets, sample render and layout.json seeding`.

---

### Task 3: Shipped presets as layouts + product and pallet presets

**Files:**
- Create: `layout.json` in `app/templates/examples/positions/default/`, `inventory/default/`, `inventory/qr-sku-68x38mm/`, and new folders `inventory/product-68x38/`, `inventory/pallet-150x100/`
- Regenerate (do not hand-edit): the `template.html`, `style.css`, `meta.json` beside each
- Modify: `app/templates/examples/README.txt` (add a "Builder presets" section)
- Test: `tests/test_layout_builder.py`, `tests/test_template_renderer.py`

**Interfaces:**
- Consumes: Task 2's `regenerate_shipped`, `load_layout`; Task 1's `generate`.

Write each `layout.json` with the element lists below. Omitted props take the Task 1 defaults; `regenerate_shipped` rewrites each `layout.json` in full normalised form. Shorthand: `T` text, `B` barcode, `Q` qr, `X` box, `L` line; `x,y,w,h` in mm; text flags `b` bold, `u` uppercase, `wrap`; `max/min` font mm; `ls` letter spacing; `al` align (default left); `t` thickness; `v` vertical line.

**positions/default** "Default 150x100mm" 150×100:
`T "{user_text}" 3,3,144,15 max9 b al=center ls0.3` · `X 3,20,144,47 t0.4` · `B barcode_data 7,24,136,39` · `X 3,71,144,26 t0.5` · `T "{visible_text}" 3.5,71.5,143,25 max18 b al=center ls1`

**inventory/default** "Default 150x100mm" 150×100 (from the current CSS):
`X 1.5,1.5,147,97 t0.4` · `L v 52,3,h94 t0.3` · `L v 101,3,h94 t0.3`
col 1: `T "SKU" 3.5,3.5,47,7 max3.9 b u al=center ls0.35` · `L 3.5,10.5,w47` · `Q sku 4.5,12,45,45` · `T "{sku}" 3.5,58,47,14 max9.5 b al=center ls0.3` · `L 3.5,89,w47` · `T "{client}" 3.5,89.5,47,6.5 max3 al=center`
col 2: `T "NAME" 55,3.5,43,7 max4 b u al=center ls0.35` · `L 55,10.5,w43` · `T "{name}" 55,12,43,20 max4.6 b wrap` · `T "NOTES" 55,35,43,7 max3.6 b u al=center ls0.35` · `L 55,42,w43` · `X 55,44,43,44 t0.3` · `L 55,58.6,w43` · `L 55,73.2,w43` · `T "{generated_date}" 55,90,43,6 max3 al=right`
col 3: `T "POS" 104,3,43.5,5.5 max3.2 b u al=center ls0.35` · `L 104,8.5,w43.5` · `Q position_data 115.75,9,20,20` · `T "{position_code}" 104,29,43.5,4.5 max3.4 b al=center` · `T "EXP" 104,34.5,43.5,5.5 max3.2 b u al=center ls0.35` · `L 104,40,w43.5` · `Q expiry 115.75,40.5,20,20` · `T "{expiry}" 104,60.5,43.5,4.5 max3.4 b al=center` · `T "LOT" 104,66,43.5,5.5 max3.2 b u al=center ls0.35` · `L 104,71.5,w43.5` · `Q batch 115.75,72,20,20` · `T "{batch}" 104,92,43.5,4.5 max3.4 b al=center`

**inventory/qr-sku-68x38mm** "QR-SKU 68x38mm" 68×38: `Q sku 2,4,30,30` · `T "{name}" 35,2,31,34 max5 b wrap`

**inventory/product-68x38** "Product 68x38mm" 68×38: `T "{name}" 2,1.5,64,11 max4.5 b wrap al=center` · `B sku 3,13.5,62,15` · `T "{sku}" 2,29.5,64,7 max5 b al=center ls0.2`

**inventory/pallet-150x100** "Pallet 150x100mm" 150×100: `X 1.5,1.5,147,97 t0.4` · `T "{sku}" 4,4,142,22 max18 min4 b al=center ls0.5` · `L 4,27,w142 t0.4` · `T "{name}" 4,29,95,22 max7 min3 b wrap` · `L v 101,29,h66 t0.3` · `T "QTY {quantity}" 4,54,95,12 max9 min3 b` · `T "LOT {batch}" 4,67,95,10 max6 min2.5` · `T "EXP {expiry}" 4,78,95,10 max6 min2.5` · `Q position_data 106,31,36,36` · `T "{position_code}" 103,68,43,10 max7 min2.5 b al=center` · `T "{generated_date}" 103,86,43,8 max3.5 al=right`

- [ ] **Step 1: Write the failing tests**
  - `test_shipped_layout_files_match_generate` parametrised over every `EXAMPLES_ROOT/{positions,inventory}/*/` folder: it **must** have `layout.json`, and each of the three files equals `generate(load_layout(folder))[name]`. Failure message: `"run: .venv/bin/python -m app.core.layout_builder"`.
  - In `tests/test_template_renderer.py`: `test_shipped_product_preset_scans_the_sku`: render "Product 68x38mm" with `{**INVENTORY_RECORD, "sku": "SKU-12345"}` → zxingcpp decodes `{"SKU-12345"}`. `test_shipped_pallet_preset_scans_the_position`: "Pallet 150x100mm" with `INVENTORY_RECORD` → `{"C002d002e"}`. Both check the image size like `:349`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Write the five `layout.json` files**, then run `.venv/bin/python -m app.core.layout_builder` to regenerate every shipped folder. Add a README section: builder presets carry `layout.json`; open them with Template > Edit… / Duplicate…; hand edits to a builder preset's HTML/CSS are lost on its next Save; presets without `layout.json` still work but can't be opened in the builder.
- [ ] **Step 4: Run** `tests/test_layout_builder.py`, `tests/test_template_renderer.py`, `tests/test_thermal_safe.py`, `tests/test_black_area.py`. Expected: all PASS, including the existing default/QR-SKU scan tests and the thermal check over all five folders. If an existing scan test fails, adjust that preset's layout coordinates (not the test), regenerate and rerun. `tests/test_black_area.py` edits the positions default CSS by string replace; if it breaks, update that test's replacement to the new CSS while keeping what it proves.
- [ ] **Step 5: Commit** `feat: shipped thermal presets as builder layouts + product and pallet presets`.

---

### Task 4: One label per unit (Qty)

**Files:**
- Modify: `app/ui/mode_inventory_panel.py` (`__init__` widgets/layout, `_on_print_clicked` `:252`, `print_checked_items` `:299`)
- Test: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Produces: `InventoryModePanel.one_per_unit_checkbox: QCheckBox` ("One label per unit (Qty)"), `InventoryModePanel._items_to_print() -> list[InventoryItem]`.

- [ ] **Step 1: Write the failing tests** (add `monkeypatch.setattr("app.ui.mode_inventory_panel.qsettings", lambda: store)` to the existing `_isolated_settings_dir` fixture so both modules share the tmp store):
  - `test_one_label_per_unit_off_by_default_prints_one_per_row`: two checked rows qty 3 and 2 → `len(panel._items_to_print()) == 2`.
  - `test_one_label_per_unit_repeats_each_item_by_quantity_in_order`: checkbox on → skus `[A, A, A, B, B]`; `print_checked_items` renders 5 records (monkeypatch `render_labels` to capture).
  - `test_one_label_per_unit_is_remembered`: toggle on, build a new panel → checked.
  - `test_one_label_per_unit_cap_applies_to_the_expanded_total`: qty 1500 and 600, on → `_on_print_clicked` shows the cap warning (monkeypatch `QMessageBox.warning` to capture) and never constructs `PrintPreviewDialog`.
- [ ] **Step 2: Run** `tests/test_mode_inventory_panel.py`. Expected: new tests FAIL.
- [ ] **Step 3: Implement.** Import `qsettings` from `app.core.config`. Checkbox placed under the Template row; initial state `qsettings().value("inventory/one_label_per_unit", False, type=bool)`; `toggled` writes it back. `_items_to_print` = `checked_items()` or, when the box is on, each item repeated `item.quantity` times. Replace `checked` with `_items_to_print()` in `_on_print_clicked` (count check, `count=`, `render_page`, status message) and in `print_checked_items` (records). Keep `_describe_skus` fed from the same list (it dedupes).
- [ ] **Step 4: Run** the file + ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: one label per unit (Qty) in inventory mode`.

---

### Task 5: Builder dialog — canvas, palette, move/resize, undo

**Files:**
- Create: `app/ui/template_builder.py`
- Test: `tests/test_template_builder.py`

**Interfaces:**
- Consumes: Task 1 `normalise_layout`, `default_element`, `ELEMENT_TYPES`; Task 2 `sample_for`.
- Produces (Tasks 6–8 build on these exact names):
  - `class TemplateBuilderDialog(QDialog)`, `__init__(self, layout: dict, shared_folder: Path, *, edit_folder: Path | None = None, sample: dict | None = None, parent=None)`
  - attributes: `layout: dict` (current, normalised), `selected: int | None`, `scene: QGraphicsScene`, `view` (a `QGraphicsView` subclass `_Canvas`), `items: list[ElementItem]`, `dirty: bool`, `saved_name: str | None = None`, `shared_folder`, `edit_folder`, `sample` (= `sample_for(mode, sample)`)
  - methods: `add_element(type_: str) -> int`, `select(index: int | None) -> None`, `set_geometry(index: int, x: float, y: float, w: float, h: float) -> None`, `update_element(index: int, **props) -> None`, `move_selected(dx: float, dy: float) -> None`, `delete_selected() -> None`, `undo() -> None`, `set_label_size(w: float, h: float) -> None`, `_commit(new_layout: dict) -> None`, `_rebuild_scene() -> None`
  - `class ElementItem(QGraphicsRectItem)` with `index: int` and `commit_drag() -> None`; `class _ResizeHandle(QGraphicsRectItem)` with `commit_resize() -> None`.

- [ ] **Step 1: Write the failing tests** (`_app()` helper as in other UI tests; layout from `new_layout("inventory")`):
  - `test_add_element_appends_default_and_selects`: `add_element("qr")` → index 0, `layout["elements"][0]["field"] == "sku"`, `selected == 0`, `dirty`.
  - `test_drag_snaps_to_1mm`: add text, `dlg.items[0].setPos(10.4, 5.6)`, `dlg.items[0].commit_drag()` → `x_mm == 10`, `y_mm == 6`.
  - `test_resize_handle_snaps_and_keeps_min_1mm`: drive `_ResizeHandle` to (w 12.7, h 0.2) then `commit_resize()` → `w_mm == 13`, `h_mm == 1`; on a horizontal line only `w_mm` changes and `h_mm` stays 0.
  - `test_nudge_moves_half_a_mm_and_clamps_at_0`: `move_selected(0.5, -5)` from (2, 2) → (2.5, 0).
  - `test_arrow_and_delete_keys_on_canvas`: `QTest.keyClick(dlg.view, Qt.Key_Right)` → +0.5; `Qt.Key_Delete` → element gone, `selected is None`.
  - `test_undo_restores_each_previous_state`: add, move, delete, then `undo()` ×3 → back to empty; extra `undo()` is a no-op.
  - `test_scene_is_in_mm`: `set_label_size(68, 38)` → `dlg.scene.sceneRect()` covers `QRectF(0, 0, 68, 38)`.
- [ ] **Step 2: Run** `tests/test_template_builder.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Layout: `QHBoxLayout` of the palette (`QVBoxLayout` of five `QPushButton`s, "Text", "Barcode", "QR", "Box", "Line" → `add_element`), the canvas, and a right-hand `QWidget` placeholder `self.properties_panel` that Task 6 fills. Top bar is a `QHBoxLayout` `self.top_bar` that Task 6 fills. `setWindowTitle("Template builder")`, `Qt.WindowMaximizeButtonHint`.
  - Scene: 1 unit = 1 mm. Background item: a white `QGraphicsRectItem(0, 0, W, H)` over the view's grey background (`#9aa0a6`); a 1 mm grid (`#e8e8e8`, cosmetic 0 px pen) and every 10 mm (`#c8c8c8`); a dashed guide inset 1.25 mm (`#d0021b`, cosmetic) for the thermal safe margin. `view.fitInView(sceneRect + 5 mm margin, Qt.KeepAspectRatio)` on rebuild and in `resizeEvent`.
  - `_commit(new_layout)`: push `json.dumps(self.layout)` onto `self._undo`, set `self.layout = normalise_layout(new_layout)`, `dirty = True`, `_rebuild_scene()`, reselect (clamped). Every mutator builds a deep copy and calls `_commit`. `undo()` pops and rebuilds without pushing.
  - `ElementItem`: movable/selectable rect at `(x, y)` with `(w, h)` (lines: thickness on the off axis). Paint: text = content in "JetBrains Mono" at `max_mm`, bold per prop, clipped to the rect; barcode/QR = `Qt.BDiagPattern` hatch + the field name; box = outline at thickness; line = filled thickness bar. Selected → accent outline `#1a73e8`. `mousePressEvent` → `dialog.select(index)`; `mouseReleaseEvent` → `commit_drag()` which calls `set_geometry(index, round(pos.x()), round(pos.y()), w, h)` (clamped ≥ 0).
  - `_ResizeHandle`: 2×2 mm accent square child at the parent's bottom-right, only on the selected item; drag changes the parent rect live; `commit_resize()` → `set_geometry` with `max(1, round(w))` / `max(1, round(h))` (a line only changes its length).
  - `_Canvas.keyPressEvent`: arrows → `move_selected(±0.5, …)`, Delete/Backspace → `delete_selected()`, else `super()`. A `QShortcut(QKeySequence.Undo, self, self.undo)` on the dialog.
- [ ] **Step 4: Run** the file + ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: template builder canvas with drag, resize, nudge and undo`.

---

### Task 6: Builder dialog — properties panel and top bar

**Files:**
- Modify: `app/ui/template_builder.py`
- Test: `tests/test_template_builder.py`

**Interfaces:**
- Consumes: Task 5's `TemplateBuilderDialog` methods; Task 1 `mode_fields`.
- Produces: widgets `name_edit: QLineEdit`, `size_combo: QComboBox`, `width_spin`, `height_spin: QDoubleSpinBox`, `undo_button`, plus per-selection property widgets kept in `self.prop_widgets: dict[str, QWidget]`. Keys: `x_mm, y_mm, w_mm, h_mm, content, insert_field, max_mm, min_mm, wrap, bold, uppercase, align, letter_spacing_mm, field, thickness_mm, orientation`. `SIZES = [(150, 100), (100, 150), (100, 100), (100, 50), (68, 38), (58, 40), (50, 30)]`.

- [ ] **Step 1: Write the failing tests**
  - `test_name_edit_sets_layout_name`.
  - `test_size_combo_preset_and_custom`: picking "68 × 38 mm" → layout 68×38 and the spins show it; editing `width_spin` to 70 → combo shows "Custom" and the layout is 70 wide.
  - `test_properties_show_only_the_selected_type`: select a QR → `"field" in prop_widgets` and `"content" not in prop_widgets`; the field combo items are exactly `mode_fields("inventory")`.
  - `test_property_edit_updates_layout_and_is_undoable`: text selected, `prop_widgets["bold"].setChecked(True)` → `bold is True`; `undo()` → False.
  - `test_insert_field_appends_placeholder`: choose `batch` in `insert_field` → content ends with `{batch}`.
  - `test_unknown_placeholder_typed_in_content_is_not_committed`: typing `{nope}` shows an inline error label and leaves the layout unchanged (validation is `normalise_layout`'s `ValueError`).
  - `test_mode_is_shown_read_only`: a `QLabel` with "Mode: inventory".
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Top bar: `Name [name_edit]`, `QLabel(f"Mode: {mode}")`, `size_combo` (`"W × H mm"` items + `"Custom"`), `width_spin`/`height_spin` (10–300, step 1), then (Task 7) Preview/Save, and `undo_button` ("Undo"). Properties: rebuilt on `select()` in a `QFormLayout`. X/Y/W/H `QDoubleSpinBox` step 0.5 (lines hide the off-axis one), then per type per the spec. Commit on `editingFinished` for line edits/spin boxes and on change for checkboxes and combos. While rebuilding the panel, block signals. A `ValueError` from `_commit` goes to a red `QLabel` under the form instead of being raised. A "Delete" button calls `delete_selected`. Empty selection shows "Click an element, or add one from the left."
- [ ] **Step 4: Run** the file + ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: template builder properties panel and size bar`.

---

### Task 7: Builder dialog — Preview, Save, close guard

**Files:**
- Modify: `app/ui/template_builder.py`
- Test: `tests/test_template_builder.py`

**Interfaces:**
- Consumes: Task 2 `render_sample`, `black_block_mm`, `check_save_target`, `save_layout`.
- Produces: `preview_button: QPushButton` (checkable, "Preview"), `save_button` ("Save template"), `status_label: QLabel`, `set_preview(on: bool) -> None`, `save() -> Path | None`. After a successful save, `saved_name` is the layout name and the dialog is accepted.

- [ ] **Step 1: Write the failing tests** (patch `app.ui.template_builder.QMessageBox` methods; never a real modal):
  - `test_preview_shows_the_rendered_bitmap_and_locks_editing`: with one QR, `set_preview(True)` → a `QGraphicsPixmapItem` in the scene whose bounding rect matches the label in mm (±0.2), element items hidden, the palette buttons disabled; `set_preview(False)` restores.
  - `test_preview_error_goes_to_status_line`: barcode on field `name` with sample `{"name": "Гвинт"}` → `status_label` text non-empty, `preview_button.isChecked()` False, no exception.
  - `test_save_writes_folder_and_accepts(tmp_path)`: name "My label", one QR → `save()` returns `tmp_path/"templates"/"inventory"/"my-label"`, the four files exist, `saved_name == "My label"`, `result() == QDialog.Accepted`.
  - `test_save_refuses_app_owned_name(tmp_path)`: name "Default" → warning shown, returns `None`, nothing written.
  - `test_save_warns_on_black_block_and_respects_cancel(tmp_path)`: stacked lines; `question` returns `No` → `None`, nothing written; returns `Yes` → written.
  - `test_save_with_empty_name_is_refused`.
  - `test_close_with_unsaved_changes_asks(tmp_path)`: dirty dialog, `question` → `No` → `reject()` does not close (`result()` unchanged / `isVisible` kept); clean dialog closes without asking.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** `set_preview(True)`: `render_sample(self.layout, self.sample)`. On `(ValueError, OSError, BarcodeError)` (`from barcode.errors import BarcodeError`) put `f"Preview failed: {error}"` in `status_label`, uncheck and return. Else convert with `PIL.ImageQt.ImageQt(image.convert("L"))` → `QPixmap`, add a `QGraphicsPixmapItem` scaled by `width_mm / image.width`, hide the element items, and disable the palette, properties and top-bar size controls. `save()`: `name.strip()` empty → warning "Give the template a name first."; `check_save_target` / render errors → `QMessageBox.warning(self, "Can't save template", str(error))`; `black_block_mm` hit → `QMessageBox.question(self, "Solid black area", f"The label has a solid black area at x={x} mm, y={y} mm. Large black areas leave residue on the thermal print head. Save anyway?", Yes | No, No)`; then `save_layout`, `saved_name`, `dirty = False`, `accept()`. Override `reject()` (covers Esc and the close button through `closeEvent`) to ask "Discard unsaved changes?" when `dirty`.
- [ ] **Step 4: Run** the file + ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: template builder preview and save`.

---

### Task 8: Open the builder from the mode panels

**Files:**
- Modify: `app/ui/mode_panel.py` (template button + `open_builder`)
- Modify: `app/ui/mode_positions_panel.py` (Template row, `_record_for_code` extraction around `:231-240`, `sample_record`)
- Modify: `app/ui/mode_inventory_panel.py` (Template row, `sample_record`)
- Test: `tests/test_mode_positions_panel.py`, `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: Task 5–7 `TemplateBuilderDialog(layout, shared_folder, *, edit_folder, sample, parent)`, `.saved_name`; Task 1 `new_layout`; Task 2 `load_layout`, `is_app_owned`.
- Produces: `ModePanel.template_button: QToolButton` ("Template", `InstantPopup`) with actions `new_action` "New…", `edit_action` "Edit…", `duplicate_action` "Duplicate…"; `ModePanel._template_row() -> QWidget` (combo + button in an `QHBoxLayout`); `ModePanel.open_builder(kind: str) -> None` (`"new" | "edit" | "duplicate"`); `ModePanel._update_template_actions() -> None`; subclasses' `sample_record() -> dict | None`.

- [ ] **Step 1: Write the failing tests** (in both panel test files; monkeypatch `app.ui.mode_panel.TemplateBuilderDialog` with a fake that records its args and whose `exec()` sets `saved_name` and returns 1):
  - `test_template_actions_enabled_for_builder_presets_only`: selecting the shipped "Default 150x100mm" → Edit disabled (app-owned), Duplicate enabled; a hand-written preset (from `_write_preset`, no `layout.json`) → both disabled; a user builder preset → both enabled. New is always enabled.
  - `test_new_opens_builder_in_panel_mode_and_selects_saved_preset`: fake saves a real preset via `save_layout` named "Mine" → after `open_builder("new")` the combo's current text is "Mine".
  - `test_duplicate_passes_copy_name_and_no_edit_folder`: layout name "Copy of Default 150x100mm", `edit_folder is None`.
  - `test_edit_passes_the_preset_folder`.
  - `test_broken_layout_json_shows_warning`: invalid `layout.json` → `QMessageBox.warning` called, no dialog built.
  - Inventory `test_sample_record_uses_first_checked_item`; positions `test_sample_record_uses_first_generated_code`; both return `None` with no data.
- [ ] **Step 2: Run** both files. Expected: FAIL.
- [ ] **Step 3: Implement.** In each panel replace `form.addRow("Template", self.preset_combo)` with `form.addRow("Template", self._template_row())`. `_update_template_actions` runs on the menu's `aboutToShow` and on combo changes: the folder is `preset.template_path.parent`; builder = `(folder / "layout.json").exists()`. `open_builder`: new → `new_layout(self.MODE)`; edit/duplicate → `load_layout(folder)` (on `ValueError` show `QMessageBox.warning(self, "Can't open template", str(error))` and return); duplicate sets `name = f"Copy of {name}"`. Build `TemplateBuilderDialog(layout, shared_folder(self._settings), edit_folder=folder if edit else None, sample=self.sample_record(), parent=self)`; on `exec()` true with a `saved_name`: `qsettings().setValue(f"{self.MODE}/last_template", saved_name)` and `refresh_from_settings(self._settings)`. Positions: move the record dict at `:231-240` into a module-level `_record_for_code(code, warehouse_prefix, user_text) -> dict` used by `_render_labels`; `sample_record()` uses `generated_codes[0]` with `_generated_warehouse` and the custom text. Inventory: first of `checked_items()`, else the table's row 0 item, via `_record_for_item(item, warehouse_combo.currentData() or "", today)`.
- [ ] **Step 4: Run** both panel files, `tests/test_main_window.py`, and ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: open the template builder from the mode panels`.

---

## Final check (after Task 8)

Run each test file separately (`for f in tests/test_*.py; do QT_QPA_PLATFORM=offscreen .venv/bin/pytest "$f" -q || echo "FAIL $f"; done`) and `ruff check .`. All green.
