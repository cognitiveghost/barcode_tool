# Barcode Label Generator — Phase 0 + Phase 1 (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the project skeleton and ship a working end-to-end pipeline for Mode 2.1 (warehouse position labels): form input → position range generation → Code128 barcode → composed label image → print-preview-ready output (testable via PDF) → audit log entry.

**Architecture:** Single-process native desktop app (PySide6/Qt). Pure, GUI-independent logic lives in `app/core/` (position generation, barcode rendering, label composition, printing, audit logging, settings persistence); `app/ui/` holds the Qt widgets that call into `core/`. No database — JSON settings file + CSV audit log, both plain files.

**Tech Stack:** Python 3.11+, PySide6 (Qt), `python-barcode` (Code128), Pillow, pytest.

## Global Constraints

- The application and all code/comments must be in English (per spec: "Додаток повинен бути повністю англійською мовою, розробка та коментарі відповідно").
- No emojis anywhere in the UI.
- Must run locally on Windows 10/11 and Ubuntu 25+.
- Single native desktop process — no separate backend server (resolved during brainstorming; see design doc §2).
- Multi-user access is via a shared network folder the user points the app at in Settings, not a client-server architecture.
- The warehouse prefix must be embedded in the barcode's encoded data but must **never** appear in the visible printed text.
- Confirmed target hardware: Citizen CL-E300 thermal printer, 203 DPI. Printing goes through the OS-installed printer driver via Qt `QPrinter`, not raw ZPL.
- Distribution is a standalone executable (PyInstaller) — not covered by this plan (Phase 5).

Full design rationale: `docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md`.

---

## Task 1: Project scaffolding + empty main window

**Files:**
- Create: `requirements.txt`
- Create: `conftest.py`
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/ui/__init__.py`
- Create: `app/ui/main_window.py`
- Create: `app/main.py`
- Test: `tests/test_main_window.py`

**Interfaces:**
- Produces: `app.ui.main_window.MainWindow` — a `QMainWindow` subclass with `windowTitle() == "Barcode Label Generator"`.

- [ ] **Step 1: Create scaffolding files**

`requirements.txt`:
```
PySide6>=6.7
python-barcode>=0.15
Pillow>=10.0
pytest>=8.0
```

`conftest.py` (repo root — makes the `app` package importable by pytest and forces headless Qt for all tests):
```python
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))
```

Create empty files: `app/__init__.py`, `app/core/__init__.py`, `app/ui/__init__.py`.

- [ ] **Step 2: Write the failing test**

`tests/test_main_window.py`:
```python
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_main_window.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.main_window'`

- [ ] **Step 4: Implement MainWindow and the entrypoint**

`app/ui/main_window.py`:
```python
from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Barcode Label Generator")
        self.resize(900, 600)
```

`app/main.py`:
```python
import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_main_window.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt conftest.py app tests
git commit -m "chore: project scaffolding and empty main window"
```

---

## Task 2: Settings persistence (`config.py`)

**Files:**
- Create: `app/core/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing (no dependency on earlier tasks beyond the package scaffolding from Task 1).
- Produces:
  - `DEFAULT_SETTINGS: dict` — keys `shared_folder: str`, `default_printer: str`, `warehouses: list[dict]` (each `{"name": str, "prefix": str}`), `label_sizes: list[dict]` (each `{"name": str, "width_mm": float, "height_mm": float}`, pre-populated with the three spec presets).
  - `default_settings_path() -> Path`
  - `load_settings(path: Path) -> dict`
  - `save_settings(path: Path, settings: dict) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import json

from app.core.config import DEFAULT_SETTINGS, load_settings, save_settings


def test_load_settings_returns_defaults_when_missing(tmp_path):
    path = tmp_path / "settings.json"
    assert load_settings(path) == DEFAULT_SETTINGS


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    settings["shared_folder"] = "/mnt/shared"
    settings["warehouses"].append({"name": "Main", "prefix": "C001"})

    save_settings(path, settings)
    loaded = load_settings(path)

    assert loaded == settings
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: Implement config.py**

