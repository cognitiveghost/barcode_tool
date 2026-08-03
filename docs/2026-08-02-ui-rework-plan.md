# UI Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the barcode/text case mismatch at its root, remove the redundant
height checkbox, make the CSV import dialog and inventory table usable, and have
the app recognise a CSV layout it has seen before.

**Architecture:** Correctness lives in `app/core/position_generator.py` — both
panels and both CSV importers already route through `format_position_code` and
`parse_position_code`, so uppercasing there covers every entry path. The Qt input
mask is then presentation. CSV column mapping moves from column *names* to column
*indexes*, which both fixes duplicate headers and makes a remembered mapping safe
to replay. Window and dialog geometry go to `QSettings` (per-machine), mapping
memory goes to `settings.json` (inspectable by the operator).

**Tech Stack:** Python 3.14, PySide6 (Qt 6), pytest. No new dependencies.

Spec: [docs/2026-08-02-ui-rework-design.md](docs/2026-08-02-ui-rework-design.md).
Parent audit: [docs/2026-08-02-stabilization-patch-plan.md](docs/2026-08-02-stabilization-patch-plan.md).

## Global Constraints

- **No new dependencies.** Everything here is stdlib or already-installed PySide6.
- **Run tests with the repo venv:** `.venv/bin/python -m pytest`. `conftest.py`
  already sets `QT_QPA_PLATFORM=offscreen`; do not set it per-test.
- **Baseline is 190 passing tests at `ce31dcf`.** Every task ends green. A task
  that changes an existing test's expectations must update that test in the same
  commit and say so in the commit message.
- **Qt widget tests** get a `QApplication` via the local `_app()` helper pattern
  already used in `tests/test_csv_import_dialog.py` and
  `tests/test_mode_positions_panel.py`. Reuse it; do not add pytest-qt.
- **Position codes are uppercase A–Z + digits.** After Task 1, no code path may
  emit a lowercase letter into a barcode payload.
- **Branch:** `GUI-Impruvment` (already checked out).

---

### Task 1: Uppercase position codes in core

Closes §0.7, and folds in §0.3 (corridor must be one letter) and §0.4 (height
range must not span punctuation) because all three are edits to the same two
functions.

**Files:**
- Modify: `app/core/position_generator.py:9-18` (`format_position_code`),
  `:21-57` (`generate_position_codes`), `:83-94` (`parse_position_code`)
- Test: `tests/test_position_generator.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `format_position_code(corridor: str, number: str, height: str = "") -> str`
  and `parse_position_code(code: str) -> tuple[str, str, str]`, both returning
  uppercase. Signatures unchanged. Tasks 2, 3 and 8 depend on this behaviour.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_position_generator.py`:

```python
def test_lowercase_corridor_and_height_are_uppercased():
    assert format_position_code("h", "29", "a") == "H029A"


def test_generate_uppercases_lowercase_input():
    assert generate_position_codes("h", "1", "1", "a", "b") == ["H001A", "H001B"]


def test_parse_position_code_uppercases():
    assert parse_position_code("h001a") == ("H", "001", "A")


def test_barcode_payload_matches_printed_text_for_lowercase_input():
    # The bug this task exists for: payload was "h001a" while the label read
    # "H-001-A", so the label scanned as something other than what it showed.
    code = generate_position_codes("h", "1", "1", "a")[0]
    letters_in_payload = [c for c in code if c.isalpha()]
    letters_on_label = [c for c in display_position_code(code) if c.isalpha()]
    assert letters_in_payload == letters_on_label


def test_format_position_code_rejects_empty_corridor():
    with pytest.raises(ValueError):
        format_position_code("", "1")


def test_format_position_code_rejects_multi_letter_corridor():
    with pytest.raises(ValueError):
        format_position_code("AB", "1")


def test_format_position_code_rejects_non_letter_corridor():
    with pytest.raises(ValueError):
        format_position_code("%", "1")


def test_format_position_code_rejects_non_letter_height():
    with pytest.raises(ValueError):
        format_position_code("H", "1", "%")


def test_height_range_does_not_span_punctuation():
    # ord('A')..ord('z') used to walk through [ \ ] ^ _ ` and emit 58 codes.
    with pytest.raises(ValueError):
        generate_position_codes("H", "1", "1", "A", "z")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_position_generator.py -v`

Expected: the eight new tests FAIL. Specifically
`test_lowercase_corridor_and_height_are_uppercased` fails with
`AssertionError: assert 'h029a' == 'H029A'`, and
`test_height_range_does_not_span_punctuation` fails with `DID NOT RAISE`.

- [ ] **Step 3: Implement uppercasing and letter validation**

In `app/core/position_generator.py`, add near the top:

```python
import string

_LETTERS = frozenset(string.ascii_uppercase)
```

`_LETTERS` must be a `frozenset`, not the plain `string.ascii_uppercase` string —
`"" in string.ascii_uppercase` is `True`, which would let an empty corridor
through the exact check we are adding.

Replace `format_position_code`:

```python
def format_position_code(corridor: str, number: str, height: str = "") -> str:
    corridor = corridor.upper()
    height = height.upper()
    if corridor not in _LETTERS:
        raise ValueError("corridor must be exactly one ASCII letter, e.g. 'H'")
    if not number.isdigit():
        raise ValueError("number must be digits")
    if int(number) > NUMBER_MAX:
        raise ValueError(f"position numbers must be at most {NUMBER_MAX}")
    if height and height not in _LETTERS:
        raise ValueError("height must be a single ASCII letter, e.g. 'A'")
    return f"{corridor}{number.zfill(NUMBER_WIDTH)}{height}"
```

In `generate_position_codes`, replace the corridor check and the height block:

```python
    corridor = corridor.upper()
    if corridor not in _LETTERS:
        raise ValueError("corridor must be exactly one ASCII letter, e.g. 'H'")
```

```python
    heights: list[str] = [""]
    if height_from is not None:
        height_from = height_from.upper()
        height_to = height_from if height_to is None else height_to.upper()
        if height_from not in _LETTERS or height_to not in _LETTERS:
            raise ValueError("height letters must be A-Z")
        if height_from > height_to:
            raise ValueError("height_from must be <= height_to")
        heights = [chr(c) for c in range(ord(height_from), ord(height_to) + 1)]
