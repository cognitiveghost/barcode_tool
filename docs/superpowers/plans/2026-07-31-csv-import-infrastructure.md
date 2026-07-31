# Barcode Label Generator — Phase 2: CSV Import Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared, reusable interactive CSV column-mapping dialog and wire it into Mode 2.1 (warehouse positions) as an alternate input to the manual range form, so users can import a ready-made list of positions from a CSV file instead of typing a corridor/number/height range.

**Architecture:** Same layering as Phase 1 — pure logic in `app/core/` (CSV parsing + column mapping in a new `csv_import.py`; CSV-row-to-position-code translation added to the existing `position_generator.py`), Qt widgets in `app/ui/` (a new generic `CsvImportDialog`, wired into the existing `PositionsModePanel`). The dialog is deliberately generic (field-name/label pairs passed in by the caller) so Phase 3/4 (Modes 2.2–2.4) can reuse it without modification.

**Tech Stack:** Python 3.11+, stdlib `csv` module (no new dependency — see design doc §3, no new library is justified for CSV parsing), PySide6, pytest.

**Product decision (resolved before this plan was written):** When a CSV row fails to map to a usable position code (e.g. non-digit number, multi-character height), that row is **skipped and counted**, not aborted — the rest of the file still imports. The result summary reports how many rows were skipped.

## Global Constraints

- The application and all code/comments must be in English.
- No emojis anywhere in the UI.
- Must run locally on Windows 10/11 and Ubuntu 25+.
- The warehouse prefix must be embedded in the barcode's encoded data but must **never** appear in the visible printed text. CSV-imported codes go through the same `_render_labels` path as manually-typed ranges, so this is inherited automatically — no separate handling needed.
- No database — plain files only.

Full design rationale: `docs/superpowers/specs/2026-07-30-barcode-label-generator-design.md` (§2 CSV import, §5 Mode 2.1 "Alternate input — CSV", §13 roadmap Phase 2).

---

## Task 1: CSV parsing + column mapping (`app/core/csv_import.py`)

**Files:**
- Create: `app/core/csv_import.py`
- Test: `tests/test_csv_import.py`

**Interfaces:**
- Consumes: nothing beyond the stdlib `csv` module.
- Produces:
  - `read_csv(path: Path) -> tuple[list[str], list[list[str]]]` — reads a CSV file, returns `(header, rows)`. `header` is the first row; `rows` is every subsequent row as a list of raw string cells. Returns `([], [])` for an empty file.
  - `apply_mapping(header: list[str], rows: list[list[str]], mapping: dict[str, str | None]) -> list[dict[str, str]]` — `mapping` is `target_field_name -> source_column_name` (or `None` for unmapped). For each row, returns a dict `target_field_name -> cell value`. A field mapped to `None`, to a column name not present in `header`, or to a column past the end of a short row all resolve to `""` (never raises — this function does no domain validation, it only rearranges columns into named fields).

- [ ] **Step 1: Write the failing tests**

`tests/test_csv_import.py`:
```python
import csv

from app.core.csv_import import apply_mapping, read_csv


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_read_csv_returns_header_and_rows(tmp_path):
    path = tmp_path / "positions.csv"
    _write_csv(path, [
        ["Corridor", "Number", "Height"],
        ["H", "029", "A"],
        ["H", "030", "B"],
    ])

    header, rows = read_csv(path)

    assert header == ["Corridor", "Number", "Height"]
    assert rows == [["H", "029", "A"], ["H", "030", "B"]]


def test_read_csv_empty_file_returns_empty_header_and_rows(tmp_path):
    path = tmp_path / "empty.csv"
    _write_csv(path, [])

    header, rows = read_csv(path)

    assert header == []
    assert rows == []


def test_apply_mapping_builds_dicts_by_target_field():
    header = ["Corridor", "Number", "Height"]
    rows = [["H", "029", "A"], ["H", "030", "B"]]
    mapping = {"corridor": "Corridor", "number": "Number", "height": "Height"}

    result = apply_mapping(header, rows, mapping)

    assert result == [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": "B"},
    ]


def test_apply_mapping_unmapped_field_is_empty_string():
    header = ["Corridor", "Number"]
    rows = [["H", "029"]]
    mapping = {"corridor": "Corridor", "number": "Number", "height": None}

    result = apply_mapping(header, rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_missing_column_name_is_empty_string():
    header = ["Corridor", "Number"]
    rows = [["H", "029"]]
    mapping = {"corridor": "Corridor", "number": "Number", "height": "Nonexistent"}

    result = apply_mapping(header, rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_short_row_resolves_to_empty_string():
    header = ["Corridor", "Number", "Height"]
    rows = [["H", "029"]]  # missing the Height cell
    mapping = {"corridor": "Corridor", "number": "Number", "height": "Height"}

    result = apply_mapping(header, rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_csv_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.csv_import'`

