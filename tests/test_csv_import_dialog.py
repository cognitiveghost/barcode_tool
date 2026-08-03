import csv

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QHeaderView, QMessageBox

from app.ui.csv_import_dialog import CsvImportDialog

FIELDS = [("corridor", "Corridor"), ("number", "Number"), ("height", "Height")]


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # accept() calls default_settings_path() (imported directly into
    # app.ui.csv_import_dialog, so patching app.core.config's copy alone
    # would not reach it - see the same double-patch in test_main_window.py)
    # to persist a confirmed mapping. Redirect it so a test that exercises
    # the real accept() never writes into the developer's actual
    # ~/.barcode_tool directory.
    monkeypatch.setattr(
        "app.ui.csv_import_dialog.default_settings_path",
        lambda: tmp_path / "settings.json",
    )
    # done() (which QDialog.accept()/reject() both call internally, so this
    # fires even for tests that only call accept()) persists geometry via
    # qsettings() the same way. An unpatched call would write into the
    # developer's real ~/.config/barcode_tool store and, worse, leave
    # geometry there for the *next* test run to restore from - redirect it
    # to a throwaway ini file per test for the same reason as above.
    store = QSettings(str(tmp_path / "geometry.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("app.ui.csv_import_dialog.qsettings", lambda: store)


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


def test_dialog_has_a_bigger_default_size():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert dialog.size().width() >= 900
    assert dialog.size().height() >= 600


def test_preview_columns_size_to_their_contents_not_the_window():
    # Stretch divided the width across nine fields and truncated every
    # header, so the operator could not tell which preview column was which.
    _app()
    dialog = CsvImportDialog(FIELDS)

    header = dialog.preview_table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert not header.stretchLastSection()


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


def test_dialog_preselects_the_detected_delimiter(tmp_path):
    _app()
    path = tmp_path / "semicolon.csv"
    path.write_bytes(b"sku;name\r\nSKU1;Widget\r\n")
    dialog = CsvImportDialog(FIELDS)

    dialog.load_csv(path)

    assert dialog.delimiter_combo.currentData() == ";"


def test_changing_delimiter_override_reparses_the_file(tmp_path):
    _app()
    path = tmp_path / "comma.csv"
    path.write_bytes(b"sku,name\r\nSKU1,Widget\r\n")
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)

    index = dialog.delimiter_combo.findData(";")
    dialog.delimiter_combo.setCurrentIndex(index)

    assert dialog._header == ["sku,name"]  # whole line becomes one column


def test_dialog_preselects_the_detected_encoding(tmp_path):
    _app()
    path = tmp_path / "cyrillic.csv"
    path.write_bytes("sku,client\r\nSKU1,Клиент\r\n".encode("cp1251"))
    dialog = CsvImportDialog(FIELDS)

    dialog.load_csv(path)

    assert dialog.encoding_combo.currentData() == "cp1251"


def test_load_csv_with_undecodable_file_shows_warning_instead_of_crashing(tmp_path, monkeypatch):
    _app()
    # Same corrupt-UTF-16-BOM fixture used in tests/test_csv_import.py: a
    # UTF-16LE BOM followed by an unpaired surrogate, which read_csv raises
    # ValueError on. Uncaught, that ValueError used to propagate out of this
    # Qt-slot-reachable method with no feedback to the operator.
    path = tmp_path / "garbage.csv"
    path.write_bytes(b"\xff\xfe\x00\xd8A\x00")
    dialog = CsvImportDialog(FIELDS)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    dialog.load_csv(path)  # must not raise

    assert len(warnings) == 1
    assert dialog._header == []
    assert dialog._rows == []


def test_failed_override_leaves_previous_parse_intact(tmp_path, monkeypatch):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number"], ["H", "029"]])
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)
    previous_header, previous_rows = dialog._header, dialog._rows

    def _boom(*args, **kwargs):
        raise ValueError("boom")

    # The initial load above already succeeded with the real read_csv; only
    # the subsequent override attempt (triggered below) needs to fail.
    monkeypatch.setattr("app.ui.csv_import_dialog.read_csv", _boom)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    index = dialog.delimiter_combo.findData(";")
    dialog.delimiter_combo.setCurrentIndex(index)  # triggers _on_override_changed

    assert len(warnings) == 1
    assert dialog._header == previous_header
    assert dialog._rows == previous_rows