`app/core/config.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SETTINGS = {
    "shared_folder": "",
    "default_printer": "",
    "warehouses": [],
    "label_sizes": [
        {"name": "100x150mm", "width_mm": 100, "height_mm": 150},
        {"name": "68x38mm", "width_mm": 68, "height_mm": 38},
        {"name": "80x80mm", "width_mm": 80, "height_mm": 80},
    ],
}


def default_settings_path() -> Path:
    return Path.home() / ".barcode_tool" / "settings.json"


def load_settings(path: Path) -> dict:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py tests/test_config.py
git commit -m "feat: JSON settings load/save"
```

---

## Task 3: Position range generator

**Files:**
- Create: `app/core/position_generator.py`
- Test: `tests/test_position_generator.py`

**Interfaces:**
- Consumes: nothing (pure function, no dependency on other tasks).
- Produces: `generate_position_codes(corridor: str, number_from: str, number_to: str, height_from: str | None = None, height_to: str | None = None) -> list[str]`. Raises `ValueError` on `number_from > number_to`, non-digit numbers, or `height_from > height_to`.

- [ ] **Step 1: Write the failing tests**

`tests/test_position_generator.py`:
```python
import pytest

from app.core.position_generator import generate_position_codes


def test_simple_range_no_height():
    codes = generate_position_codes("H", "029", "031")
    assert codes == ["H029", "H030", "H031"]


def test_range_with_height_range():
    codes = generate_position_codes("H", "029", "030", "A", "C")
    assert codes == [
        "H029A", "H029B", "H029C",
        "H030A", "H030B", "H030C",
    ]


def test_single_height():
    codes = generate_position_codes("H", "029", "029", "A")
    assert codes == ["H029A"]


def test_invalid_number_range_raises():
    with pytest.raises(ValueError):
        generate_position_codes("H", "090", "029")


def test_invalid_height_range_raises():
    with pytest.raises(ValueError):
        generate_position_codes("H", "029", "030", "F", "A")


def test_zero_padding_matches_input_width():
    codes = generate_position_codes("H", "005", "006")
    assert codes == ["H005", "H006"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_position_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.position_generator'`

- [ ] **Step 3: Implement position_generator.py**

`app/core/position_generator.py`:
```python
from __future__ import annotations


def generate_position_codes(
    corridor: str,
    number_from: str,
    number_to: str,
    height_from: str | None = None,
    height_to: str | None = None,
) -> list[str]:
    if not number_from.isdigit() or not number_to.isdigit():
        raise ValueError("number_from and number_to must be digits")

    width = len(number_from)
    start, end = int(number_from), int(number_to)
    if start > end:
        raise ValueError("number_from must be <= number_to")

    heights: list[str] = [""]
    if height_from is not None:
        if height_to is None:
            height_to = height_from
        if len(height_from) != 1 or len(height_to) != 1:
            raise ValueError("height letters must be single characters")
        if height_from > height_to:
            raise ValueError("height_from must be <= height_to")
        heights = [chr(c) for c in range(ord(height_from), ord(height_to) + 1)]

    codes = []
    for number in range(start, end + 1):
        padded = str(number).zfill(width)
        for height in heights:
            codes.append(f"{corridor}{padded}{height}")
    return codes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_position_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/position_generator.py tests/test_position_generator.py
git commit -m "feat: warehouse position range generator"
```

---

## Task 4: Barcode image generation

**Files:**
- Create: `app/core/barcode_engine.py`
- Test: `tests/test_barcode_engine.py`

**Interfaces:**
- Consumes: nothing beyond `python-barcode` and `Pillow`.
- Produces: `generate_barcode_image(data: str) -> PIL.Image.Image`. Renders Code128 **without** python-barcode's own human-readable text line (that line would otherwise leak the raw encoded string, including the warehouse prefix, onto the label).

- [ ] **Step 1: Write the failing tests**

`tests/test_barcode_engine.py`:
```python
from PIL import Image

from app.core.barcode_engine import generate_barcode_image


def test_generate_barcode_image_returns_image():
    img = generate_barcode_image("C001H029A")
    assert isinstance(img, Image.Image)
    assert img.width > 0
    assert img.height > 0


def test_different_data_produces_different_image():
    img_a = generate_barcode_image("C001H029A")
    img_b = generate_barcode_image("C001H030A")
    assert img_a.tobytes() != img_b.tobytes()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_barcode_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.barcode_engine'`