```

In `parse_position_code`, uppercase before matching:

```python
def parse_position_code(code: str) -> tuple[str, str, str]:
    code = code.upper()
    if not _POSITION_CODE_PATTERN.fullmatch(code):
```

Leave `_POSITION_CODE_PATTERN` as `[A-Za-z][0-9]+[A-Za-z]?` — it still matches,
and narrowing it is a separate change with no benefit here.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green. `test_non_ascii_corridor_raises_value_error` still passes
(a non-ASCII corridor is not in `_LETTERS`). If
`tests/test_inventory_import.py` or `tests/test_mode_positions_panel.py` fail on
a case expectation, the fixture used lowercase — update the *expectation* to
uppercase, never the production code.

- [ ] **Step 5: Commit**

```bash
git add app/core/position_generator.py tests/test_position_generator.py
git commit -m "fix: uppercase position codes in core so barcode matches printed text

The payload carried whatever the operator typed while only the caption was
uppercased, so a lowercase corridor printed a label reading H-001-A that
scanned as h001a. Normalizing in format_position_code/parse_position_code
covers typed input and both CSV importers in one edit.

Also folds in the one-letter corridor check (0.3) and the A-Z height range
check (0.4), which are edits to the same two functions.

Payloads generated from lowercase input change from Ch001a to CH001A."
```

---

### Task 2: Force uppercase in the positions letter fields

Closes §4.6.

**Files:**
- Modify: `app/ui/mode_positions_panel.py:9-10` (imports), `:36`, `:65-67`, `:76-80`
- Test: `tests/test_mode_positions_panel.py`

**Interfaces:**
- Consumes: Task 1's uppercase core (this task is the visible affordance, not the
  correctness boundary).
- Produces: `corridor_edit`, `height_from_edit`, `height_to_edit` return
  uppercase from `.text()`, and `""` when empty.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mode_positions_panel.py`:

```python
def test_letter_fields_force_uppercase():
    _app()
    panel = PositionsModePanel(SETTINGS)

    panel.corridor_edit.setText("h")
    panel.height_from_edit.setText("a")
    panel.height_to_edit.setText("c")

    assert panel.corridor_edit.text() == "H"
    assert panel.height_from_edit.text() == "A"
    assert panel.height_to_edit.text() == "C"


def test_empty_letter_fields_are_still_empty_strings():
    # An input mask can leave placeholder characters behind; the panel's
    # `text() or None` logic depends on empty staying "".
    _app()
    panel = PositionsModePanel(SETTINGS)

    assert panel.corridor_edit.text() == ""
    assert panel.height_from_edit.text() == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mode_positions_panel.py -k uppercase -v`

Expected: `test_letter_fields_force_uppercase` FAILS with
`AssertionError: assert 'h' == 'H'`.

- [ ] **Step 3: Replace the validators with an input mask**

In `app/ui/mode_positions_panel.py`, delete line 36:

```python
_LETTER_VALIDATOR = QRegularExpressionValidator(QRegularExpression("[A-Za-z]"))
```

Delete these two imports (nothing else uses them — grep to confirm):

```python
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator
```

`QIntValidator` is still used by the number fields, so keep it:

```python
from PySide6.QtGui import QIntValidator
```

Replace each `setValidator(_LETTER_VALIDATOR)` + `setMaxLength(1)` pair:

```python
        self.corridor_edit = QLineEdit()
        self.corridor_edit.setInputMask(">a")
```

```python
        self.height_from_edit = QLineEdit()
        self.height_from_edit.setInputMask(">a")
        self.height_to_edit = QLineEdit()
        self.height_to_edit.setInputMask(">a")
```

`>` forces every following character to uppercase; `a` is one *optional* ASCII
letter. Verified against this repo's PySide6: empty `text()` is `""`, `setText("a")`
yields `"A"`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py
git commit -m "feat: force uppercase in corridor and height fields

setInputMask('>a') replaces a validator plus a maxLength call on each of the
three letter fields, and shows the operator what will actually be printed."
```

---

### Task 3: Delete the "Use height" checkbox

Closes §4.7.

**Files:**
- Modify: `app/ui/mode_positions_panel.py:74`, `:102`, `:146-151` (`generate`),
  and the `QCheckBox` import at `:12`
- Test: `tests/test_mode_positions_panel.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `PositionsModePanel` no longer has a `height_enabled_check`
  attribute. Height applies iff `height_from_edit.text()` is non-empty.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mode_positions_panel.py`:

```python
def test_height_applies_without_a_checkbox():
    _app()
    panel = PositionsModePanel(SETTINGS)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.height_from_edit.setText("A")
    panel.height_to_edit.setText("B")

    results = panel.generate()

    assert [code for code, _ in results] == ["H029A", "H029B"]


def test_no_height_letter_means_no_height_suffix():
    _app()
    panel = PositionsModePanel(SETTINGS)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")

    results = panel.generate()

    assert [code for code, _ in results] == ["H029"]


def test_height_checkbox_is_gone():
    _app()
    panel = PositionsModePanel(SETTINGS)

    assert not hasattr(panel, "height_enabled_check")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mode_positions_panel.py -k height -v`

Expected: `test_height_applies_without_a_checkbox` FAILS — `generate()` returns
`["H029"]` because the checkbox is unchecked. `test_height_checkbox_is_gone`
FAILS on the `hasattr` assertion.

- [ ] **Step 3: Remove the checkbox**

Delete line 74 (`self.height_enabled_check = QCheckBox("Use height")`) and line
102 (`form.addRow(self.height_enabled_check)`). Remove `QCheckBox` from the
`PySide6.QtWidgets` import list.

In `generate()`, replace the first four lines:

```python
    def generate(self) -> list[tuple[str, Image.Image]]:
        height_from = self.height_from_edit.text() or None
        height_to = self.height_to_edit.text() or None
```

The `if not self.height_enabled_check.isChecked():` branch goes away entirely —
an empty height field already yields `None`, and core already defaults
`height_to` to `height_from`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green. Nothing else references `height_enabled_check` — confirmed
by grep across `app/` and `tests/` before this task was written.

- [ ] **Step 5: Commit**

```bash
git add app/ui/mode_positions_panel.py tests/test_mode_positions_panel.py
git commit -m "refactor: drop the 'Use height' checkbox

