# blabel Template Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-coded PIL pixel-math label renderer with HTML/CSS
template presets rendered through blabel (Jinja2 + WeasyPrint), so label
layouts can be designed and iterated on as files instead of Python code.

**Architecture:** A new `app/core/template_renderer.py` discovers named
template presets (`template.html` + `style.css` + `meta.json`) from
`<shared_folder>/templates/<mode>/<preset>/`, feeds per-label data dicts
through `blabel.LabelWriter` to get a PDF, and rasterizes each PDF page to a
`PIL.Image` via `pypdfium2` at the same DPI convention the app already uses.
Everything downstream of that (`print_service.py`, `zpl_print_service.py`,
audit log, PDF archive/debug-preview) is untouched — it already consumes
`list[PIL.Image]`.

**Tech Stack:** Python, PySide6, blabel (Jinja2 + WeasyPrint), pypdfium2,
pytest.

Design doc: `docs/superpowers/specs/2026-08-02-blabel-template-presets-design.md`

## Global Constraints

- App code and comments are English-only (existing project convention).
- No emojis anywhere in code, UI, or commit messages.
- blabel pulls in WeasyPrint; on Windows this needs the GTK3/Pango native
  libraries. Confirmed acceptable for this internal tool (one-time
  per-machine setup) — do not attempt to avoid this dependency.
- CI (`.github/workflows/ci.yml`) runs the full test suite on both
  `ubuntu-latest` and `windows-latest`. Any dependency added here must work
  on both, including native library setup.
- Template presets live under `<shared_folder>/templates/<mode>/<preset>/`
  (the same shared folder already used for the audit log and printed-PDF
  archive), not bundled inside the app. This is a deliberate deviation from
  the original "configurable custom size" idea in
  `Essential technical specifications.txt` §2.1 — a custom size is now "add
  a new preset folder" rather than a separate size-only setting.
- The per-mode "Orientation" combo (Landscape/Portrait swap) is removed —
  confirmed during design review, since blindly swapping `@page` dimensions
  on a hand-authored CSS layout can break it rather than rotate it cleanly.
- Rendering DPI default stays 203 (matches the thermal-printer convention
  the old `mm_to_px` used).

---

### Task 1: Add blabel/pypdfium2 dependencies and fix Windows CI for WeasyPrint

**Files:**
- Modify: `requirements.txt`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `blabel` and `pypdfium2` importable in the app's environment on
  both Linux and Windows (including CI).

- [ ] **Step 1: Add the new dependencies to `requirements.txt`**

Insert after the `zebrafy>=1.2` line (before the `pywin32` platform-conditional
line):

```
blabel>=0.3
pypdfium2>=4.0
```

Full resulting file:

```
PySide6>=6.7
python-barcode>=0.15
qrcode>=7.4
Pillow>=10.1.0
zebrafy>=1.2
blabel>=0.3
pypdfium2>=4.0
pywin32>=306; sys_platform == "win32"
pytest>=8.0
ruff>=0.6
```

- [ ] **Step 2: Fix Windows CI so `import blabel` doesn't fail on missing native libs**

WeasyPrint (pulled in by blabel) needs Pango/Cairo/GDK-Pixbuf native
libraries on Windows — `pip install` alone doesn't provide them. GitHub's
`windows-latest` runner image ships MSYS2 pre-installed at `C:\msys64`, so
install the missing package from there and point WeasyPrint at the
resulting DLL directory for the rest of the job.

Edit `.github/workflows/ci.yml` — add a new step between the existing
"Install Qt runtime libraries (Linux)" step and the `pip install` step:

```yaml
      - name: Install Pango for WeasyPrint (Windows)
        if: runner.os == 'Windows'
        shell: cmd
        run: |
          C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-x86_64-pango
          echo WEASYPRINT_DLL_DIRECTORIES=C:\msys64\mingw64\bin>> %GITHUB_ENV%
```

Full resulting `test` job:

```yaml
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install Qt runtime libraries (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1 libxkbcommon0 libxcb-cursor0
      - name: Install Pango for WeasyPrint (Windows)
        if: runner.os == 'Windows'
        shell: cmd
        run: |
          C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-x86_64-pango
          echo WEASYPRINT_DLL_DIRECTORIES=C:\msys64\mingw64\bin>> %GITHUB_ENV%
      - run: pip install -r requirements.txt
      - run: pytest -v
```

(The `lint` job is untouched.)

- [ ] **Step 3: Verify locally on this Linux dev machine**

Run: `pip install -r requirements.txt && python -c "import blabel; import pypdfium2; print('ok')"`
Expected: prints `ok` with no errors. (This only proves the Linux path —
the Windows native-library path can only be verified by CI, which is why
step 5 below checks the actual Actions run rather than a local repro.)

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .github/workflows/ci.yml
git commit -m "build: add blabel/pypdfium2 deps, fix Windows CI for WeasyPrint"
```

- [ ] **Step 5: Push and verify both CI matrix legs go green**

Push the branch and check the GitHub Actions run for this commit. Both
`ubuntu-latest` and `windows-latest` legs of the `test` job must pass (they
just run the existing, unmodified test suite — nothing consumes blabel yet,
so this only proves the dependency installs and imports cleanly on both
OSes). If `windows-latest` fails on the Pango step or on `pytest` importing
blabel, check the job log for the actual pacman/DLL error before proceeding
to Task 2.

---

### Task 2: `TemplatePreset` + preset discovery with example-template seeding

**Files:**
- Create: `app/core/template_renderer.py`
- Create: `app/templates/examples/positions/default/meta.json`
- Create: `app/templates/examples/positions/default/template.html`
- Create: `app/templates/examples/positions/default/style.css`
- Create: `app/templates/examples/inventory/default/meta.json`
- Create: `app/templates/examples/inventory/default/template.html`
- Create: `app/templates/examples/inventory/default/style.css`
- Test: `tests/test_template_renderer.py`

**Interfaces:**
- Produces: `TemplatePreset` dataclass (`name`, `mode`, `width_mm`,
  `height_mm`, `template_path`, `stylesheet_path`); `list_presets(shared_folder: Path, mode: str) -> list[TemplatePreset]`.
  Both are consumed by Task 3 (`render_records`) and Tasks 4/5 (the UI panels).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_template_renderer.py`:

```python
import json

from app.core.template_renderer import list_presets


def test_list_presets_seeds_examples_into_empty_shared_folder(tmp_path):
    presets = list_presets(tmp_path, "positions")

    assert len(presets) == 1
    assert presets[0].name == "Default 100x50mm"
    assert presets[0].width_mm == 100
    assert presets[0].height_mm == 50
    assert (tmp_path / "templates" / "positions" / "default" / "template.html").exists()


def test_list_presets_seeds_inventory_examples_too(tmp_path):
    presets = list_presets(tmp_path, "inventory")

    assert len(presets) == 1
    assert presets[0].name == "Default 150x100mm"


def test_list_presets_returns_existing_presets_without_reseeding(tmp_path):
    mode_dir = tmp_path / "templates" / "inventory" / "custom"
    mode_dir.mkdir(parents=True)
    (mode_dir / "meta.json").write_text(
        json.dumps({"name": "Custom", "width_mm": 80, "height_mm": 80})
    )
    (mode_dir / "template.html").write_text("<div>{{ sku }}</div>")
    (mode_dir / "style.css").write_text("@page { size: 80mm 80mm; }")

    presets = list_presets(tmp_path, "inventory")

    assert [p.name for p in presets] == ["Custom"]
    assert not (tmp_path / "templates" / "inventory" / "default").exists()


def test_list_presets_lists_multiple_presets_sorted_by_folder_name(tmp_path):
    for slug, name in (("b_preset", "B"), ("a_preset", "A")):
        mode_dir = tmp_path / "templates" / "positions" / slug
        mode_dir.mkdir(parents=True)
        (mode_dir / "meta.json").write_text(
            json.dumps({"name": name, "width_mm": 50, "height_mm": 50})
        )
        (mode_dir / "template.html").write_text("<div></div>")
        (mode_dir / "style.css").write_text("@page { size: 50mm 50mm; }")

    presets = list_presets(tmp_path, "positions")

    assert [p.name for p in presets] == ["A", "B"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_template_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.template_renderer'`

- [ ] **Step 3: Create the example templates that get seeded**

Create `app/templates/examples/positions/default/meta.json`:

```json
{"name": "Default 100x50mm", "width_mm": 100, "height_mm": 50}
```

Create `app/templates/examples/positions/default/template.html`:

```html
<div class="label">
  <img class="barcode" src="{{ label_tools.barcode(barcode_data) }}">
  <div class="caption">{{ visible_text }}</div>
</div>
```

Create `app/templates/examples/positions/default/style.css`:

```css
@page { size: 100mm 50mm; margin: 0; }
body { margin: 0; }
.label {
  box-sizing: border-box;
  width: 100mm;
  height: 50mm;
  padding: 4mm;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2mm;
  font-family: sans-serif;
}
.barcode {
  max-width: 100%;
  max-height: 70%;
  object-fit: contain;
}
.caption {
  font-size: 6mm;
  text-align: center;
}
```

Create `app/templates/examples/inventory/default/meta.json`:

```json
{"name": "Default 150x100mm", "width_mm": 150, "height_mm": 100}
```

Create `app/templates/examples/inventory/default/template.html`:

```html
<div class="label">
  <div class="col">
    <img class="qr" src="{{ label_tools.qr_code(sku) }}">
    <div class="caption">{{ sku }}</div>
  </div>
  <div class="col mid">
    <div class="name">{{ name }}</div>
    {% if client %}<div>{{ client }}</div>{% endif %}
    {% if batch %}<div>Batch: {{ batch }}</div>{% endif %}
    {% if expiry %}<div>Expiry: {{ expiry }}</div>{% endif %}
    <div class="date">{{ generated_date }}</div>
  </div>
  <div class="col">
    <img class="qr" src="{{ label_tools.qr_code(position_data) }}">
    <div class="caption">{{ position_code }}</div>
  </div>
</div>
```

Create `app/templates/examples/inventory/default/style.css`:

```css
@page { size: 150mm 100mm; margin: 0; }
body { margin: 0; }
.label {
  box-sizing: border-box;
  width: 150mm;
  height: 100mm;
  padding: 4mm;
  display: flex;
  flex-direction: row;
  font-family: sans-serif;
}
.col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2mm;
}
.mid {
  justify-content: flex-start;
  text-align: center;
}
.qr {
  max-width: 90%;
  max-height: 60%;
  object-fit: contain;
}
.caption { font-size: 5mm; }
.name { font-weight: bold; font-size: 6mm; }
.date { font-size: 3mm; margin-top: auto; }
```

- [ ] **Step 4: Implement `TemplatePreset` and `list_presets`**

Create `app/core/template_renderer.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "templates" / "examples"


@dataclass(frozen=True)
class TemplatePreset:
    name: str
    mode: str
    width_mm: float
    height_mm: float
    template_path: Path
    stylesheet_path: Path


def list_presets(shared_folder: Path, mode: str) -> list[TemplatePreset]:
    mode_dir = Path(shared_folder) / "templates" / mode
    if not mode_dir.exists() or not any(mode_dir.iterdir()):
        _seed_examples(mode_dir, mode)

    presets = []
    for preset_dir in sorted(p for p in mode_dir.iterdir() if p.is_dir()):
        meta_path = preset_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        presets.append(
            TemplatePreset(
                name=meta["name"],
                mode=mode,
                width_mm=meta["width_mm"],
                height_mm=meta["height_mm"],
                template_path=preset_dir / "template.html",
                stylesheet_path=preset_dir / "style.css",
            )
        )
    return presets


def _seed_examples(mode_dir: Path, mode: str) -> None:
    example_dir = EXAMPLES_ROOT / mode / "default"
    if not example_dir.exists():
        return
    target_dir = mode_dir / "default"
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("template.html", "style.css", "meta.json"):
        (target_dir / filename).write_text(
            (example_dir / filename).read_text(encoding="utf-8"), encoding="utf-8"
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_template_renderer.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add app/core/template_renderer.py app/templates/examples tests/test_template_renderer.py
git commit -m "feat: add template preset discovery with example-template seeding"
```

---

### Task 3: `render_records` — blabel + pypdfium2 rendering pipeline

**Files:**
- Modify: `app/core/template_renderer.py`
- Create: `tests/fixtures/templates/sample/template.html`
- Create: `tests/fixtures/templates/sample/style.css`
- Modify: `tests/test_template_renderer.py`

**Interfaces:**
- Consumes: `TemplatePreset` from Task 2.
- Produces: `render_records(preset: TemplatePreset, records: list[dict], dpi: int = 203) -> list[PIL.Image.Image]`,
  one image per record, in the same order. Consumed by Tasks 4 and 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/fixtures/templates/sample/template.html`:

```html
<div class="label">
  <img src="{{ label_tools.qr_code(code) }}">
  <div class="caption">{{ label }}</div>
</div>
```

Create `tests/fixtures/templates/sample/style.css`:

```css
@page { size: 40mm 30mm; margin: 0; }
body { margin: 0; }
.label {
  box-sizing: border-box;
  width: 40mm;
  height: 30mm;
}
```

Append to `tests/test_template_renderer.py`:

```python
from pathlib import Path

from PIL import Image

from app.core.template_renderer import TemplatePreset, render_records

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "templates" / "sample"