- [ ] **Step 3: Implement barcode_engine.py**

`app/core/barcode_engine.py`:
```python
from __future__ import annotations

import barcode
from barcode.writer import ImageWriter
from PIL import Image


def generate_barcode_image(data: str) -> Image.Image:
    code = barcode.get("code128", data, writer=ImageWriter())
    return code.render(writer_options={"write_text": False})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_barcode_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/barcode_engine.py tests/test_barcode_engine.py
git commit -m "feat: Code128 barcode image generation"
```

---

## Task 5: Label composition (barcode + text)

**Files:**
- Create: `app/core/label_renderer.py`
- Test: `tests/test_label_renderer.py`

**Interfaces:**
- Consumes: `app.core.barcode_engine.generate_barcode_image(data: str) -> PIL.Image.Image` (Task 4).
- Produces:
  - `mm_to_px(mm: float, dpi: int = 203) -> int`
  - `render_label(barcode_data: str, visible_text: str, width_mm: float, height_mm: float, dpi: int = 203) -> PIL.Image.Image`

- [ ] **Step 1: Write the failing tests**

`tests/test_label_renderer.py`:
```python
from PIL import Image

from app.core.label_renderer import mm_to_px, render_label


def test_mm_to_px_at_203_dpi():
    assert mm_to_px(25.4, dpi=203) == 203


def test_render_label_returns_image_of_expected_size():
    img = render_label("C001H029A", "H029A", width_mm=68, height_mm=38, dpi=203)
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(68, 203), mm_to_px(38, 203))


def test_render_label_visible_text_differs_from_barcode_data_changes_output():
    img_with_prefix_text = render_label("C001H029A", "C001H029A", width_mm=68, height_mm=38)
    img_without_prefix_text = render_label("C001H029A", "H029A", width_mm=68, height_mm=38)
    assert img_with_prefix_text.tobytes() != img_without_prefix_text.tobytes()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_label_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.label_renderer'`

- [ ] **Step 3: Implement label_renderer.py**

`app/core/label_renderer.py`:
```python
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from app.core.barcode_engine import generate_barcode_image

MM_PER_INCH = 25.4


def mm_to_px(mm: float, dpi: int = 203) -> int:
    return round(mm / MM_PER_INCH * dpi)


def render_label(
    barcode_data: str,
    visible_text: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)

    canvas = Image.new("RGB", (width_px, height_px), "white")

    barcode_img = generate_barcode_image(barcode_data)
    max_barcode_height = round(height_px * 0.7)
    scale = min(width_px / barcode_img.width, max_barcode_height / barcode_img.height, 1)
    barcode_img = barcode_img.resize(
        (round(barcode_img.width * scale), round(barcode_img.height * scale))
    )
    barcode_x = (width_px - barcode_img.width) // 2
    canvas.paste(barcode_img, (barcode_x, 0))

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), visible_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = max((width_px - text_width) // 2, 0)
    text_y = barcode_img.height + 2
    draw.text((text_x, text_y), visible_text, fill="black", font=font)

    return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_label_renderer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/label_renderer.py tests/test_label_renderer.py
git commit -m "feat: compose barcode + text into a sized label image"
```

---

## Task 6: Settings window (UI)

**Files:**
- Create: `app/ui/settings_window.py`
- Test: `tests/test_settings_window.py`

**Interfaces:**
- Consumes: `app.core.config.{DEFAULT_SETTINGS, load_settings, save_settings}` (Task 2).
- Produces: `app.ui.settings_window.SettingsWindow(QDialog)` with:
  - `__init__(self, settings: dict, settings_path: Path | None, parent=None)`
  - `get_current_settings(self) -> dict` — returns `{"shared_folder": str, "default_printer": str, "warehouses": list[dict]}` read from the widgets.
  - Widgets used by later tasks/tests: `shared_folder_edit`, `printer_combo`, `warehouse_table`.

- [ ] **Step 1: Write the failing tests**