With height enabled by typing a height letter, the checkbox is derivable state
that can only ever disagree with the fields it guards."
```

---

### Task 4: Merge loaded settings over the defaults

Prerequisite for Task 6 (§1.1, partial). Without this, a `settings.json` written
by an older build has no `csv_mappings` key and the recall path raises on the
first import.

**Scope note:** this task implements *only* the merge. The rest of §1.1 (atomic
write, `settings.json.corrupt` recovery) stays Phase 1 work in the parent plan.

**Files:**
- Modify: `app/core/config.py:6-12` (`DEFAULT_SETTINGS`), `:19-23` (`load_settings`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_settings(path) -> dict` always contains every key in
  `DEFAULT_SETTINGS`. `DEFAULT_SETTINGS` gains `"csv_mappings": {}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_load_settings_fills_in_keys_missing_from_an_older_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"shared_folder": "/mnt/shared"}), encoding="utf-8")

    loaded = load_settings(path)

    assert loaded["shared_folder"] == "/mnt/shared"
    assert loaded["csv_mappings"] == {}
    assert loaded["warehouses"] == []


def test_load_settings_does_not_share_mutable_defaults(tmp_path):
    first = load_settings(tmp_path / "a.json")
    first["warehouses"].append({"name": "Main", "prefix": "C001"})

    second = load_settings(tmp_path / "b.json")

    assert second["warehouses"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`

Expected: `test_load_settings_fills_in_keys_missing_from_an_older_file` FAILS
with `KeyError: 'csv_mappings'`.

- [ ] **Step 3: Add the key and merge on load**

```python
DEFAULT_SETTINGS = {
    "shared_folder": "",
    "default_printer": "",
    "print_mode": "driver",
    "raw_zpl_target": "",
    "warehouses": [],
    "csv_mappings": {},
}


def _defaults() -> dict:
    # Deep copy via JSON: DEFAULT_SETTINGS holds a list and a dict, and callers
    # mutate what they get back.
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def load_settings(path: Path) -> dict:
    settings = _defaults()
    if not path.exists():
        return settings
    with path.open("r", encoding="utf-8") as f:
        settings.update(json.load(f))
    return settings
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green. `test_load_settings_returns_defaults_when_missing` still
passes — the merged result equals `DEFAULT_SETTINGS` when the file is absent.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py tests/test_config.py
git commit -m "fix: merge loaded settings over the defaults

A settings.json from an older build was returned as-is, so any newly added key
was simply missing at the call site. Adds the csv_mappings key that Task 6
needs."
```

---

### Task 5: Map CSV columns by index, not by name

Closes §3.3, and is a prerequisite for Task 6 — a remembered mapping stored by
column name would replay the duplicate-header bug on every import.

**Files:**
- Modify: `app/core/csv_import.py:19-35` (`apply_mapping`),
  `app/ui/csv_import_dialog.py:37-42`, `:65-83`
- Test: `tests/test_csv_import.py`, `tests/test_csv_import_dialog.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `apply_mapping(rows: list[list[str]], mapping: dict[str, int | None]) -> list[dict[str, str]]`
  — **the `header` parameter is gone**. `CsvImportDialog._current_mapping() -> dict[str, int | None]`.
  Task 6 stores exactly what `_current_mapping()` returns.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_csv_import.py`:

```python
def test_apply_mapping_resolves_duplicate_header_names_by_index():
    # header ['code', 'name', 'code'] used to resolve both 'code' fields to
    # column 0, so the third column was unreachable.
    rows = [["A1", "Widget", "B2"]]
    mapping = {"sku": 0, "name": 1, "alt_sku": 2}

    result = apply_mapping(rows, mapping)

    assert result == [{"sku": "A1", "name": "Widget", "alt_sku": "B2"}]
```

Rewrite the four existing `apply_mapping` tests in that file to pass indexes and
drop the `header` argument. For example:

```python
def test_apply_mapping_builds_dicts_by_target_field():
    rows = [["H", "029", "A"], ["H", "030", "B"]]
    mapping = {"corridor": 0, "number": 1, "height": 2}

    result = apply_mapping(rows, mapping)

    assert result == [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": "B"},
    ]


def test_apply_mapping_unmapped_field_is_empty_string():
    rows = [["H", "029"]]
    mapping = {"corridor": 0, "number": 1, "height": None}

    result = apply_mapping(rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_index_past_end_of_row_is_empty_string():
    rows = [["H", "029"]]  # missing the Height cell
    mapping = {"corridor": 0, "number": 1, "height": 2}

    result = apply_mapping(rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]
```

`test_apply_mapping_missing_column_name_is_empty_string` has no meaning once
mapping is by index — delete it; the case it covered is now
`test_apply_mapping_index_past_end_of_row_is_empty_string`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_csv_import.py -v`

Expected: every `apply_mapping` test FAILS with
`TypeError: apply_mapping() missing 1 required positional argument`.

- [ ] **Step 3: Take indexes in `apply_mapping`**

```python
def apply_mapping(
    rows: list[list[str]],
    mapping: dict[str, int | None],
) -> list[dict[str, str]]:
    mapped_rows = []
    for row in rows:
        mapped_row = {}
        for field, index in mapping.items():
            mapped_row[field] = row[index] if index is not None and index < len(row) else ""
        mapped_rows.append(mapped_row)
    return mapped_rows
```

The `header.index(column) if column in header else None` lookup — the actual
duplicate-header bug — is deleted, not patched.

- [ ] **Step 4: Carry the index as combo item data**

In `app/ui/csv_import_dialog.py`, the combos must store the column index and
disambiguate repeated names. Replace `load_csv` and `_current_mapping`:

```python
    def load_csv(self, path: Path) -> None:
        self._header, self._rows = read_csv(path)
        seen: dict[str, int] = {}
        for combo in self.field_combos.values():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(NONE_OPTION, None)
            for index, name in enumerate(self._header):
                combo.addItem(name, index)
            combo.blockSignals(False)
        # Repeated header names are indistinguishable in the dropdown, so show
        # the column number on the duplicates only.
        for name in self._header:
            seen[name] = seen.get(name, 0) + 1
        for combo in self.field_combos.values():
            for index, name in enumerate(self._header):
                if seen[name] > 1:
                    combo.setItemText(index + 1, f"{name} (col {index + 1})")
        self._refresh_preview()

    def _current_mapping(self) -> dict[str, int | None]:
        return {name: combo.currentData() for name, combo in self.field_combos.items()}

    def get_mapped_rows(self) -> list[dict[str, str]]:
        return apply_mapping(self._rows, self._current_mapping())