def test_duplicate_header_names_are_selectable_by_column(tmp_path):
    _app()
    path = tmp_path / "dupes.csv"
    _write_csv(path, [["code", "name", "code"], ["A1", "Widget", "B2"]])
    dialog = CsvImportDialog([("sku", "SKU"), ("alt", "Alt")])

    dialog.load_csv(path)
    dialog.field_combos["sku"].setCurrentIndex(1)   # first "code" (CSV column 0)
    dialog.field_combos["alt"].setCurrentIndex(3)   # second "code" (CSV column 2)

    assert dialog.get_mapped_rows() == [{"sku": "A1", "alt": "B2"}]
    assert dialog.field_combos["sku"].itemText(1) == "code (col 1)"
    assert dialog.field_combos["sku"].itemText(3) == "code (col 3)"


def test_recalled_mapping_is_preselected_on_matching_header(tmp_path):
    _app()
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


def test_dialog_without_settings_still_auto_maps_by_name(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number", "Height"], ["H", "029", "A"]])

    dialog = CsvImportDialog(FIELDS)  # no settings/mode - recall disabled
    dialog.load_csv(path)

    assert dialog.field_combos["corridor"].currentData() == 0
    assert dialog.field_combos["number"].currentData() == 1
    assert dialog.field_combos["height"].currentData() == 2


def test_ok_button_disabled_until_validator_is_satisfied(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Junk"], ["nothing useful"]])
    dialog = CsvImportDialog(
        FIELDS,
        validate_mapping=lambda mapping: None if mapping.get("corridor") is not None else "Map Corridor",
    )

    dialog.load_csv(path)

    assert not dialog._ok_button.isEnabled()
    assert dialog._reason_label.text() == "Map Corridor"

    dialog.field_combos["corridor"].setCurrentIndex(1)

    assert dialog._ok_button.isEnabled()
    assert dialog._reason_label.text() == ""


def test_ok_button_stays_enabled_without_a_validator(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Junk"], ["nothing useful"]])
    dialog = CsvImportDialog(FIELDS)  # no validate_mapping - always enabled

    dialog.load_csv(path)

    assert dialog._ok_button.isEnabled()


def test_preview_marks_a_row_that_would_be_skipped(tmp_path):
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor", "Number"], ["H", "029"], ["H", "not-a-number"]])
    dialog = CsvImportDialog(
        FIELDS,
        row_would_be_skipped=lambda row: not row.get("number", "").isdigit(),
    )
    dialog.load_csv(path)
    dialog.field_combos["corridor"].setCurrentIndex(1)
    dialog.field_combos["number"].setCurrentIndex(2)

    good_item = dialog.preview_table.item(0, 0)
    bad_item = dialog.preview_table.item(1, 0)

    assert good_item.background().color().name() != bad_item.background().color().name()


def test_accepting_without_settings_does_not_raise(tmp_path):
    # Regression guard: accept() must be a no-op wrt persistence when
    # settings/mode are None, not raise on missing state.
    _app()
    path = tmp_path / "positions.csv"
    _write_csv(path, [["Corridor"], ["H"]])
    dialog = CsvImportDialog(FIELDS)
    dialog.load_csv(path)

    dialog.accept()  # must not raise


def test_ok_button_disabled_from_construction_when_validator_would_fail():
    _app()
    dialog = CsvImportDialog(
        FIELDS,
        validate_mapping=lambda mapping: None if mapping.get("corridor") is not None else "Map Corridor",
    )

    assert not dialog._ok_button.isEnabled()
    assert dialog._reason_label.text() == "Map Corridor"


def test_mapping_form_and_preview_are_in_a_splitter():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert dialog.splitter.count() == 2
    assert dialog.splitter.orientation() == Qt.Orientation.Vertical


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