- [ ] **Step 3: Implement csv_import.py**

`app/core/csv_import.py`:
```python
from __future__ import annotations

import csv
from pathlib import Path


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        all_rows = list(csv.reader(f))
    if not all_rows:
        return [], []
    return all_rows[0], all_rows[1:]


def apply_mapping(
    header: list[str],
    rows: list[list[str]],
    mapping: dict[str, str | None],
) -> list[dict[str, str]]:
    column_indexes = {
        field: header.index(column) if column in header else None
        for field, column in mapping.items()
    }

    mapped_rows = []
    for row in rows:
        mapped_row = {}
        for field, index in column_indexes.items():
            mapped_row[field] = row[index] if index is not None and index < len(row) else ""
        mapped_rows.append(mapped_row)
    return mapped_rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_csv_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/csv_import.py tests/test_csv_import.py
git commit -m "feat: CSV parsing and column-mapping core logic"
```

---

## Task 2: CSV rows → position codes, with skip-and-continue (`position_generator.py`)

**Files:**
- Modify: `app/core/position_generator.py`
- Modify: `tests/test_position_generator.py`

**Interfaces:**
- Consumes: nothing new (pure logic, same as the rest of the module).
- Produces:
  - `format_position_code(corridor: str, number: str, height: str = "") -> str` — validates and formats a single position code (same rules `generate_position_codes` already enforces per-number: corridor must be ASCII, number must be digits and `<= NUMBER_MAX`, height if given must be a single ASCII character). Raises `ValueError` on any violation. `generate_position_codes` is refactored to call this internally (no behavior change — existing tests must still pass unmodified).
  - `codes_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[str], list[int]]` — consumes rows shaped like `apply_mapping`'s output (keys among `position_code`, `corridor`, `number`, `height`; any may be absent or empty). For each row (1-indexed in the returned skip list): if `position_code` is non-empty, use it directly as the code (after an ASCII check); otherwise build a code from `corridor`/`number`/`height` via `format_position_code`. Rows that fail validation are **skipped, not raised** — collected in the second return value (1-indexed row numbers) so the caller can report a summary. Returns `(codes, skipped_row_numbers)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_position_generator.py`:
```python
from app.core.position_generator import codes_from_csv_rows, format_position_code


def test_format_position_code_pads_and_combines():
    assert format_position_code("H", "29", "A") == "H029A"


def test_format_position_code_no_height():
    assert format_position_code("H", "29") == "H029"


def test_format_position_code_rejects_non_digit_number():
    with pytest.raises(ValueError):
        format_position_code("H", "abc")


def test_format_position_code_rejects_multi_letter_height():
    with pytest.raises(ValueError):
        format_position_code("H", "29", "AB")


def test_format_position_code_rejects_number_above_max():
    with pytest.raises(ValueError):
        format_position_code("H", "1000")


def test_codes_from_csv_rows_builds_codes_from_components():
    rows = [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": ""},
    ]

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["H029A", "H030"]
    assert skipped == []


def test_codes_from_csv_rows_prefers_position_code_when_present():
    rows = [{"position_code": "C001H099Z", "corridor": "X", "number": "1", "height": ""}]

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["C001H099Z"]


def test_codes_from_csv_rows_skips_invalid_rows_and_continues():
    rows = [
        {"corridor": "H", "number": "029", "height": ""},
        {"corridor": "H", "number": "not-a-number", "height": ""},
        {"corridor": "H", "number": "030", "height": ""},
    ]

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["H029", "H030"]
    assert skipped == [2]


def test_codes_from_csv_rows_handles_missing_keys():
    rows = [{"corridor": "H", "number": "029"}]  # no "height" key at all

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["H029"]
    assert skipped == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_position_generator.py -v`