```

- [ ] **Step 5: Update the dialog tests that select columns by text**

In `tests/test_csv_import_dialog.py`, `setCurrentText("Corridor")` still works
for unique headers, so those tests pass unchanged. Add one duplicate-header test:

```python
def test_duplicate_header_names_are_selectable_by_column(tmp_path):
    _app()
    path = tmp_path / "dupes.csv"
    _write_csv(path, [["code", "name", "code"], ["A1", "Widget", "B2"]])
    dialog = CsvImportDialog([("sku", "SKU"), ("alt", "Alt")])
    dialog.load_csv(path)

    dialog.field_combos["sku"].setCurrentIndex(1)   # first "code"
    dialog.field_combos["alt"].setCurrentIndex(3)   # second "code"

    assert dialog.get_mapped_rows() == [{"sku": "A1", "alt": "B2"}]
    assert dialog.field_combos["sku"].itemText(1) == "code (col 1)"
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add app/core/csv_import.py app/ui/csv_import_dialog.py tests/test_csv_import.py tests/test_csv_import_dialog.py
git commit -m "fix: map CSV columns by index instead of by name

header.index(column) resolved every duplicate header name to the first match,
making later columns of the same name unreachable. Mapping by index deletes the
lookup entirely and is what Task 6 needs to store a replayable mapping."
```

---

### Task 6: Remember the mapping per CSV layout

Closes §3.5's remembered-mapping item.

**Not in this task:** §3.5's *other* bullet — auto-mapping an unseen header by
synonym (`sku|article|code`, `position|pos|location`) — stays parent-plan work.
Until it lands, an unrecognised layout leaves every dropdown on `-- none --`,
exactly as today. Recall only helps the second time you import a given format.

**Files:**
- Create: `app/core/csv_mapping_memory.py`
- Create: `tests/test_csv_mapping_memory.py`
- Modify: `app/ui/csv_import_dialog.py` (constructor, `load_csv`, `accept`),
  `app/ui/mode_positions_panel.py:210-217`, `app/ui/mode_inventory_panel.py:151-158`
- Test: `tests/test_csv_import_dialog.py`

**Interfaces:**
- Consumes: `load_settings`/`save_settings` from Task 4 (`csv_mappings` key
  guaranteed present); `_current_mapping() -> dict[str, int | None]` from Task 5.
- Produces:
  - `header_signature(header: list[str]) -> str`
  - `recall_mapping(settings: dict, mode: str, header: list[str]) -> dict[str, int] | None`
  - `remember_mapping(settings: dict, mode: str, header: list[str], mapping: dict[str, int | None]) -> None`
    (mutates `settings` in place)
  - `CsvImportDialog(fields, parent=None, *, settings=None, mode=None)` — both
    keyword arguments default to `None`, which disables recall entirely, so the
    existing dialog tests keep working unchanged.

- [ ] **Step 1: Write the failing tests for the core module**

Create `tests/test_csv_mapping_memory.py`:

```python
from app.core.csv_mapping_memory import (
    MAX_REMEMBERED_LAYOUTS,
    header_signature,
    recall_mapping,
    remember_mapping,
)


def test_signature_ignores_case_and_surrounding_whitespace():
    assert header_signature([" SKU ", "Name"]) == header_signature(["sku", "name"])


def test_signature_is_order_sensitive():
    # Column order matters: the stored mapping is a set of column indexes, so a
    # reordered export must count as a different layout.
    assert header_signature(["sku", "name"]) != header_signature(["name", "sku"])


def test_remember_then_recall_round_trips():
    settings = {"csv_mappings": {}}
    header = ["sku", "name"]

    remember_mapping(settings, "inventory", header, {"sku": 0, "name": 1})

    assert recall_mapping(settings, "inventory", header) == {"sku": 0, "name": 1}


def test_recall_returns_none_for_an_unseen_layout():
    settings = {"csv_mappings": {}}
    remember_mapping(settings, "inventory", ["sku"], {"sku": 0})

    assert recall_mapping(settings, "inventory", ["totally", "different"]) is None


def test_recall_is_scoped_per_mode():
    settings = {"csv_mappings": {}}
    remember_mapping(settings, "inventory", ["sku"], {"sku": 0})

    assert recall_mapping(settings, "positions", ["sku"]) is None


def test_unmapped_fields_are_not_stored():
    settings = {"csv_mappings": {}}

    remember_mapping(settings, "inventory", ["sku", "name"], {"sku": 0, "name": None})

    assert recall_mapping(settings, "inventory", ["sku", "name"]) == {"sku": 0}


def test_oldest_layout_is_evicted_past_the_cap():
    settings = {"csv_mappings": {}}
    for i in range(MAX_REMEMBERED_LAYOUTS + 1):
        remember_mapping(settings, "inventory", [f"col{i}"], {"sku": 0})

    stored = settings["csv_mappings"]["inventory"]
    assert len(stored) == MAX_REMEMBERED_LAYOUTS
    assert header_signature(["col0"]) not in stored
    assert header_signature([f"col{MAX_REMEMBERED_LAYOUTS}"]) in stored


def test_re_remembering_a_layout_does_not_grow_the_store():
    settings = {"csv_mappings": {}}
    remember_mapping(settings, "inventory", ["sku"], {"sku": 0})
    remember_mapping(settings, "inventory", ["sku"], {"sku": 1})

    assert settings["csv_mappings"]["inventory"] == {header_signature(["sku"]): {"sku": 1}}


def test_missing_csv_mappings_key_is_tolerated():
    assert recall_mapping({}, "inventory", ["sku"]) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_csv_mapping_memory.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'app.core.csv_mapping_memory'`.

- [ ] **Step 3: Write the core module**

Create `app/core/csv_mapping_memory.py`:

```python
from __future__ import annotations

# One CSV layout per header row. Twenty covers every export format an operator
# realistically feeds this app; the cap only exists so settings.json cannot grow
# without bound.
MAX_REMEMBERED_LAYOUTS = 20

_SEPARATOR = "\x1f"  # ASCII unit separator - cannot occur in a CSV header cell


def header_signature(header: list[str]) -> str:
    return _SEPARATOR.join(cell.strip().lower() for cell in header)


def recall_mapping(settings: dict, mode: str, header: list[str]) -> dict[str, int] | None:
    by_mode = settings.get("csv_mappings", {}).get(mode, {})
    return by_mode.get(header_signature(header))