def _sample_preset() -> TemplatePreset:
    return TemplatePreset(
        name="Sample",
        mode="test",
        width_mm=40,
        height_mm=30,
        template_path=FIXTURE_DIR / "template.html",
        stylesheet_path=FIXTURE_DIR / "style.css",
    )


def test_render_records_returns_one_image_per_record():
    images = render_records(
        _sample_preset(),
        [{"code": "A1", "label": "A1"}, {"code": "A2", "label": "A2"}],
    )

    assert len(images) == 2
    assert all(isinstance(img, Image.Image) for img in images)


def test_render_records_image_size_matches_preset_mm_at_dpi():
    images = render_records(_sample_preset(), [{"code": "A1", "label": "A1"}], dpi=203)

    expected_width = round(40 / 25.4 * 203)
    expected_height = round(30 / 25.4 * 203)
    assert abs(images[0].width - expected_width) <= 1
    assert abs(images[0].height - expected_height) <= 1


def test_render_records_output_reflects_record_data():
    img_a = render_records(_sample_preset(), [{"code": "A1", "label": "A1"}])[0]
    img_b = render_records(_sample_preset(), [{"code": "A2", "label": "A2"}])[0]

    assert img_a.tobytes() != img_b.tobytes()
```

(Note: this appended block has its own `from pathlib import Path` /
`from PIL import Image` imports — when combining with Task 2's version of
the file, de-duplicate imports at the top instead of repeating them.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_template_renderer.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_records'`

- [ ] **Step 3: Implement `render_records`**

Edit `app/core/template_renderer.py` — add these imports at the top
(alongside the existing `json`/`dataclass`/`Path` imports):

```python
from blabel import LabelWriter
from PIL import Image
import pypdfium2 as pdfium
```

Add at the end of the file:

```python
def render_records(
    preset: TemplatePreset,
    records: list[dict],
    dpi: int = 203,
) -> list[Image.Image]:
    writer = LabelWriter(
        str(preset.template_path),
        default_stylesheets=(str(preset.stylesheet_path),),
        items_per_page=1,
    )
    pdf_bytes = writer.write_labels(records, target="@memory")

    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    for page in pdf:
        bitmap = page.render(scale=dpi / 72)
        images.append(bitmap.to_pil().convert("RGB"))
    return images
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_template_renderer.py -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Commit**

```bash
git add app/core/template_renderer.py tests/test_template_renderer.py tests/fixtures
git commit -m "feat: render template presets to images via blabel + pypdfium2"
```

---

### Task 4: Wire `PositionsModePanel` to template presets

**Files:**
- Modify: `app/ui/mode_positions_panel.py`
- Modify: `tests/test_mode_positions_panel.py`
- Modify: `tests/test_main_window.py`

**Interfaces:**
- Consumes: `TemplatePreset`, `list_presets`, `render_records` from
  `app.core.template_renderer` (Tasks 2-3).
- Produces: `PositionsModePanel.preset_combo` (replaces `label_size_combo`);
  `PositionsModePanel` no longer has `orientation_combo` or `label_size_combo`.

**Note on why `test_main_window.py` is in scope:** `MainWindow.__init__`
constructs `PositionsModePanel(self._settings)` where `self._settings` comes
from the real `default_settings_path()` unless a test patches it. Today that's
harmless (`label_size_combo` only reads an in-memory list), but once
`refresh_from_settings` calls `list_presets` — which can *write* seeded
example templates to disk — unpatched `MainWindow()` tests would start
writing into the developer's real `~/.barcode_tool` directory. This task
fixes that alongside the panel wiring it's caused by.

- [ ] **Step 1: Rewrite the test files first**

Replace `tests/test_mode_positions_panel.py` in full:

```python
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.mode_positions_panel import ArchiveError, PositionsModePanel

SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
}


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # Prevents the shared_folder="" fallback path from touching the real
    # ~/.barcode_tool directory (and seeding example templates into it)
    # during tests.
    monkeypatch.setattr(
        "app.ui.mode_positions_panel.default_settings_path",
        lambda: tmp_path / "settings.json",
    )


def _write_preset(
    shared_folder: Path, mode: str, slug: str, name: str, width_mm: float, height_mm: float
) -> None:
    preset_dir = Path(shared_folder) / "templates" / mode / slug
    preset_dir.mkdir(parents=True)
    (preset_dir / "meta.json").write_text(
        json.dumps({"name": name, "width_mm": width_mm, "height_mm": height_mm})
    )
    (preset_dir / "template.html").write_text(
        '<div><img src="{{ label_tools.barcode(barcode_data) }}">'
        "<div>{{ visible_text }}</div></div>"
    )
    (preset_dir / "style.css").write_text(
        f"@page {{ size: {width_mm}mm {height_mm}mm; margin: 0; }}"
    )


def test_generate_produces_expected_codes_and_labels():
    _app()
    panel = PositionsModePanel(SETTINGS)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")

    results = panel.generate()

    assert [code for code, _ in results] == ["H029", "H030"]
    assert panel.result_label.text() == "2 labels generated"
    assert len(panel.generated_labels) == 2


def test_generate_single_position_without_number_to():
    _app()
    panel = PositionsModePanel(SETTINGS)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")

    results = panel.generate()

    assert [code for code, _ in results] == ["H029"]


def test_corridor_field_rejects_non_letter_input():
    _app()
    panel = PositionsModePanel(SETTINGS)

    panel.corridor_edit.insert("1")  # simulates typing, unlike setText()

    assert panel.corridor_edit.text() == ""


def test_corridor_field_accepts_single_letter():
    _app()
    panel = PositionsModePanel(SETTINGS)

    panel.corridor_edit.insert("H")
    panel.corridor_edit.insert("X")  # second letter must be rejected (maxLength=1)

    assert panel.corridor_edit.text() == "H"


def test_number_from_field_rejects_value_above_max():
    _app()
    panel = PositionsModePanel(SETTINGS)

    panel.number_from_edit.insert("1000")

    assert panel.number_from_edit.text() == ""


def test_invalid_range_raises_value_error():
    _app()
    panel = PositionsModePanel(SETTINGS)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("090")
    panel.number_to_edit.setText("029")

    with pytest.raises(ValueError):
        panel.generate()