Expected: FAIL with `ImportError: cannot import name 'codes_from_csv_rows'` (the new tests fail; all pre-existing tests in this file still pass since nothing has changed yet).

- [ ] **Step 3: Refactor and extend position_generator.py**

Replace the full contents of `app/core/position_generator.py`:
```python
from __future__ import annotations

NUMBER_WIDTH = 3
NUMBER_MAX = 10**NUMBER_WIDTH - 1


def format_position_code(corridor: str, number: str, height: str = "") -> str:
    if not corridor.isascii():
        raise ValueError("corridor must contain only ASCII characters (Code128 can't encode this)")
    if not number.isdigit():
        raise ValueError("number must be digits")
    if int(number) > NUMBER_MAX:
        raise ValueError(f"position numbers must be at most {NUMBER_MAX}")
    if height and (len(height) != 1 or not height.isascii()):
        raise ValueError("height must be a single ASCII character")
    return f"{corridor}{number.zfill(NUMBER_WIDTH)}{height}"


def generate_position_codes(
    corridor: str,
    number_from: str,
    number_to: str | None = None,
    height_from: str | None = None,
    height_to: str | None = None,
) -> list[str]:
    if number_to is None:
        number_to = number_from
    if not number_from.isdigit() or not number_to.isdigit():
        raise ValueError("number_from and number_to must be digits")
    if not corridor.isascii():
        raise ValueError("corridor must contain only ASCII characters (Code128 can't encode this)")

    start, end = int(number_from), int(number_to)
    if start > NUMBER_MAX or end > NUMBER_MAX:
        raise ValueError(f"position numbers must be at most {NUMBER_MAX}")
    if start > end:
        raise ValueError("number_from must be <= number_to")

    heights: list[str] = [""]
    if height_from is not None:
        if height_to is None:
            height_to = height_from
        if len(height_from) != 1 or len(height_to) != 1:
            raise ValueError("height letters must be single characters")
        if not height_from.isascii() or not height_to.isascii():
            raise ValueError("height letters must be ASCII characters (Code128 can't encode this)")
        if height_from > height_to:
            raise ValueError("height_from must be <= height_to")
        heights = [chr(c) for c in range(ord(height_from), ord(height_to) + 1)]

    return [
        format_position_code(corridor, str(number), height)
        for number in range(start, end + 1)
        for height in heights
    ]


def codes_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[str], list[int]]:
    codes: list[str] = []
    skipped_rows: list[int] = []
    for row_number, row in enumerate(rows, start=1):
        position_code = (row.get("position_code") or "").strip()
        try:
            if position_code:
                if not position_code.isascii():
                    raise ValueError("position code must be ASCII")
                codes.append(position_code)
            else:
                corridor = (row.get("corridor") or "").strip()
                number = (row.get("number") or "").strip()
                height = (row.get("height") or "").strip()
                codes.append(format_position_code(corridor, number, height))
        except ValueError:
            skipped_rows.append(row_number)
    return codes, skipped_rows
```

- [ ] **Step 4: Run the full test file to verify everything passes**

Run: `pytest tests/test_position_generator.py -v`
Expected: PASS — both the pre-existing tests (unchanged behavior) and the new ones.

- [ ] **Step 5: Commit**

```bash
git add app/core/position_generator.py tests/test_position_generator.py
git commit -m "feat: derive position codes from CSV rows with skip-and-continue"
```

---

## Task 3: Generic CSV import dialog (`app/ui/csv_import_dialog.py`)

**Files:**
- Create: `app/ui/csv_import_dialog.py`
- Test: `tests/test_csv_import_dialog.py`