def remember_mapping(
    settings: dict,
    mode: str,
    header: list[str],
    mapping: dict[str, int | None],
) -> None:
    by_mode = settings.setdefault("csv_mappings", {}).setdefault(mode, {})
    signature = header_signature(header)
    # Re-inserting moves the layout to the end, so eviction is least-recently-saved.
    by_mode.pop(signature, None)
    by_mode[signature] = {
        field: index for field, index in mapping.items() if index is not None
    }
    while len(by_mode) > MAX_REMEMBERED_LAYOUTS:
        by_mode.pop(next(iter(by_mode)))
```

- [ ] **Step 4: Run the core tests**

Run: `.venv/bin/python -m pytest tests/test_csv_mapping_memory.py -v`

Expected: all nine PASS.

- [ ] **Step 5: Write the failing dialog test**

Add to `tests/test_csv_import_dialog.py`:

```python
def test_reloading_the_same_layout_restores_the_previous_mapping(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr(
        "app.ui.csv_import_dialog.default_settings_path",
        lambda: tmp_path / "settings.json",
    )
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number", "Height"], ["H", "029", "A"]])
    settings = {"csv_mappings": {}}

    first = CsvImportDialog(FIELDS, settings=settings, mode="positions")
    first.load_csv(path)
    first.field_combos["corridor"].setCurrentIndex(1)
    first.field_combos["number"].setCurrentIndex(2)
    first.accept()

    second = CsvImportDialog(FIELDS, settings=settings, mode="positions")
    second.load_csv(path)

    assert second.field_combos["corridor"].currentData() == 0
    assert second.field_combos["number"].currentData() == 1
    assert second.field_combos["height"].currentData() is None


def test_dialog_without_settings_does_not_recall(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number", "Height"], ["H", "029", "A"]])

    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)

    assert dialog.field_combos["corridor"].currentData() is None
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_csv_import_dialog.py -k restores -v`

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'settings'`.

- [ ] **Step 7: Wire recall and remember into the dialog**

In `app/ui/csv_import_dialog.py`, add imports:

```python
from app.core.config import default_settings_path, save_settings
from app.core.csv_mapping_memory import recall_mapping, remember_mapping
```

Change the constructor signature and store the two new arguments:

```python
    def __init__(self, fields: list[tuple[str, str]], parent=None, *, settings=None, mode=None):
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._fields = fields
        self._settings = settings
        self._mode = mode
        self._header: list[str] = []
        self._rows: list[list[str]] = []
```

At the end of `load_csv`, after the combos are repopulated and before
`self._refresh_preview()`, apply any remembered mapping:

```python
        self._apply_remembered_mapping()
        self._refresh_preview()
```

```python
    def _apply_remembered_mapping(self) -> None:
        if self._settings is None or self._mode is None:
            return
        remembered = recall_mapping(self._settings, self._mode, self._header)
        if not remembered:
            return
        for field, index in remembered.items():
            combo = self.field_combos.get(field)
            if combo is None:
                continue
            combo_index = combo.findData(index)
            if combo_index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(combo_index)
                combo.blockSignals(False)
```

`findData` returning `-1` is the case where a remembered index no longer exists
in a shorter file with the same signature — leave that field on `-- none --`
rather than guessing.

Override `accept` to save:

```python
    def accept(self) -> None:
        if self._settings is not None and self._mode is not None and self._header:
            remember_mapping(self._settings, self._mode, self._header, self._current_mapping())
            try:
                save_settings(default_settings_path(), self._settings)
            except OSError:
                # A remembered mapping is a convenience; failing to persist it
                # must never block an import the operator already confirmed.
                pass
        super().accept()
```

- [ ] **Step 8: Pass settings and mode from both panels**

`app/ui/mode_positions_panel.py`:

```python
        dialog = CsvImportDialog(
            POSITION_CSV_FIELDS, parent=self, settings=self._settings, mode="positions"
        )
```

`app/ui/mode_inventory_panel.py`:

```python
        dialog = CsvImportDialog(
            INVENTORY_CSV_FIELDS, parent=self, settings=self._settings, mode="inventory"
        )
```

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add app/core/csv_mapping_memory.py app/ui/csv_import_dialog.py app/ui/mode_positions_panel.py app/ui/mode_inventory_panel.py tests/test_csv_mapping_memory.py tests/test_csv_import_dialog.py
git commit -m "feat: remember the column mapping per CSV layout

Keyed by the normalized header row, so importing the same export tomorrow
pre-fills all nine dropdowns with no clicks and nothing to save by hand.
Capped at 20 layouts per mode, least-recently-saved evicted."
```

---

### Task 7: Make the CSV import dialog readable

Closes §4.8.

**Files:**
- Modify: `app/ui/csv_import_dialog.py:44-58`
- Test: `tests/test_csv_import_dialog.py:97-104` (existing assertion changes)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `preview_table` uses `ResizeToContents`; the dialog exposes
  `self.splitter` holding the mapping form above the preview table.
  `app/core/config.py` gains `qsettings() -> QSettings`, which Task 10 reuses
  for the main window. It lives in `config.py` and not in `main_window.py`
  because `main_window` imports the panels which import this dialog — the
  helper cannot live downstream of its own callers.

- [ ] **Step 1: Update the existing test and add the new one**

`tests/test_csv_import_dialog.py:97-104` currently asserts `Stretch`, which this
task deliberately changes. Replace that test:

```python
def test_preview_columns_size_to_their_contents_not_the_window():
    # Stretch divided the width across nine fields and truncated every header,
    # so the operator could not tell which preview column was which.
    _app()
    dialog = CsvImportDialog(FIELDS)

    header = dialog.preview_table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert not header.stretchLastSection()


def test_mapping_form_and_preview_are_in_a_splitter():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert dialog.splitter.count() == 2
    assert dialog.splitter.orientation() == Qt.Orientation.Vertical
```

Add the imports the new tests need at the top of the file:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_csv_import_dialog.py -k "splitter or size_to_their_contents" -v`

Expected: `test_preview_columns_size_to_their_contents_not_the_window` FAILS
(mode is `Stretch`); `test_mapping_form_and_preview_are_in_a_splitter` FAILS with
`AttributeError: 'CsvImportDialog' object has no attribute 'splitter'`.

- [ ] **Step 3: Rebuild the layout**

Add `QSplitter`, `QWidget` and `Qt` to the imports in
`app/ui/csv_import_dialog.py`:

```python
from PySide6.QtCore import Qt
```

and add `QSplitter`, `QWidget` to the existing `PySide6.QtWidgets` import list.

Replace the layout block (currently lines 51-58):

```python
        form_panel = QWidget()
        form_panel.setLayout(form)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(form_panel)
        self.splitter.addWidget(self.preview_table)
        # The preview is what the operator checks before importing; give it the
        # space when the dialog is resized.
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(browse_button)
        layout.addWidget(self.splitter)
        layout.addWidget(buttons)

        header = self.preview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.resize(900, 600)
```

`ResizeToContents` sizes each column to the wider of its header text and its
cells, so `SKU (required)` is never clipped; the table scrolls horizontally when
nine columns exceed the width.

- [ ] **Step 4: Persist the dialog size and splitter position**

Add the shared helper to `app/core/config.py`:

```python
from PySide6.QtCore import QSettings


def qsettings() -> QSettings:
    # Window geometry is per-machine state. It must never go into
    # settings.json, which the operator may point at a shared folder.
    return QSettings("barcode_tool", "barcode_tool")
```

`app/core/print_service.py` already imports Qt, so this adds no new dependency
edge to `core`.

In `app/ui/csv_import_dialog.py`, import `qsettings` alongside the existing
config imports, then restore at the end of `__init__`:

```python
        self.resize(900, 600)
        stored = qsettings()
        geometry = stored.value("csv_import_dialog/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter_state = stored.value("csv_import_dialog/splitter")
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)
```

and save on close, whether the operator imports or cancels:

```python
    def done(self, result: int) -> None:
        stored = qsettings()
        stored.setValue("csv_import_dialog/geometry", self.saveGeometry())
        stored.setValue("csv_import_dialog/splitter", self.splitter.saveState())
        super().done(result)
```

`done` rather than `accept`/`reject` — Qt routes both through it, so the size is
kept even when the import is cancelled.

Add a test:

```python
def test_dialog_geometry_is_remembered(tmp_path, monkeypatch):
    _app()
    store = QSettings(str(tmp_path / "geo.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("app.ui.csv_import_dialog.qsettings", lambda: store)

    first = CsvImportDialog(FIELDS)
    first.resize(742, 531)
    first.done(0)

    second = CsvImportDialog(FIELDS)

    assert second.size().width() == 742
    assert second.size().height() == 531
```

**Do not raise those numbers.** `restoreGeometry` clamps to the screen, and the
offscreen platform reports an 800×800 screen — asserting a restored 1111 px width
yields 798 and the test fails for a reason that has nothing to do with the code.
Verified: 742×531 round-trips exactly.

Import `QSettings` from `PySide6.QtCore` in the test file.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green, including `test_dialog_has_a_bigger_default_size`.

- [ ] **Step 6: Look at it**

Run: `.venv/bin/python -m app.main`, open Inventory → Import CSV..., load any
CSV with the nine inventory fields. Confirm every column header is fully
readable and the splitter handle between the dropdowns and the preview drags.

- [ ] **Step 7: Commit**

```bash
git add app/core/config.py app/ui/csv_import_dialog.py tests/test_csv_import_dialog.py
git commit -m "fix: stop the import preview truncating every column header

Stretch across nine columns rendered 'SKU (required)' as 'KU (required'. Sizes
columns to their contents and puts the mapping form and preview in a splitter
so the preview gets real height."
```

---

### Task 8: Inventory table — sortable, filterable, counted

Closes §4.4. The `UserRole` change and `setSortingEnabled(True)` ship together:
sorting first would make `checked_items()` return the wrong items.

**Files:**
- Modify: `app/ui/mode_inventory_panel.py:70-71`, `:122-149`, `:84-90` (layout)
- Test: `tests/test_mode_inventory_panel.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `checked_items()` reads the `InventoryItem` off the row via
  `Qt.ItemDataRole.UserRole` instead of indexing `self.items[row]`. New widgets:
  `filter_edit` (`QLineEdit`), `selection_label` (`QLabel`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mode_inventory_panel.py`:

```python
def test_checked_items_survive_sorting():
    # checked_items() used to map table row -> self.items[row]; sorting the view
    # would have printed labels for whichever items happened to land on the
    # checked rows.
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "ZZZ", "position_code": "H011A"},
        {"sku": "AAA", "position_code": "H012A"},
    ])
    panel._set_all_checked(False)
    panel.items_table.item(0, 0).setCheckState(Qt.CheckState.Checked)  # ZZZ

    panel.items_table.sortItems(1, Qt.SortOrder.AscendingOrder)

    assert [item.sku for item in panel.checked_items()] == ["ZZZ"]


def test_filter_hides_non_matching_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "WIDGET1", "position_code": "H011A"},
        {"sku": "GADGET2", "position_code": "H012A"},
    ])

    panel.filter_edit.setText("widget")

    assert not panel.items_table.isRowHidden(0)
    assert panel.items_table.isRowHidden(1)


def test_hidden_rows_are_still_printed_if_checked():
    # Filtering is a view concern. Silently dropping checked-but-filtered items
    # would be the same class of bug as the sorting one.
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "WIDGET1", "position_code": "H011A"},
        {"sku": "GADGET2", "position_code": "H012A"},
    ])

    panel.filter_edit.setText("widget")

    assert len(panel.checked_items()) == 2


def test_selection_count_updates_live():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU2", "position_code": "H012A"},
    ])

    panel._set_all_checked(False)

    assert panel.selection_label.text() == "0 of 2 selected"
```

Add `from PySide6.QtCore import Qt` to the test file if it is not already
imported.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mode_inventory_panel.py -k "sorting or filter or selection_count or hidden" -v`

Expected: FAILs with `AttributeError` on `filter_edit` and `selection_label`;
`test_checked_items_survive_sorting` FAILS returning `["AAA"]`.

- [ ] **Step 3: Store the item on the row and enable sorting**

In `_populate_table`, attach the item to the checkbox cell:

```python
    def _populate_table(self, items: list[InventoryItem]) -> None:
        self.items_table.setSortingEnabled(False)
        # itemChanged fires once per setItem and the handler counts every row.
        # With 2000 SKUs that is 14 000 signals x a 2000-row scan; block them
        # and update the count once at the end.
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            # The row carries its own item: the table can be re-sorted, so the
            # row index is not a stable key into self.items.
            check_item.setData(Qt.ItemDataRole.UserRole, item)
            self.items_table.setItem(row_index, 0, check_item)

            values = [item.sku, item.name, item.client, item.position_code, item.batch, item.expiry]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row_index, column, cell)
        self.items_table.blockSignals(False)
        self.items_table.setSortingEnabled(True)
        self._update_selection_label()