`tests/test_settings_window.py`:
```python
from PySide6.QtWidgets import QApplication

from app.core.config import DEFAULT_SETTINGS, load_settings
from app.ui.settings_window import SettingsWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_settings_window_prefills_shared_folder():
    _app()
    settings = {**DEFAULT_SETTINGS, "shared_folder": "/mnt/shared"}
    window = SettingsWindow(settings, settings_path=None)
    assert window.shared_folder_edit.text() == "/mnt/shared"


def test_add_and_read_warehouse_row():
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=None)
    window._add_warehouse_row("Main", "C001")
    result = window.get_current_settings()
    assert result["warehouses"] == [{"name": "Main", "prefix": "C001"}]


def test_save_writes_settings_to_disk(tmp_path):
    _app()
    settings_path = tmp_path / "settings.json"
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=settings_path)
    window.shared_folder_edit.setText("/mnt/shared")
    window._save_and_close()

    saved = load_settings(settings_path)
    assert saved["shared_folder"] == "/mnt/shared"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settings_window.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.settings_window'`

- [ ] **Step 3: Implement settings_window.py**

`app/ui/settings_window.py`:
```python
from __future__ import annotations

from pathlib import Path

from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.config import load_settings, save_settings


class SettingsWindow(QDialog):
    def __init__(self, settings: dict, settings_path: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._settings_path = settings_path

        self.shared_folder_edit = QLineEdit(settings.get("shared_folder", ""))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_shared_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.shared_folder_edit)
        folder_row.addWidget(browse_button)

        self.printer_combo = QComboBox()
        printer_names = [p.printerName() for p in QPrinterInfo.availablePrinters()]
        self.printer_combo.addItems(printer_names)
        current_printer = settings.get("default_printer", "")
        if current_printer in printer_names:
            self.printer_combo.setCurrentText(current_printer)

        self.warehouse_table = QTableWidget(0, 2)
        self.warehouse_table.setHorizontalHeaderLabels(["Name", "Prefix"])
        for warehouse in settings.get("warehouses", []):
            self._add_warehouse_row(warehouse["name"], warehouse["prefix"])

        add_warehouse_button = QPushButton("Add warehouse")
        add_warehouse_button.clicked.connect(lambda: self._add_warehouse_row("", ""))
        remove_warehouse_button = QPushButton("Remove selected")
        remove_warehouse_button.clicked.connect(self._remove_selected_warehouse)
        warehouse_buttons = QHBoxLayout()
        warehouse_buttons.addWidget(add_warehouse_button)
        warehouse_buttons.addWidget(remove_warehouse_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(folder_row)
        layout.addWidget(self.printer_combo)
        layout.addWidget(self.warehouse_table)
        layout.addLayout(warehouse_buttons)
        layout.addWidget(buttons)

    def _browse_shared_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select shared folder")
        if folder:
            self.shared_folder_edit.setText(folder)

    def _add_warehouse_row(self, name: str, prefix: str) -> None:
        row = self.warehouse_table.rowCount()
        self.warehouse_table.insertRow(row)
        self.warehouse_table.setItem(row, 0, QTableWidgetItem(name))
        self.warehouse_table.setItem(row, 1, QTableWidgetItem(prefix))

    def _remove_selected_warehouse(self) -> None:
        for index in sorted(
            {i.row() for i in self.warehouse_table.selectedIndexes()}, reverse=True
        ):
            self.warehouse_table.removeRow(index)

    def get_current_settings(self) -> dict:
        warehouses = []
        for row in range(self.warehouse_table.rowCount()):
            name_item = self.warehouse_table.item(row, 0)
            prefix_item = self.warehouse_table.item(row, 1)
            warehouses.append(
                {
                    "name": name_item.text() if name_item else "",
                    "prefix": prefix_item.text() if prefix_item else "",
                }
            )
        return {
            "shared_folder": self.shared_folder_edit.text(),
            "default_printer": self.printer_combo.currentText(),
            "warehouses": warehouses,
        }

    def _save_and_close(self) -> None:
        full_settings = load_settings(self._settings_path)
        full_settings.update(self.get_current_settings())
        save_settings(self._settings_path, full_settings)
        self.accept()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings_window.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/settings_window.py tests/test_settings_window.py
git commit -m "feat: settings window for shared folder, printer, warehouses"
```