**Interfaces:**
- Consumes: `app.core.csv_import.{read_csv, apply_mapping}` (Task 1).
- Produces: `app.ui.csv_import_dialog.CsvImportDialog(QDialog)`:
  - `__init__(self, fields: list[tuple[str, str]], parent=None)` — `fields` is `[(target_field_name, display_label), ...]`, defined by the caller (e.g. Mode 2.1 passes corridor/number/height/position_code; Mode 2.2 will later pass its own field list).
  - `field_combos: dict[str, QComboBox]` — one combo per field, keyed by field name. Each combo's first entry is always `"-- none --"`, followed by the CSV's column names once a file is loaded.
  - `preview_table: QTableWidget` — one column per field (headers = display labels), showing up to 5 mapped rows, refreshed whenever the loaded file or any mapping selection changes.
  - `load_csv(self, path: Path) -> None` — reads the file via `read_csv`, repopulates every combo's column choices, refreshes the preview. Exposed directly (not only via the Browse button) so tests don't need to drive a native file picker.
  - `get_mapped_rows(self) -> list[dict[str, str]]` — reads the current combo selections into a mapping and returns `apply_mapping`'s result. Returns `[]` if no file has been loaded yet.

- [ ] **Step 1: Write the failing tests**

`tests/test_csv_import_dialog.py`:
```python
import csv

from PySide6.QtWidgets import QApplication

from app.ui.csv_import_dialog import CsvImportDialog

FIELDS = [("corridor", "Corridor"), ("number", "Number"), ("height", "Height")]


def _app():
    return QApplication.instance() or QApplication([])


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_get_mapped_rows_before_load_returns_empty_list():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert dialog.get_mapped_rows() == []


def test_load_csv_populates_column_choices(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number", "Height"], ["H", "029", "A"]])
    dialog = CsvImportDialog(FIELDS)

    dialog.load_csv(path)

    choices = [
        dialog.field_combos["corridor"].itemText(i)
        for i in range(dialog.field_combos["corridor"].count())
    ]
    assert choices == ["-- none --", "Corridor", "Number", "Height"]


def test_get_mapped_rows_uses_selected_columns(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number", "Height"], ["H", "029", "A"], ["H", "030", "B"]])
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)
    dialog.field_combos["corridor"].setCurrentText("Corridor")
    dialog.field_combos["number"].setCurrentText("Number")
    dialog.field_combos["height"].setCurrentText("Height")

    rows = dialog.get_mapped_rows()

    assert rows == [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": "B"},
    ]


def test_unmapped_field_defaults_to_empty_string(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number"], ["H", "029"]])
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)
    dialog.field_combos["corridor"].setCurrentText("Corridor")
    dialog.field_combos["number"].setCurrentText("Number")
    # "height" left as "-- none --"

    rows = dialog.get_mapped_rows()

    assert rows == [{"corridor": "H", "number": "029", "height": ""}]


def test_preview_table_shows_mapped_rows(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number"], ["H", "029"], ["H", "030"]])
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)

    dialog.field_combos["corridor"].setCurrentText("Corridor")
    dialog.field_combos["number"].setCurrentText("Number")

    assert dialog.preview_table.rowCount() == 2
    assert dialog.preview_table.item(0, 0).text() == "H"
    assert dialog.preview_table.item(0, 1).text() == "029"


def test_loading_a_second_file_replaces_column_choices(tmp_path):
    _app()
    first = tmp_path / "first.csv"
    _write_csv(first, [["A", "B"], ["1", "2"]])
    second = tmp_path / "second.csv"
    _write_csv(second, [["X", "Y", "Z"], ["1", "2", "3"]])
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(first)

    dialog.load_csv(second)

    choices = [
        dialog.field_combos["corridor"].itemText(i)
        for i in range(dialog.field_combos["corridor"].count())
    ]
    assert choices == ["-- none --", "X", "Y", "Z"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_csv_import_dialog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ui.csv_import_dialog'`

- [ ] **Step 3: Implement csv_import_dialog.py**