```

Sorting is switched off while filling the table — with it on, Qt re-sorts after
every `setItem` and the row you are still populating moves out from under you.

Replace `checked_items`:

```python
    def checked_items(self) -> list[InventoryItem]:
        checked = []
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None and check_item.checkState() == Qt.CheckState.Checked:
                checked.append(check_item.data(Qt.ItemDataRole.UserRole))
        return checked
```

- [ ] **Step 4: Add the filter box and the live count**

In `__init__`, after `self.items_table` is created:

```python
        self.items_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.items_table.itemChanged.connect(lambda _item: self._update_selection_label())

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by SKU, name or position")
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.selection_label = QLabel("0 of 0 selected")
```

Add the two methods:

```python
    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            item = check_item.data(Qt.ItemDataRole.UserRole) if check_item else None
            haystack = (
                f"{item.sku} {item.name} {item.position_code}".lower() if item else ""
            )
            self.items_table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _update_selection_label(self) -> None:
        total = self.items_table.rowCount()
        self.selection_label.setText(f"{len(self.checked_items())} of {total} selected")
```

Filtering hides rows; it never unchecks them. `checked_items()` ignores hidden
state, so a checked row that is currently filtered out still prints — the
alternative silently drops labels the operator asked for.

Add `QHeaderView` and `QLineEdit` to the `PySide6.QtWidgets` imports, and place
the two new widgets in the layout:

```python
        layout.addLayout(select_buttons)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.selection_label)
        layout.addWidget(self.items_table)