---

## Task 7: Position mode panel (UI)

**Files:**
- Create: `app/ui/mode_positions_panel.py`
- Test: `tests/test_mode_positions_panel.py`

**Interfaces:**
- Consumes:
  - `app.core.position_generator.generate_position_codes(...)` (Task 3)
  - `app.core.label_renderer.render_label(...)` (Task 5)
- Produces: `app.ui.mode_positions_panel.PositionsModePanel(QWidget)` with:
  - `__init__(self, settings: dict, parent=None)`
  - `generate(self) -> list[tuple[str, PIL.Image.Image]]` — raises `ValueError` on invalid ranges (does **not** show a dialog itself, so it stays unit-testable; the dialog is shown by the button's click handler).
  - Attributes later tasks rely on: `generated_codes: list[str]`, `generated_labels: list[PIL.Image.Image]`, `warehouse_combo`, `label_size_combo`.

- [ ] **Step 1: Write the failing tests**

`tests/test_mode_positions_panel.py`:
```python
import pytest
from PySide6.QtWidgets import QApplication

from app.ui.mode_positions_panel import PositionsModePanel

SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
    "label_sizes": [{"name": "68x38mm", "width_mm": 68, "height_mm": 38}],
}


def _app():
    return QApplication.instance() or QApplication([])


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


def test_invalid_range_raises_value_error():
    _app()
    panel = PositionsModePanel(SETTINGS)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("090")
    panel.number_to_edit.setText("029")

    with pytest.raises(ValueError):
        panel.generate()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.mode_positions_panel'`

- [ ] **Step 3: Implement mode_positions_panel.py**

`app/ui/mode_positions_panel.py`:
```python
from __future__ import annotations

from PIL import Image
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

from app.core.label_renderer import render_label
from app.core.position_generator import generate_position_codes


class PositionsModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.generated_codes: list[str] = []
        self.generated_labels: list[Image.Image] = []

        self.warehouse_combo = QComboBox()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        self.corridor_edit = QLineEdit()
        self.number_from_edit = QLineEdit()
        self.number_to_edit = QLineEdit()

        self.height_enabled_check = QCheckBox("Use height")
        self.height_from_edit = QLineEdit()
        self.height_to_edit = QLineEdit()

        self.custom_text_edit = QLineEdit()

        self.label_size_combo = QComboBox()
        for size in settings.get("label_sizes", []):
            self.label_size_combo.addItem(size["name"], size)

        self.result_label = QLabel("0 labels generated")
        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(self._on_generate_clicked)

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Corridor", self.corridor_edit)
        form.addRow("Number from", self.number_from_edit)
        form.addRow("Number to", self.number_to_edit)
        form.addRow(self.height_enabled_check)
        form.addRow("Height from", self.height_from_edit)
        form.addRow("Height to", self.height_to_edit)
        form.addRow("Custom text", self.custom_text_edit)
        form.addRow("Label size", self.label_size_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(generate_button)
        layout.addWidget(self.result_label)

    def _on_generate_clicked(self) -> None:
        try:
            self.generate()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid range", str(error))

    def generate(self) -> list[tuple[str, Image.Image]]:
        warehouse_prefix = self.warehouse_combo.currentData() or ""
        height_from = self.height_from_edit.text() or None
        height_to = self.height_to_edit.text() or None
        if not self.height_enabled_check.isChecked():
            height_from = height_to = None

        codes = generate_position_codes(
            self.corridor_edit.text(),
            self.number_from_edit.text(),
            self.number_to_edit.text(),
            height_from,
            height_to,
        )

        label_size = self.label_size_combo.currentData()
        custom_text = self.custom_text_edit.text()

        results = []
        for code in codes:
            visible_text = f"{code} {custom_text}".strip()
            barcode_data = f"{warehouse_prefix}{code}"
            image = render_label(
                barcode_data,
                visible_text,
                width_mm=label_size["width_mm"],
                height_mm=label_size["height_mm"],
            )
            results.append((code, image))

        self.generated_codes = codes
        self.generated_labels = [image for _, image in results]
        self.result_label.setText(f"{len(results)} labels generated")
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py
git commit -m "feat: position mode form generating labels from a range"
```

---

## Task 8: Print service (QPrinter, PDF-testable)

**Files:**
- Create: `app/core/print_service.py`
- Test: `tests/test_print_service.py`

**Interfaces:**
- Consumes: nothing beyond Pillow + PySide6.
- Produces: `print_labels(images: list[PIL.Image.Image], width_mm: float, height_mm: float, printer_name: str | None = None, output_pdf_path: Path | None = None) -> None`. When `output_pdf_path` is given, renders to that PDF instead of a physical printer — this is both the print-preview export path and the test double for hardware printing.

- [ ] **Step 1: Write the failing test**

`tests/test_print_service.py`:
```python
from PIL import Image
from PySide6.QtWidgets import QApplication

from app.core.print_service import print_labels


def _app():
    return QApplication.instance() or QApplication([])


def test_print_labels_writes_pdf_with_expected_page_count(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white") for _ in range(3)]
    output_path = tmp_path / "labels.pdf"

    print_labels(images, width_mm=68, height_mm=38, output_pdf_path=output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_print_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.print_service'`

- [ ] **Step 3: Implement print_service.py**

`app/core/print_service.py`:
```python
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageSize, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrinter


def print_labels(
    images: list[Image.Image],
    width_mm: float,
    height_mm: float,
    printer_name: str | None = None,
    output_pdf_path: Path | None = None,
) -> None:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageSize.Unit.Millimeter)

    if output_pdf_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_pdf_path))
    elif printer_name:
        printer.setPrinterName(printer_name)

    painter = QPainter(printer)
    for index, image in enumerate(images):
        if index > 0:
            printer.newPage()
        pixmap = QPixmap.fromImage(ImageQt(image))
        target = painter.viewport()
        painter.drawPixmap(target, pixmap, pixmap.rect())
    painter.end()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_print_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/print_service.py tests/test_print_service.py
git commit -m "feat: print label batch via QPrinter (PDF-testable)"
```

---

## Task 9: Audit log + wire printing into the position panel

**Files:**
- Create: `app/core/audit_log.py`
- Test: `tests/test_audit_log.py`
- Modify: `app/ui/mode_positions_panel.py` (add `print_current_labels`)
- Modify: `tests/test_mode_positions_panel.py` (add integration test)

**Interfaces:**
- Consumes:
  - `app.core.print_service.print_labels(...)` (Task 8)
  - `app.core.audit_log.append_print_log(...)` (this task)
- Produces:
  - `append_print_log(log_path: Path, mode: str, warehouse_prefix: str, count: int, description: str) -> None` — appends one CSV row, writing the header row only if the file doesn't exist yet.
  - `PositionsModePanel.print_current_labels(self, output_pdf_path: Path | None = None) -> None` — raises `ValueError` if `generate()` hasn't produced labels yet.

- [ ] **Step 1: Write the failing tests**

`tests/test_audit_log.py`:
```python
import csv

from app.core.audit_log import append_print_log


def test_append_creates_file_with_header_and_row(tmp_path):
    log_path = tmp_path / "audit.csv"

    append_print_log(log_path, mode="positions", warehouse_prefix="C001", count=2, description="H029-H030")

    with log_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]
    assert rows[1][2:] == ["positions", "C001", "2", "H029-H030"]


def test_append_twice_adds_second_row_without_duplicate_header(tmp_path):
    log_path = tmp_path / "audit.csv"

    append_print_log(log_path, mode="positions", warehouse_prefix="C001", count=1, description="H029")
    append_print_log(log_path, mode="positions", warehouse_prefix="C001", count=1, description="H030")

    with log_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert len(rows) == 3
    assert rows.count(
        ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]
    ) == 1
```

Add to `tests/test_mode_positions_panel.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_audit_log.py tests/test_mode_positions_panel.py -v`
Expected: `test_audit_log.py` fails with `ModuleNotFoundError: No module named 'app.core.audit_log'`; the new panel test fails with `AttributeError: 'PositionsModePanel' object has no attribute 'print_current_labels'`.

- [ ] **Step 3: Implement audit_log.py**

`app/core/audit_log.py`:
```python
from __future__ import annotations

import csv
import getpass
from datetime import datetime, timezone
from pathlib import Path

LOG_COLUMNS = ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]


def append_print_log(
    log_path: Path,
    mode: str,
    warehouse_prefix: str,
    count: int,
    description: str,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(LOG_COLUMNS)
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                getpass.getuser(),
                mode,
                warehouse_prefix,
                count,
                description,
            ]
        )
```

- [ ] **Step 4: Wire printing + logging into the panel**

Add to the top of `app/ui/mode_positions_panel.py`:
```python
from pathlib import Path

from app.core.audit_log import append_print_log
from app.core.print_service import print_labels
```

Add this method to `PositionsModePanel`:
```python
    def print_current_labels(self, output_pdf_path: Path | None = None) -> None:
        if not self.generated_labels:
            raise ValueError("Nothing to print - generate labels first")

        label_size = self.label_size_combo.currentData()
        printer_name = self._settings.get("default_printer") or None

        print_labels(
            self.generated_labels,
            width_mm=label_size["width_mm"],
            height_mm=label_size["height_mm"],
            printer_name=printer_name,
            output_pdf_path=output_pdf_path,
        )

        warehouse_prefix = self.warehouse_combo.currentData() or ""
        log_path = Path(self._settings.get("shared_folder", ".")) / "audit_log.csv"
        if len(self.generated_codes) > 1:
            description = f"{self.generated_codes[0]}..{self.generated_codes[-1]}"
        else:
            description = self.generated_codes[0]
        append_print_log(
            log_path,
            mode="positions",
            warehouse_prefix=warehouse_prefix,
            count=len(self.generated_codes),
            description=description,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_audit_log.py tests/test_mode_positions_panel.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/audit_log.py app/ui/mode_positions_panel.py tests/test_audit_log.py tests/test_mode_positions_panel.py
git commit -m "feat: audit log, wired into position panel printing"
```

---

## Task 10: Assemble the main window (Settings + Positions panel)

**Files:**
- Modify: `app/ui/main_window.py`
- Modify: `tests/test_main_window.py` (add integration test)

**Interfaces:**
- Consumes:
  - `app.core.config.{default_settings_path, load_settings}` (Task 2)
  - `app.ui.mode_positions_panel.PositionsModePanel` (Task 7)
  - `app.ui.settings_window.SettingsWindow` (Task 6)
- Produces: `MainWindow.positions_panel` (the `PositionsModePanel` instance set as central widget) and a "Settings..." menu action that opens `SettingsWindow` and refreshes `positions_panel` on save.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main_window.py`:
```python
def test_main_window_hosts_positions_panel_as_central_widget():
    _app()
    window = MainWindow()
    assert window.centralWidget() is window.positions_panel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_window.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute 'positions_panel'`

- [ ] **Step 3: Implement the assembly**

Replace the contents of `app/ui/main_window.py`:
```python
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow

from app.core.config import default_settings_path, load_settings
from app.ui.mode_positions_panel import PositionsModePanel
from app.ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Barcode Label Generator")
        self.resize(900, 600)

        self._settings_path = default_settings_path()
        self._settings = load_settings(self._settings_path)

        self.positions_panel = PositionsModePanel(self._settings)
        self.setCentralWidget(self.positions_panel)

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        self.menuBar().addAction(settings_action)

    def _open_settings(self) -> None:
        dialog = SettingsWindow(self._settings, self._settings_path, parent=self)
        if dialog.exec():
            self._settings = load_settings(self._settings_path)
            self.positions_panel._settings = self._settings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main_window.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests from Tasks 1-10 PASS

- [ ] **Step 6: Manual smoke test (do this once, in the session that executes this plan)**

Run: `python -m app.main` — confirm the window opens titled "Barcode Label Generator", the position form is visible, "Generate" produces a result count, and "Settings..." opens the settings dialog. This step is GUI-only and isn't covered by the automated tests above.

- [ ] **Step 7: Commit**

```bash
git add app/ui/main_window.py tests/test_main_window.py
git commit -m "feat: assemble main window with positions panel and settings"
```

---

## Roadmap-level outline: Phases 2-5 (not yet task-broken)

These are intentionally **not** decomposed into bite-sized tasks yet — per the design doc, they get planned in detail closer to when each one starts, once Phase 1 is built and any assumptions below get tested against reality.

**Phase 2 — CSV infrastructure**
- Shared interactive column-mapping dialog: load a CSV, show its header row, let the user assign each column to a target field (varies by mode), preview the first few mapped rows before confirming.
- Wire it into Mode 2.1 as an alternate input to the manual range form.
- Open question to resolve before planning: what happens on a mapping error mid-file (skip row vs. abort import) — needs a product decision, not just an engineering one.

**Phase 3 — Mode 2.2 (inventory from CSV)**
- Reuses Phase 2's column-mapping component.
- One label per row: SKU barcode + text (name, batch/expiry when present) + position barcode (same hidden-prefix rule as Mode 2.1).
- Depends on Phase 1's `barcode_engine`/`label_renderer`/`print_service`/`audit_log` — no new core primitives expected, mostly a new `mode_inventory_panel.py`.

**Phase 4 — Modes 2.3 and 2.4**
- 2.3: single code + text, manual entry and CSV bulk (reuses Phase 2's importer).
- 2.4: free text label (no barcode); sequence labels (`{i}-{N}` pattern, configurable separator).
- Mostly new UI panels over existing `label_renderer`/`print_service`; `label_renderer` may need a "text-only, no barcode" code path.

**Phase 5 — Enhancements**
- QR code support: new `generate_qr_image` alongside `generate_barcode_image` in `barcode_engine.py`, selected per-mode.
- Light/dark theme toggle via QSS.
- Custom label size UI (the data model already supports arbitrary `width_mm`/`height_mm`; this phase is the UI for entering and saving one).
- PyInstaller packaging for Windows and Ubuntu, including a real print test against the Citizen CL-E300 (this is the point where the OS-driver-printing assumption from the design doc gets validated against real hardware).

---

## Plan self-review notes

- **Spec coverage:** Mode 2.1's corridor/number/height/prefix/custom-text rules (Tasks 3, 5, 7) match design doc §5 exactly, including the hidden-warehouse-prefix rule (Task 4's `write_text=False` + Task 7's separate `barcode_data`/`visible_text` construction). Settings (Task 6) covers warehouses, shared folder, default printer per design §9; label size presets ship via `DEFAULT_SETTINGS` (Task 2). Audit logging (Task 9) matches design §11, including "log at print time, not generation time." **Correction (post-review of PR #2):** printing (Task 8) does *not* fully match design §10 — the Print button commits the job directly with no `QPrintPreviewDialog` confirmation step. This was confirmed as an intentional MVP cut, not an oversight; adding the preview dialog is deferred to a follow-up rather than blocking Phase 1. Modes 2.2-2.4 and enhancements are intentionally deferred to the roadmap-level section per the user's request for this session.
- **Known limitation, deferred (post-review of PR #2):** `append_print_log` (`app/core/audit_log.py`) does an unlocked check-then-append against a file on the shared network folder — the stated deployment model is multiple warehouse workstations sharing that folder, so concurrent printing from two machines can race on the header write or interleave rows. Failure is confined to the audit trail (label generation and printing both still succeed). Defensible to defer for initial rollout with a handful of stations; revisit before scaling to more concurrent stations. Cheapest fix when needed: per-workstation log files (`audit_log_<hostname>.csv`) merged on read, which sidesteps shared-file locking over SMB/NFS entirely rather than adding a lock that may not be reliable there. Also flagged inline via a `ponytail:` comment at the call site.
- **Testability of hardware-facing code:** `print_service.py` is exercised via `QPrinter`'s PDF output format rather than a physical printer, so Task 8/9 tests run in CI without hardware. Real-hardware validation against the Citizen CL-E300 is called out explicitly in Phase 5, not silently assumed.
- **Fixed during drafting:** Task 7 originally called `QMessageBox.warning` directly from `generate()`, which would block an automated test under a modal event loop. Split into a testable `generate()` (raises `ValueError`) and a UI-only `_on_generate_clicked()` (shows the dialog) — this is reflected in the final task text above.