`app/ui/csv_import_dialog.py`:
```python
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.csv_import import apply_mapping, read_csv

NONE_OPTION = "-- none --"
PREVIEW_ROW_LIMIT = 5


class CsvImportDialog(QDialog):
    def __init__(self, fields: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._fields = fields
        self._header: list[str] = []
        self._rows: list[list[str]] = []

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)

        self.field_combos: dict[str, QComboBox] = {}
        form = QFormLayout()
        for name, label in fields:
            combo = QComboBox()
            combo.addItem(NONE_OPTION)
            combo.currentIndexChanged.connect(self._refresh_preview)
            self.field_combos[name] = combo
            form.addRow(label, combo)

        self.preview_table = QTableWidget(0, len(fields))
        self.preview_table.setHorizontalHeaderLabels([label for _, label in fields])

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(browse_button)
        layout.addLayout(form)
        layout.addWidget(self.preview_table)
        layout.addWidget(buttons)

    def _on_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import CSV", filter="CSV files (*.csv)")
        if path:
            self.load_csv(Path(path))

    def load_csv(self, path: Path) -> None:
        self._header, self._rows = read_csv(path)
        for combo in self.field_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(NONE_OPTION)
            combo.addItems(self._header)
            combo.blockSignals(False)
        self._refresh_preview()

    def _current_mapping(self) -> dict[str, str | None]:
        mapping = {}
        for name, combo in self.field_combos.items():
            text = combo.currentText()
            mapping[name] = None if text == NONE_OPTION else text
        return mapping

    def get_mapped_rows(self) -> list[dict[str, str]]:
        return apply_mapping(self._header, self._rows, self._current_mapping())

    def _refresh_preview(self) -> None:
        mapped_rows = self.get_mapped_rows()[:PREVIEW_ROW_LIMIT]
        self.preview_table.setRowCount(len(mapped_rows))
        for row_index, mapped_row in enumerate(mapped_rows):
            for col_index, (name, _label) in enumerate(self._fields):
                self.preview_table.setItem(
                    row_index, col_index, QTableWidgetItem(mapped_row.get(name, ""))
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_csv_import_dialog.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/csv_import_dialog.py tests/test_csv_import_dialog.py
git commit -m "feat: generic interactive CSV column-mapping dialog"
```

---

## Task 4: Wire CSV import into Mode 2.1 (`mode_positions_panel.py`)

**Files:**
- Modify: `app/ui/mode_positions_panel.py`
- Modify: `tests/test_mode_positions_panel.py`

**Interfaces:**
- Consumes:
  - `app.core.position_generator.codes_from_csv_rows(...)` (Task 2)
  - `app.ui.csv_import_dialog.CsvImportDialog` (Task 3)
- Produces (additions to `PositionsModePanel`):
  - `import_csv_button: QPushButton`
  - `generate_from_rows(self, rows: list[dict[str, str]]) -> list[tuple[str, Image.Image]]` — same rendering path as `generate()`, but the codes come from already-mapped CSV rows via `codes_from_csv_rows`. Raises `ValueError` if zero valid codes result (nothing to render). Updates `result_label` with a skipped-row count when any rows were skipped, e.g. `"18 labels generated (2 rows skipped)"`.
  - `_render_labels(self, codes: list[str]) -> list[tuple[str, Image.Image]]` — the rendering loop extracted out of `generate()` so both entry points share it (sets `generated_codes`, `generated_labels`, `_generated_label_size`; raises `ValueError` if no label size is selected).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mode_positions_panel.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: FAIL with `AttributeError: 'PositionsModePanel' object has no attribute 'generate_from_rows'` (and later, `'import_csv_button'`).

- [ ] **Step 3: Implement the wiring**

Add to the imports at the top of `app/ui/mode_positions_panel.py` (alongside the existing ones):
```python
from app.core.position_generator import NUMBER_MAX, codes_from_csv_rows, generate_position_codes
from app.ui.csv_import_dialog import CsvImportDialog
```

Add this constant near the top of the module, after the imports:
```python
POSITION_CSV_FIELDS = [
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]
```

In `__init__`, add the button (right after `generate_button` is created and wired, before the `form`/`layout` construction that follows it):
```python
        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)
```