```

`_set_all_checked` must refresh the count — add `self._update_selection_label()`
as its last line.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/ui/mode_inventory_panel.py tests/test_mode_inventory_panel.py
git commit -m "feat: sortable, filterable inventory table with a live selection count

checked_items() mapped table row -> self.items[row], so enabling sorting would
have printed the wrong items. The row now carries its own InventoryItem in
UserRole, which is what makes sorting safe to turn on."
```

---

### Task 9: Label the Settings fields

Closes §4.1.

**Files:**
- Modify: `app/ui/settings_window.py:78-85` (layout), `:104-130` (validation)
- Test: `tests/test_settings_window.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SettingsWindow.validation_error() -> str | None` — returns the
  reason the current form cannot be saved, or `None` when it is valid.
  `_save_and_close` refuses to save when it returns a string.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_settings_window.py`:

```python
def test_raw_zpl_mode_requires_a_target():
    # An empty target reached Path("").write_bytes and surfaced as a cryptic
    # OS error at print time instead of here.
    _app()
    window = SettingsWindow({}, None)
    window.print_mode_combo.setCurrentIndex(window.print_mode_combo.findData("raw_zpl"))
    window.raw_zpl_target_edit.setText("")

    assert "target" in window.validation_error().lower()


def test_driver_mode_does_not_require_a_zpl_target():
    _app()
    window = SettingsWindow({}, None)
    window.print_mode_combo.setCurrentIndex(window.print_mode_combo.findData("driver"))

    assert window.validation_error() is None


def test_duplicate_warehouse_prefixes_are_rejected():
    _app()
    window = SettingsWindow(
        {
            "warehouses": [
                {"name": "Main", "prefix": "C001"},
                {"name": "Spare", "prefix": "C001"},
            ]
        },
        None,
    )

    assert "prefix" in window.validation_error().lower()


def test_warehouse_with_an_empty_name_is_rejected():
    _app()
    window = SettingsWindow({"warehouses": [{"name": "", "prefix": "C001"}]}, None)

    assert "name" in window.validation_error().lower()


def test_every_field_has_a_visible_label():
    _app()
    window = SettingsWindow({}, None)

    labels = {label.text() for label in window.findChildren(QLabel)}
    assert "Shared folder" in labels
    assert "Printer" in labels
    assert "Print mode" in labels
    assert "Raw ZPL target" in labels
```

Import `QLabel` from `PySide6.QtWidgets` in the test file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_settings_window.py -k "validation or requires or duplicate or visible_label" -v`

Expected: `AttributeError: 'SettingsWindow' object has no attribute 'validation_error'`,
and `test_every_field_has_a_visible_label` FAILS because no `QLabel` exists.

- [ ] **Step 3: Group the widgets into labelled form layouts**

Add `QFormLayout`, `QGroupBox`, `QLabel` to the `PySide6.QtWidgets` imports.
Replace the layout block at the end of `__init__`:

```python
        folder_widget = QWidget()
        folder_widget.setLayout(folder_row)

        storage_form = QFormLayout()
        storage_form.addRow("Shared folder", folder_widget)
        storage_box = QGroupBox("Storage")
        storage_box.setLayout(storage_form)

        printing_form = QFormLayout()
        printing_form.addRow("Printer", self.printer_combo)
        printing_form.addRow("Print mode", self.print_mode_combo)
        printing_form.addRow("Raw ZPL target", self.raw_zpl_target_edit)
        zpl_help = QLabel(
            "Only used in Raw ZPL mode. The printer's raw queue name or device path."
        )
        zpl_help.setWordWrap(True)
        printing_form.addRow("", zpl_help)
        printing_box = QGroupBox("Printing")
        printing_box.setLayout(printing_form)

        warehouse_layout = QVBoxLayout()
        warehouse_layout.addWidget(self.warehouse_table)
        warehouse_layout.addLayout(warehouse_buttons)
        warehouse_box = QGroupBox("Warehouses")
        warehouse_box.setLayout(warehouse_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(storage_box)
        layout.addWidget(printing_box)
        layout.addWidget(warehouse_box)
        layout.addWidget(buttons)
```

Add `QWidget` to the imports — `QFormLayout.addRow` takes a widget, and
`folder_row` is a layout.

- [ ] **Step 4: Add validation**