def test_print_current_labels_writes_pdf_and_log(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.generate()

    pdf_path = tmp_path / "out.pdf"
    panel.print_current_labels(output_pdf_path=pdf_path)

    assert pdf_path.exists()
    log_path = tmp_path / "audit_log.csv"
    log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 2  # header + one entry
    assert log_lines[1].split(",")[2:] == ["positions", "C001", "2", "H029..H030"]


def test_generate_without_preset_raises_value_error(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr("app.ui.mode_positions_panel.list_presets", lambda *a, **k: [])
    settings = {**SETTINGS, "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")

    with pytest.raises(ValueError):
        panel.generate()


def test_print_button_click_invokes_print_current_labels(monkeypatch):
    _app()
    panel = PositionsModePanel(SETTINGS)
    calls = []
    monkeypatch.setattr(panel, "print_current_labels", lambda: calls.append(True))

    panel.print_button.click()

    assert calls == [True]


def test_print_button_click_without_generated_labels_shows_warning(monkeypatch):
    _app()
    panel = PositionsModePanel(SETTINGS)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert len(warnings) == 1


def test_print_current_labels_falls_back_to_settings_dir_when_shared_folder_empty(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": ""}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.generate()

    panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    assert (tmp_path / "audit_log.csv").exists()


def test_print_uses_preset_from_generate_time_not_live_combo(monkeypatch, tmp_path):
    _app()
    _write_preset(tmp_path, "positions", "a", "68x38mm", 68, 38)
    _write_preset(tmp_path, "positions", "b", "80x80mm", 80, 80)
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.preset_combo.setCurrentIndex(0)  # 68x38mm
    panel.generate()

    panel.preset_combo.setCurrentIndex(1)  # user changes template after Generate

    calls = []
    monkeypatch.setattr(
        "app.ui.mode_positions_panel.send_to_printer",
        lambda *a, **k: calls.append(k),
    )
    panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    assert calls[0]["width_mm"] == 68
    assert calls[0]["height_mm"] == 38


def test_generate_from_rows_builds_labels_from_components():
    _app()
    panel = PositionsModePanel(SETTINGS)
    rows = [
        {"corridor": "H", "number": "029", "height": ""},
        {"corridor": "H", "number": "030", "height": ""},
    ]

    results = panel.generate_from_rows(rows)

    assert [code for code, _ in results] == ["H029", "H030"]
    assert panel.result_label.text() == "2 labels generated"


def test_generate_from_rows_reports_skipped_rows():
    _app()
    panel = PositionsModePanel(SETTINGS)
    rows = [
        {"corridor": "H", "number": "029", "height": ""},
        {"corridor": "H", "number": "not-a-number", "height": ""},
        {"corridor": "H", "number": "030", "height": ""},
    ]

    results = panel.generate_from_rows(rows)

    assert [code for code, _ in results] == ["H029", "H030"]
    assert panel.result_label.text() == "2 labels generated (1 row skipped)"


def test_generate_from_rows_uses_position_code_field_directly():
    _app()
    panel = PositionsModePanel(SETTINGS)
    rows = [{"position_code": "H099Z"}]

    results = panel.generate_from_rows(rows)

    assert [code for code, _ in results] == ["H099Z"]


def test_generate_from_rows_raises_when_no_valid_codes():
    _app()
    panel = PositionsModePanel(SETTINGS)
    rows = [{"corridor": "H", "number": "not-a-number", "height": ""}]

    with pytest.raises(ValueError):
        panel.generate_from_rows(rows)


def test_import_csv_button_opens_dialog_and_generates_from_rows(monkeypatch):
    _app()
    panel = PositionsModePanel(SETTINGS)
    fake_rows = [{"corridor": "H", "number": "029", "height": ""}]

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return fake_rows

    monkeypatch.setattr("app.ui.mode_positions_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert panel.generated_codes == ["H029"]


def test_import_csv_button_does_nothing_when_dialog_cancelled(monkeypatch):
    _app()
    panel = PositionsModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return False

        def get_mapped_rows(self):
            raise AssertionError("should not be called when the dialog is cancelled")

    monkeypatch.setattr("app.ui.mode_positions_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert panel.generated_codes == []


def test_import_csv_button_shows_warning_when_no_valid_rows(monkeypatch):
    _app()
    panel = PositionsModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return [{"corridor": "H", "number": "not-a-number", "height": ""}]

    monkeypatch.setattr("app.ui.mode_positions_panel.CsvImportDialog", FakeDialog)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.import_csv_button.click()

    assert len(warnings) == 1


def test_refresh_from_settings_rebuilds_combos(tmp_path):
    _app()
    panel = PositionsModePanel(SETTINGS)
    _write_preset(tmp_path, "positions", "a", "80x80mm", 80, 80)

    panel.refresh_from_settings(
        {
            "warehouses": [{"name": "Second", "prefix": "C002"}],
            "shared_folder": str(tmp_path),
        }
    )

    warehouse_names = [
        panel.warehouse_combo.itemText(i) for i in range(panel.warehouse_combo.count())
    ]
    preset_names = [
        panel.preset_combo.itemText(i) for i in range(panel.preset_combo.count())
    ]
    assert warehouse_names == ["Second"]
    assert preset_names == ["80x80mm"]


def test_print_current_labels_writes_archive_pdf_to_shared_folder(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.generate()

    panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    archived = list((tmp_path / "printed_pdfs").glob("*.pdf"))
    assert len(archived) == 1
    assert archived[0].stat().st_size > 0
    assert "C001" in archived[0].name
    assert "H029..H030" in archived[0].name


def test_print_current_labels_raises_archive_error_after_successful_print(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.generate()
    (tmp_path / "printed_pdfs").write_text("occupied by a file, not a directory")

    with pytest.raises(ArchiveError):
        panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    assert (tmp_path / "out.pdf").exists()
    log_lines = (tmp_path / "audit_log.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 2  # header + one entry - logged despite the archive failure


def test_print_current_labels_skips_archive_when_send_to_printer_raises(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.generate()

    def _boom(*a, **k):
        raise OSError("printer offline")

    monkeypatch.setattr("app.ui.mode_positions_panel.send_to_printer", _boom)

    with pytest.raises(OSError):
        panel.print_current_labels()

    assert not (tmp_path / "printed_pdfs").exists()
```

Replace `tests/test_main_window.py` in full:

```python
import pytest
from PySide6.QtWidgets import QApplication

import app.ui.main_window as main_window_module
from app.core.config import save_settings
from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # MainWindow (and the panels it constructs) fall back to the real
    # default_settings_path() whenever shared_folder is unset; redirect all
    # three references into tmp_path so tests never touch (or seed template
    # presets into) the developer's actual ~/.barcode_tool directory.
    for module in (
        "app.ui.main_window",
        "app.ui.mode_positions_panel",
        "app.ui.mode_inventory_panel",
    ):
        monkeypatch.setattr(f"{module}.default_settings_path", lambda: tmp_path / "settings.json")


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"


def test_main_window_hosts_positions_and_inventory_tabs():
    _app()
    window = MainWindow()
    assert window.centralWidget() is window.tabs
    assert window.tabs.widget(0) is window.positions_panel
    assert window.tabs.widget(1) is window.inventory_panel
    assert window.tabs.tabText(0) == "Positions"
    assert window.tabs.tabText(1) == "Inventory"


def test_open_settings_refreshes_positions_panel_combos(monkeypatch, tmp_path):
    _app()
    window = MainWindow()
    window._settings_path = tmp_path / "settings.json"
    save_settings(
        window._settings_path,
        {"warehouses": [{"name": "New", "prefix": "C999"}]},
    )

    class FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window_module, "SettingsWindow", FakeSettingsDialog)

    window._open_settings()

    warehouse_names = [
        window.positions_panel.warehouse_combo.itemText(i)
        for i in range(window.positions_panel.warehouse_combo.count())
    ]
    assert warehouse_names == ["New"]


def test_open_settings_refreshes_inventory_panel_combos(monkeypatch, tmp_path):
    _app()
    window = MainWindow()
    window._settings_path = tmp_path / "settings.json"
    save_settings(
        window._settings_path,
        {"warehouses": [{"name": "New", "prefix": "C999"}]},
    )

    class FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window_module, "SettingsWindow", FakeSettingsDialog)

    window._open_settings()

    warehouse_names = [
        window.inventory_panel.warehouse_combo.itemText(i)
        for i in range(window.inventory_panel.warehouse_combo.count())
    ]
    assert warehouse_names == ["New"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_mode_positions_panel.py tests/test_main_window.py -v`
Expected: FAIL — `AttributeError`/`ImportError` referencing `preset_combo`,
`list_presets`, etc. (the panel hasn't been changed yet).

- [ ] **Step 3: Rewrite `app/ui/mode_positions_panel.py`**

Replace the file in full:

```python
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from barcode.errors import BarcodeError
from PIL import Image
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.audit_log import append_print_log
from app.core.config import default_settings_path
from app.core.position_generator import (
    NUMBER_MAX,
    codes_from_csv_rows,
    generate_position_codes,
)
from app.core.print_service import send_to_printer
from app.core.template_renderer import TemplatePreset, list_presets, render_records
from app.core.zpl_print_service import windows_print_errors
from app.ui.csv_import_dialog import CsvImportDialog

_LETTER_VALIDATOR = QRegularExpressionValidator(QRegularExpression("[A-Za-z]"))

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename_component(value: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", value)


class ArchiveError(OSError):
    pass


POSITION_CSV_FIELDS = [
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]


class PositionsModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.generated_codes: list[str] = []
        self.generated_labels: list[Image.Image] = []
        self._generated_label_size: dict | None = None

        self.warehouse_combo = QComboBox()
        self.corridor_edit = QLineEdit()
        self.corridor_edit.setValidator(_LETTER_VALIDATOR)
        self.corridor_edit.setMaxLength(1)
        self.number_from_edit = QLineEdit()
        self.number_from_edit.setValidator(QIntValidator(0, NUMBER_MAX, self))
        self.number_to_edit = QLineEdit()
        self.number_to_edit.setValidator(QIntValidator(0, NUMBER_MAX, self))
        self.number_to_edit.setPlaceholderText("same as from (optional)")

        self.height_enabled_check = QCheckBox("Use height")
        self.height_from_edit = QLineEdit()
        self.height_from_edit.setValidator(_LETTER_VALIDATOR)
        self.height_from_edit.setMaxLength(1)
        self.height_to_edit = QLineEdit()
        self.height_to_edit.setValidator(_LETTER_VALIDATOR)
        self.height_to_edit.setMaxLength(1)

        self.custom_text_edit = QLineEdit()

        self.preset_combo = QComboBox()
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 labels generated")
        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(self._on_generate_clicked)

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Corridor", self.corridor_edit)
        form.addRow("Number from", self.number_from_edit)
        form.addRow("Number to", self.number_to_edit)
        form.addRow(self.height_enabled_check)
        form.addRow("Height from", self.height_from_edit)
        form.addRow("Height to", self.height_to_edit)
        form.addRow("Custom text", self.custom_text_edit)
        form.addRow("Template", self.preset_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(generate_button)
        layout.addWidget(self.import_csv_button)
        layout.addWidget(self.result_label)
        layout.addWidget(self.print_button)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        shared_folder = settings.get("shared_folder") or default_settings_path().parent
        self.preset_combo.clear()
        for preset in list_presets(Path(shared_folder), "positions"):
            self.preset_combo.addItem(preset.name, preset)

    def _on_generate_clicked(self) -> None:
        try:
            self.generate()
        except (ValueError, BarcodeError) as error:
            QMessageBox.warning(self, "Invalid range", str(error))

    def _on_print_clicked(self) -> None:
        try:
            self.print_current_labels()
        except ArchiveError as error:
            QMessageBox.warning(
                self,
                "Archive failed",
                f"Labels printed, but the PDF archive failed: {error}\n"
                "Do not reprint this batch.",
            )
        except (ValueError, BarcodeError, OSError, *windows_print_errors()) as error:
            QMessageBox.warning(self, "Print failed", str(error))

    def generate(self) -> list[tuple[str, Image.Image]]:
        height_from = self.height_from_edit.text() or None
        height_to = self.height_to_edit.text() or None
        if not self.height_enabled_check.isChecked():
            height_from = height_to = None

        codes = generate_position_codes(
            self.corridor_edit.text(),
            self.number_from_edit.text(),
            self.number_to_edit.text() or None,
            height_from,
            height_to,
        )

        results = self._render_labels(codes)
        self.result_label.setText(f"{len(results)} labels generated")
        return results

    def generate_from_rows(self, rows: list[dict[str, str]]) -> list[tuple[str, Image.Image]]:
        codes, skipped_rows = codes_from_csv_rows(rows)
        if not codes:
            raise ValueError("No valid position codes found in the imported rows")

        results = self._render_labels(codes)

        if skipped_rows:
            unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f"{len(results)} labels generated ({len(skipped_rows)} {unit} skipped)"
            )
        else:
            self.result_label.setText(f"{len(results)} labels generated")
        return results

    def _render_labels(self, codes: list[str]) -> list[tuple[str, Image.Image]]:
        warehouse_prefix = self.warehouse_combo.currentData() or ""
        preset: TemplatePreset | None = self.preset_combo.currentData()
        if preset is None:
            raise ValueError(
                "No label template selected - check the shared folder's templates directory"
            )
        custom_text = self.custom_text_edit.text()

        records = [
            {
                "code": code,
                "barcode_data": f"{warehouse_prefix}{code}",
                "visible_text": f"{code} {custom_text}".strip(),
                "warehouse_prefix": warehouse_prefix,
                "custom_text": custom_text,
            }
            for code in codes
        ]
        images = render_records(preset, records)
        results = list(zip(codes, images))

        self.generated_codes = codes
        self.generated_labels = images
        self._generated_label_size = {"width_mm": preset.width_mm, "height_mm": preset.height_mm}
        return results

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(POSITION_CSV_FIELDS, parent=self)
        if not dialog.exec():
            return
        try:
            self.generate_from_rows(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def print_current_labels(self, output_pdf_path: Path | None = None) -> None:
        if not self.generated_labels:
            raise ValueError("Nothing to print - generate labels first")

        # Use the size the labels were actually rendered at, not whatever the
        # combo currently shows - the user may have changed it after Generate.
        label_size = self._generated_label_size

        send_to_printer(
            self.generated_labels,
            width_mm=label_size["width_mm"],
            height_mm=label_size["height_mm"],
            settings=self._settings,
            output_pdf_path=output_pdf_path,
        )

        warehouse_prefix = self.warehouse_combo.currentData() or ""
        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        if len(self.generated_codes) > 1:
            description = f"{self.generated_codes[0]}..{self.generated_codes[-1]}"
        else:
            description = self.generated_codes[0]

        log_path = Path(shared_folder) / "audit_log.csv"
        append_print_log(
            log_path,
            mode="positions",
            warehouse_prefix=warehouse_prefix,
            count=len(self.generated_codes),
            description=description,
        )

        try:
            archive_dir = Path(shared_folder) / "printed_pdfs"
            archive_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            archive_name = (
                f"{timestamp}_{_safe_filename_component(warehouse_prefix)}"
                f"_{_safe_filename_component(description)}.pdf"
            )
            send_to_printer(
                self.generated_labels,
                width_mm=label_size["width_mm"],
                height_mm=label_size["height_mm"],
                settings=self._settings,
                output_pdf_path=archive_dir / archive_name,
            )
        except OSError as error:
            raise ArchiveError(str(error)) from error
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_mode_positions_panel.py tests/test_main_window.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py tests/test_main_window.py
git commit -m "feat: wire PositionsModePanel to template presets, drop orientation combo"
```

---

### Task 5: Wire `InventoryModePanel` to template presets

**Files:**
- Modify: `app/ui/mode_inventory_panel.py`
- Modify: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: `TemplatePreset`, `list_presets`, `render_records` from
  `app.core.template_renderer` (Tasks 2-3).
- Produces: `InventoryModePanel.preset_combo`.

- [ ] **Step 1: Rewrite `tests/test_mode_inventory_panel.py` in full**

```python
import csv
import json
import re
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.mode_inventory_panel import (
    TABLE_COLUMNS,
    InventoryModePanel,
    _describe_skus,
)

SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
}


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # Prevents the shared_folder="" fallback path from touching the real
    # ~/.barcode_tool directory (and seeding example templates into it)
    # during tests.
    monkeypatch.setattr(
        "app.ui.mode_inventory_panel.default_settings_path",
        lambda: tmp_path / "settings.json",
    )


def _write_preset(
    shared_folder: Path, slug: str, name: str, width_mm: float, height_mm: float
) -> None:
    preset_dir = Path(shared_folder) / "templates" / "inventory" / slug
    preset_dir.mkdir(parents=True)
    (preset_dir / "meta.json").write_text(
        json.dumps({"name": name, "width_mm": width_mm, "height_mm": height_mm})
    )
    (preset_dir / "template.html").write_text(
        '<div><img src="{{ label_tools.qr_code(sku) }}"><div>{{ name }}</div></div>'
    )
    (preset_dir / "style.css").write_text(
        f"@page {{ size: {width_mm}mm {height_mm}mm; margin: 0; }}"
    )


def test_load_items_populates_table():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "name": "Widget", "position_code": "H011A"},
        {"sku": "SKU2", "name": "Gadget", "position_code": "H012A"},
    ]

    items = panel.load_items(rows)

    assert [item.sku for item in items] == ["SKU1", "SKU2"]
    assert panel.items_table.rowCount() == 2
    assert panel.items_table.item(0, 1).text() == "SKU1"
    assert panel.result_label.text() == "2 items imported"


def test_data_cells_are_not_editable():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    for column in range(1, len(TABLE_COLUMNS)):
        cell = panel.items_table.item(0, column)
        assert not (cell.flags() & Qt.ItemFlag.ItemIsEditable)


def test_load_items_reports_skipped_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "", "position_code": "H012A"},
    ]

    panel.load_items(rows)

    assert panel.result_label.text() == "1 item imported (1 row skipped)"


def test_load_items_raises_when_no_valid_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [{"sku": "", "position_code": "H011A"}]

    with pytest.raises(ValueError):
        panel.load_items(rows)


def test_rows_are_checked_by_default():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    assert panel.checked_items()[0].sku == "SKU1"


def test_select_none_then_select_all():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )

    panel.select_none_button.click()
    assert panel.checked_items() == []

    panel.select_all_button.click()
    assert [item.sku for item in panel.checked_items()] == ["SKU1", "SKU2"]


def test_unchecking_one_row_excludes_it_from_checked_items():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )

    panel.items_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)

    assert [item.sku for item in panel.checked_items()] == ["SKU2"]


def test_import_csv_button_opens_dialog_and_loads_items(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    fake_rows = [{"sku": "SKU1", "position_code": "H011A"}]

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return fake_rows

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert [item.sku for item in panel.items] == ["SKU1"]


def test_import_csv_button_does_nothing_when_dialog_cancelled(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return False

        def get_mapped_rows(self):
            raise AssertionError("should not be called when the dialog is cancelled")

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert panel.items == []


def test_import_csv_button_shows_warning_when_no_valid_rows(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return [{"sku": "", "position_code": "H011A"}]

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.import_csv_button.click()

    assert len(warnings) == 1


def test_refresh_from_settings_rebuilds_combos(tmp_path):
    _app()
    panel = InventoryModePanel(SETTINGS)
    _write_preset(tmp_path, "a", "80x80mm", 80, 80)

    panel.refresh_from_settings(
        {
            "warehouses": [{"name": "Second", "prefix": "C002"}],
            "shared_folder": str(tmp_path),
        }
    )

    warehouse_names = [panel.warehouse_combo.itemText(i) for i in range(panel.warehouse_combo.count())]
    preset_names = [panel.preset_combo.itemText(i) for i in range(panel.preset_combo.count())]
    assert warehouse_names == ["Second"]
    assert preset_names == ["80x80mm"]


def test_print_checked_items_writes_pdf_and_log(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {
                "sku": "SKU1",
                "name": "Widget",
                "batch": "4471",
                "expiry": "2027-03",
                "position_code": "H011A",
            },
            {"sku": "SKU2", "name": "Gadget", "position_code": "H012A"},
        ]
    )

    pdf_path = tmp_path / "out.pdf"
    panel.print_checked_items(output_pdf_path=pdf_path)

    assert pdf_path.exists()
    log_path = tmp_path / "audit_log.csv"
    rows = list(csv.reader(log_path.read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 2  # header + one entry
    assert rows[1][2:] == ["inventory", "C001", "2", "SKU1, SKU2"]


def test_print_checked_items_writes_a_timestamped_debug_pdf_next_to_the_audit_log(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items(output_pdf_path=tmp_path / "explicit.pdf")

    debug_pdfs = list(tmp_path.glob("inventory_label_preview_*.pdf"))
    assert len(debug_pdfs) == 1
    assert debug_pdfs[0].stat().st_size > 0


def test_print_checked_items_creates_a_not_yet_existing_shared_folder(tmp_path):
    _app()
    shared_folder = tmp_path / "not_yet_created" / "nested"
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(shared_folder)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items(output_pdf_path=tmp_path / "explicit.pdf")

    debug_pdfs = list(shared_folder.glob("inventory_label_preview_*.pdf"))
    assert len(debug_pdfs) == 1
    assert debug_pdfs[0].stat().st_size > 0
    assert (shared_folder / "audit_log.csv").exists()


def test_print_checked_items_still_writes_debug_pdf_without_an_explicit_output_path(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items()

    debug_pdfs = list(tmp_path.glob("inventory_label_preview_*.pdf"))
    assert len(debug_pdfs) == 1


def test_print_checked_items_skips_unchecked_rows(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )
    panel.items_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    log_path = tmp_path / "audit_log.csv"
    log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert log_lines[1].split(",")[2:] == ["inventory", "C001", "1", "SKU1"]


def test_print_checked_items_raises_when_nothing_checked(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])
    panel.select_none_button.click()

    with pytest.raises(ValueError):
        panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")


def test_print_checked_items_raises_without_warehouse():
    _app()
    settings = {"warehouses": []}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    with pytest.raises(ValueError):
        panel.print_checked_items()


def test_print_button_click_without_warehouse_shows_warning(monkeypatch):
    _app()
    settings = {"warehouses": []}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert len(warnings) == 1


def test_print_failure_reports_print_failed_and_skips_audit_log(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    def _boom(*a, **k):
        raise OSError("printer offline")

    monkeypatch.setattr("app.ui.mode_inventory_panel.send_to_printer", _boom)
    log_calls = []
    monkeypatch.setattr(
        "app.ui.mode_inventory_panel.append_print_log",
        lambda *a, **k: log_calls.append(True),
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert warnings[0][1] == "Print failed"
    assert log_calls == []


def test_audit_log_failure_reports_distinct_warning_after_successful_print(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    print_calls = []

    def _log_boom(*a, **k):
        raise OSError("share unavailable")

    monkeypatch.setattr(
        "app.ui.mode_inventory_panel.send_to_printer",
        lambda *a, **k: print_calls.append(True),
    )
    monkeypatch.setattr("app.ui.mode_inventory_panel.append_print_log", _log_boom)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert print_calls == [True, True]
    assert warnings[0][1] == "Audit log failed"


def test_describe_skus_dedupes_repeated_sku():
    assert _describe_skus(["SKU1", "SKU2", "SKU1"]) == "SKU1, SKU2"


def test_describe_skus_caps_long_lists():
    skus = [f"SKU{i}" for i in range(7)]
    assert _describe_skus(skus) == "SKU0, SKU1, SKU2, SKU3, SKU4 +2 more"


def test_print_button_click_invokes_print_checked_items(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    calls = []
    monkeypatch.setattr(panel, "print_checked_items", lambda: calls.append(True))

    panel.print_button.click()

    assert calls == [True]


def test_print_button_click_without_items_shows_warning(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert len(warnings) == 1


def test_client_column_populated_from_item():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A", "client": "Acme Corp"}])

    client_column = TABLE_COLUMNS.index("Client")
    assert panel.items_table.item(0, client_column).text() == "Acme Corp"


def test_print_checked_items_passes_generated_date_in_ddmmyyyy_format(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    render_calls = []

    def _fake_render(preset, records, **kwargs):
        render_calls.append(records)
        return [Image.new("RGB", (10, 10)) for _ in records]

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_records", _fake_render)
    monkeypatch.setattr("app.ui.mode_inventory_panel.send_to_printer", lambda *a, **k: None)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    generated_date = render_calls[0][0]["generated_date"]
    assert re.fullmatch(r"\d{8}", generated_date)


def test_print_checked_items_passes_structured_fields_to_renderer(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {
                "sku": "SKU1",
                "name": "Widget",
                "client": "Acme Corp",
                "batch": "4471",
                "expiry": "2027-03",
                "position_code": "H011A",
            }
        ]
    )

    render_calls = []

    def _fake_render(preset, records, **kwargs):
        render_calls.append(records)
        return [Image.new("RGB", (10, 10)) for _ in records]

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_records", _fake_render)
    monkeypatch.setattr("app.ui.mode_inventory_panel.send_to_printer", lambda *a, **k: None)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    record = render_calls[0][0]
    assert (
        record["sku"],
        record["name"],
        record["client"],
        record["batch"],
        record["expiry"],
        record["position_code"],
    ) == ("SKU1", "Widget", "Acme Corp", "4471", "2027-03", "H011A")
    assert record["position_data"] == "C001H011A"  # warehouse prefix + position_code
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: FAIL — `AttributeError`/`ImportError` referencing `preset_combo`,
`list_presets`, `render_records`.

- [ ] **Step 3: Rewrite `app/ui/mode_inventory_panel.py`**

Replace the file in full:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.audit_log import append_print_log
from app.core.config import default_settings_path
from app.core.inventory_import import (
    INVENTORY_CSV_FIELDS,
    InventoryItem,
    items_from_csv_rows,
)
from app.core.print_service import send_to_printer
from app.core.template_renderer import TemplatePreset, list_presets, render_records
from app.core.zpl_print_service import windows_print_errors
from app.ui.csv_import_dialog import CsvImportDialog

TABLE_COLUMNS = ["", "SKU", "Name", "Client", "Position", "Batch", "Expiry"]

_DESCRIPTION_SKU_LIMIT = 5


class AuditLogError(OSError):
    """Raised when labels printed successfully but the audit log entry could not be written."""


def _describe_skus(skus: list[str], limit: int = _DESCRIPTION_SKU_LIMIT) -> str:
    unique_skus = list(dict.fromkeys(skus))
    description = ", ".join(unique_skus[:limit])
    remaining = len(unique_skus) - limit
    if remaining > 0:
        description += f" +{remaining} more"
    return description


class InventoryModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.items: list[InventoryItem] = []

        self.warehouse_combo = QComboBox()
        self.preset_combo = QComboBox()
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 items imported")

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))

        self.items_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(TABLE_COLUMNS)

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Template", self.preset_combo)

        select_buttons = QHBoxLayout()
        select_buttons.addWidget(self.select_all_button)
        select_buttons.addWidget(self.select_none_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.import_csv_button)
        layout.addWidget(self.result_label)
        layout.addLayout(select_buttons)
        layout.addWidget(self.items_table)
        layout.addWidget(self.print_button)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        shared_folder = settings.get("shared_folder") or default_settings_path().parent
        self.preset_combo.clear()
        for preset in list_presets(Path(shared_folder), "inventory"):
            self.preset_combo.addItem(preset.name, preset)

    def load_items(self, rows: list[dict[str, str]]) -> list[InventoryItem]:
        items, skipped_rows = items_from_csv_rows(rows)
        if not items:
            raise ValueError("No valid inventory rows found in the imported file")

        self.items = items
        self._populate_table(items)

        item_unit = "item" if len(items) == 1 else "items"
        if skipped_rows:
            row_unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f"{len(items)} {item_unit} imported ({len(skipped_rows)} {row_unit} skipped)"
            )
        else:
            self.result_label.setText(f"{len(items)} {item_unit} imported")
        return items

    def _populate_table(self, items: list[InventoryItem]) -> None:
        self.items_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.items_table.setItem(row_index, 0, check_item)

            values = [item.sku, item.name, item.client, item.position_code, item.batch, item.expiry]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row_index, column, cell)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None:
                check_item.setCheckState(state)

    def checked_items(self) -> list[InventoryItem]:
        checked = []
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None and check_item.checkState() == Qt.CheckState.Checked:
                checked.append(self.items[row])
        return checked

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(INVENTORY_CSV_FIELDS, parent=self)
        if not dialog.exec():
            return
        try:
            self.load_items(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def _on_print_clicked(self) -> None:
        try:
            self.print_checked_items()
        except AuditLogError as error:
            QMessageBox.warning(
                self,
                "Audit log failed",
                f"Labels printed, but the audit log entry failed: {error}\n"
                "Do not reprint this batch.",
            )
        except (ValueError, OSError, *windows_print_errors()) as error:
            QMessageBox.warning(self, "Print failed", str(error))

    def print_checked_items(self, output_pdf_path: Path | None = None) -> None:
        checked = self.checked_items()
        if not checked:
            raise ValueError("Nothing to print - import a CSV and check at least one row")

        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            raise ValueError("No warehouse selected - add one in Settings first")

        preset: TemplatePreset | None = self.preset_combo.currentData()
        if preset is None:
            raise ValueError(
                "No label template selected - check the shared folder's templates directory"
            )

        generated_date = datetime.now(timezone.utc).astimezone().strftime("%d%m%Y")

        records = [
            {
                "sku": item.sku,
                "name": item.name,
                "client": item.client,
                "batch": item.batch,
                "expiry": item.expiry,
                "position_code": item.position_code,
                "position_data": f"{warehouse_prefix}{item.position_code}",
                "generated_date": generated_date,
            }
            for item in checked
        ]
        images = render_records(preset, records)

        send_to_printer(
            images,
            width_mm=preset.width_mm,
            height_mm=preset.height_mm,
            settings=self._settings,
            output_pdf_path=output_pdf_path,
        )

        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        Path(shared_folder).mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).astimezone()
        debug_pdf_path = Path(shared_folder) / f"inventory_label_preview_{now:%Y%m%d_%H%M%S}.pdf"
        send_to_printer(
            images,
            width_mm=preset.width_mm,
            height_mm=preset.height_mm,
            settings=self._settings,
            output_pdf_path=debug_pdf_path,
        )

        log_path = Path(shared_folder) / "audit_log.csv"
        description = _describe_skus([item.sku for item in checked])
        try:
            append_print_log(
                log_path,
                mode="inventory",
                warehouse_prefix=warehouse_prefix,
                count=len(checked),
                description=description,
            )
        except OSError as error:
            raise AuditLogError(str(error)) from error
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_mode_inventory_panel.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "feat: wire InventoryModePanel to template presets"
```

---

### Task 6: Delete the old renderer and dead settings

**Files:**
- Delete: `app/core/label_renderer.py`
- Delete: `app/core/barcode_engine.py`
- Delete: `tests/test_label_renderer.py`
- Delete: `tests/test_barcode_engine.py`
- Modify: `app/core/config.py`

**Interfaces:**
- Consumes: nothing new — this only removes code no longer referenced by
  any of Tasks 1-5.

- [ ] **Step 1: Confirm nothing still references the modules being deleted**

Run: `grep -rn "label_renderer\|barcode_engine\|label_sizes" --include=*.py app tests`
Expected: only hits inside `app/core/label_renderer.py`,
`app/core/barcode_engine.py`, `tests/test_label_renderer.py`,
`tests/test_barcode_engine.py`, and the `label_sizes` key definition in
`app/core/config.py` itself. If anything else shows up, stop and find out
why before deleting (Tasks 1-5 should have already removed every other
reference).

- [ ] **Step 2: Delete the dead files**

```bash
git rm app/core/label_renderer.py app/core/barcode_engine.py \
  tests/test_label_renderer.py tests/test_barcode_engine.py
```

- [ ] **Step 3: Remove `label_sizes` from `DEFAULT_SETTINGS`**

Edit `app/core/config.py` — remove the `"label_sizes": [...]` entry:

```python
DEFAULT_SETTINGS = {
    "shared_folder": "",
    "default_printer": "",
    "print_mode": "driver",
    "raw_zpl_target": "",
    "warehouses": [],
}
```

- [ ] **Step 4: Run the full test suite and linter**

Run: `pytest -v`
Expected: PASS, no failures, no collection errors from the deleted modules.

Run: `ruff check .`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py
git commit -m "chore: remove the old PIL label renderer and dead label_sizes setting"
```

---

## Self-Review Notes

- **Spec coverage:** Architecture/pipeline (Task 1-3), preset structure +
  data contract (Task 2), UI changes + orientation removal (Task 4-5),
  settings cleanup + migration (Task 6) — every section of the design doc
  maps to a task.
- **Windows CI risk:** Task 1's Pango install step is the one piece of this
  plan that can't be verified locally in this Linux dev environment — it's
  called out explicitly as needing a real CI run to confirm, rather than
  asserted as certain.
- **Hidden regression caught during planning:** `MainWindow()` (exercised by
  `test_main_window.py`) constructs both panels using settings loaded from
  the *real* `default_settings_path()` unless patched. Once
  `refresh_from_settings` starts calling `list_presets` (which can write
  seeded example templates to disk), unpatched tests would pollute the
  developer's actual `~/.barcode_tool` directory. Fixed by isolating
  `default_settings_path` in `test_main_window.py` as part of Task 4.