Add it to the layout, after `generate_button` and before `result_label`:
```python
        layout.addWidget(generate_button)
        layout.addWidget(self.import_csv_button)
        layout.addWidget(self.result_label)
```

Replace the body of `generate()` and add the new methods. The full set of methods from `generate()` onward becomes:
```python
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
        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")
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
        self._generated_label_size = label_size
        return results

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(POSITION_CSV_FIELDS, parent=self)
        if not dialog.exec():
            return
        try:
            self.generate_from_rows(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))
```

(`print_current_labels` below these methods is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mode_positions_panel.py -v`
Expected: PASS — including every pre-existing test in this file (the refactor must not change `generate()`'s observable behavior).

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py
git commit -m "feat: wire CSV import as alternate input to Mode 2.1"
```

---

## Task 5: Full regression check

No file changes in this task — it exists to catch integration issues between Tasks 1-4 before calling Phase 2 done.

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest -v`
Expected: every test across the whole repo passes, including all of Phase 1's tests (Tasks 1-10 of the prior plan) and Phase 2's new tests (Tasks 1-4 above).

- [ ] **Step 2: Run the linter**

Run: `ruff check .`
Expected: no errors (CI's `lint` job runs this same command).

- [ ] **Step 3: Manual smoke test (do this once, in the session that executes this plan)**

Run: `python -m app.main`. In the Positions panel:
1. Click "Import CSV..." — confirm the dialog opens with a "Browse..." button, four mapping rows (Position code / Corridor / Number / Height), and an empty preview table.
2. Click "Browse...", pick a small CSV file with a header row and a few data rows (e.g. columns `Corridor,Number,Height` with 2-3 rows, one row with a non-numeric Number to test the skip path).
3. Map "Corridor" → `Corridor`, "Number" → `Number`, "Height" → `Height`; confirm the preview table updates live to show the mapped values.
4. Click OK; confirm the main panel's result label shows the generated count and, if the test file had a bad row, the skipped-row count.
5. Click "Print" and confirm it still produces a PDF/print job as before (Phase 1 behavior unaffected).

This step is GUI-only and isn't covered by the automated tests above.

---

## Plan self-review notes

- **Spec coverage:** Design doc §5 "Alternate input — CSV" (columns can map to corridor/number/height, or to a single already-formed position code) is covered by `POSITION_CSV_FIELDS` and `codes_from_csv_rows`'s `position_code`-takes-priority behavior (Task 2/4). §2's "one shared import component reused by every mode" is covered by `CsvImportDialog` taking a generic `fields` list rather than being Mode-2.1-specific (Task 3) — Phase 3/4 will pass their own field lists without modifying the dialog. The roadmap's explicit open question (skip vs. abort on a mapping error) is resolved per the product decision at the top of this plan and implemented as `codes_from_csv_rows`'s skip-and-continue behavior with a reported count (Task 2/4).
- **Out of scope for this phase, by design:** domain-specific row validation/import for Modes 2.2-2.4 (Phase 3/4 work, per roadmap); named/reusable column-mapping presets (explicitly deferred, design doc §12); enforcing "required" fields in the generic dialog itself (deferred to each mode's own row-interpretation logic, since "required" varies per mode and the dialog is intentionally domain-agnostic).
- **Backward compatibility:** Task 2 refactors `generate_position_codes` to call the new `format_position_code` internally; all of Phase 1's existing tests in `tests/test_position_generator.py` and `tests/test_mode_positions_panel.py` are required to keep passing unmodified (verified explicitly in Task 2 Step 4 and Task 4 Step 4) — this is a refactor, not a behavior change.
- **Type/interface consistency:** `codes_from_csv_rows` (Task 2) returns `(list[str], list[int])`; `generate_from_rows` (Task 4) destructures it the same way. `CsvImportDialog.get_mapped_rows()` (Task 3) returns exactly the shape `codes_from_csv_rows` expects (`list[dict[str, str]]`) via `apply_mapping` (Task 1) — no adapter needed between the dialog and the position-code logic.
