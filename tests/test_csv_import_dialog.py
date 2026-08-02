import csv

from PySide6.QtWidgets import QApplication, QHeaderView

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


def test_dialog_has_a_bigger_default_size():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert dialog.size().width() >= 900
    assert dialog.size().height() >= 600


def test_preview_table_columns_stretch_to_fill_width():
    _app()
    dialog = CsvImportDialog(FIELDS)

    assert (
        dialog.preview_table.horizontalHeader().sectionResizeMode(0)
        == QHeaderView.ResizeMode.Stretch
    )


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