```python
    def validation_error(self) -> str | None:
        current = self.get_current_settings()
        if current["print_mode"] == "raw_zpl" and not current["raw_zpl_target"].strip():
            return "Raw ZPL mode needs a target: a raw print queue name or a device path."
        prefixes = []
        for warehouse in current["warehouses"]:
            if not warehouse["name"].strip():
                return "Every warehouse needs a name."
            if not warehouse["prefix"].strip():
                return "Every warehouse needs a prefix."
            prefixes.append(warehouse["prefix"].strip())
        duplicates = {p for p in prefixes if prefixes.count(p) > 1}
        if duplicates:
            return f"Duplicate warehouse prefix: {', '.join(sorted(duplicates))}."
        return None

    def _save_and_close(self) -> None:
        error = self.validation_error()
        if error is not None:
            QMessageBox.warning(self, "Cannot save", error)
            return
        if self._settings_path is None:
            QMessageBox.warning(self, "Cannot save", "No settings file location configured.")
            return
        full_settings = load_settings(self._settings_path)
        full_settings.update(self.get_current_settings())
        save_settings(self._settings_path, full_settings)
        self.accept()
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/ui/settings_window.py tests/test_settings_window.py
git commit -m "feat: label and validate the Settings fields

The window stacked two combos and two text boxes into a QVBoxLayout with no
labels at all, so the operator had to guess which was the printer. Adds form
labels, group boxes, and save-time validation for the ZPL target and warehouse
prefixes."
```

---

### Task 10: Remember window geometry, add shortcuts

Closes §4.5's geometry and shortcut items. The status bar, live label count,
and template-per-mode memory stay with Phase 4 of the parent plan — they depend
on the preview dialog (§4.2) that this plan does not touch.

**Files:**
- Modify: `app/ui/main_window.py`, `app/ui/csv_import_dialog.py`
- Test: `tests/test_main_window.py`

**Interfaces:**
- Consumes: `qsettings()` from `app/core/config.py`, added in Task 7.
- Produces: `MainWindow.closeEvent` persists geometry via `QSettings`;
  `Ctrl+P`, `Ctrl+O`, `Ctrl+,` actions exist on the main window.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main_window.py`:

```python
def test_geometry_is_restored_from_qsettings(tmp_path, monkeypatch):
    # Back QSettings with a temp ini rather than the real user config, and
    # patch the accessor so the test cannot depend on QSettings' own caching.
    _app()
    store = QSettings(str(tmp_path / "geo.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("app.ui.main_window.qsettings", lambda: store)

    first = MainWindow()
    first.resize(742, 531)
    first.close()

    second = MainWindow()

    # 742x531 fits the offscreen platform's 800x800 screen. restoreGeometry
    # clamps to the screen, so a larger assertion would fail on the clamp
    # rather than on the code. Verified to round-trip exactly.
    assert second.size().width() == 742
    assert second.size().height() == 531


def test_shortcuts_are_registered():
    _app()
    window = MainWindow()

    shortcuts = {a.shortcut().toString() for a in window.actions()}
    assert {"Ctrl+P", "Ctrl+O", "Ctrl+,"} <= shortcuts
```

Import `QSettings` from `PySide6.QtCore` in the test file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_main_window.py -k "geometry or shortcuts" -v`

Expected: `test_shortcuts_are_registered` FAILS — `window.actions()` is empty
(the Settings action is on the menu bar, not the window).
`test_geometry_is_restored_from_qsettings` FAILS with 900×600.

- [ ] **Step 3: Persist geometry and add the actions**

In `app/ui/main_window.py`, reuse the helper Task 7 added to `config.py`:

```python
from PySide6.QtGui import QAction, QKeySequence

from app.core.config import default_settings_path, load_settings, qsettings
```

In `__init__`, after `self.setCentralWidget(self.tabs)`:

```python
        geometry = qsettings().value("main_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        settings_action = QAction("Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._open_settings)

        print_action = QAction("Print", self)
        print_action.setShortcut(QKeySequence.StandardKey.Print)
        print_action.triggered.connect(self._print_current_tab)

        import_action = QAction("Import CSV...", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.triggered.connect(self._import_current_tab)

        self.addActions([settings_action, print_action, import_action])
        self.menuBar().addAction(settings_action)
```

The existing `self.resize(900, 600)` stays as the first-run default; the restore
overwrites it only when a saved geometry exists.

```python
    def _current_panel(self):
        return self.tabs.currentWidget()

    def _print_current_tab(self) -> None:
        self._current_panel()._on_print_clicked()

    def _import_current_tab(self) -> None:
        self._current_panel()._on_import_csv_clicked()

    def closeEvent(self, event) -> None:
        qsettings().setValue("main_window/geometry", self.saveGeometry())
        super().closeEvent(event)
```

Both panels already define `_on_print_clicked` and `_on_import_csv_clicked` with
the same names and no arguments, so the tab dispatch needs no per-mode branching.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add app/ui/main_window.py tests/test_main_window.py
git commit -m "feat: remember window geometry, add Ctrl+P/Ctrl+O/Ctrl+, shortcuts

Geometry goes to QSettings rather than settings.json - it is per-machine state
and must not travel through the shared folder."
```

---

## Verification before calling this done

- [ ] `.venv/bin/python -m pytest -q` — all green, count is 190 + the new tests.
- [ ] `.venv/bin/python -m ruff check app tests` — clean (the repo has a
      `.ruff_cache`, so ruff is the established linter).
- [ ] Launch `.venv/bin/python -m app.main` and confirm by hand:
  - Positions: typing `h` in Corridor shows `H`; there is no "Use height"
    checkbox; typing `a` in Height from produces height-suffixed codes.
  - Inventory: Import CSV shows fully readable column headers; importing the
    same file twice pre-fills the dropdowns the second time.
  - Inventory: the filter box hides rows, the count updates, clicking a column
    header sorts, and Print still prints the rows that are actually checked.
  - Settings: every field is labelled; saving in Raw ZPL mode with an empty
    target is refused with a readable reason.
  - Resize the window, quit, relaunch — the size is remembered.

## Out of scope for this plan

Everything else in the parent stabilization plan, in particular:

- §0.1, §0.2, §0.5, §0.6 — the other Phase 0 defects.
- The rest of §1.1 (atomic write, corrupt-file recovery) and all of §1.2–§1.5.
- Phase 2's `print_batch` pipeline, §4.2's preview dialog, §4.3's progress
  dialog, and Phase 5's logging.
- §3.1 delimiter sniffing and §3.2 encoding detection — independent of the
  mapping work here, and both still needed.
- The light/dark theme toggle.
