import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.label_renderer import mm_to_px
from app.ui.mode_positions_panel import PositionsModePanel

SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
    "label_sizes": [{"name": "68x38mm", "width_mm": 68, "height_mm": 38}],
}


def _app():
    return QApplication.instance() or QApplication([])


def test_orientation_defaults_to_landscape():
    _app()
    panel = PositionsModePanel(SETTINGS)
    assert panel.orientation_combo.currentText() == "Landscape"


def test_portrait_orientation_swaps_generated_label_dimensions():
    _app()
    panel = PositionsModePanel(SETTINGS)  # 68x38mm size
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.orientation_combo.setCurrentText("Portrait")

    results = panel.generate()

    _, image = results[0]
    assert image.size == (mm_to_px(38), mm_to_px(68))


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


def test_generate_without_label_size_raises_value_error():
    _app()
    panel = PositionsModePanel({"warehouses": SETTINGS["warehouses"], "label_sizes": []})
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


def test_print_current_labels_falls_back_to_settings_dir_when_shared_folder_empty(
    monkeypatch, tmp_path
):
    _app()
    monkeypatch.setattr(
        "app.ui.mode_positions_panel.default_settings_path",
        lambda: tmp_path / "settings.json",
    )
    settings = {**SETTINGS, "default_printer": "", "shared_folder": ""}
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.generate()

    panel.print_current_labels(output_pdf_path=tmp_path / "out.pdf")

    assert (tmp_path / "audit_log.csv").exists()


def test_print_uses_label_size_from_generate_time_not_live_combo(monkeypatch, tmp_path):
    _app()
    settings = {
        "warehouses": SETTINGS["warehouses"],
        "label_sizes": [
            {"name": "68x38mm", "width_mm": 68, "height_mm": 38},
            {"name": "80x80mm", "width_mm": 80, "height_mm": 80},
        ],
        "default_printer": "",
        "shared_folder": str(tmp_path),
    }
    panel = PositionsModePanel(settings)
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")
    panel.number_to_edit.setText("030")
    panel.label_size_combo.setCurrentIndex(0)  # 68x38mm
    panel.generate()

    panel.label_size_combo.setCurrentIndex(1)  # user changes size after Generate

    calls = []
    monkeypatch.setattr(
        "app.ui.mode_positions_panel.print_labels",
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


def test_refresh_from_settings_rebuilds_combos():
    _app()
    panel = PositionsModePanel(SETTINGS)

    panel.refresh_from_settings(
        {
            "warehouses": [{"name": "Second", "prefix": "C002"}],
            "label_sizes": [{"name": "80x80mm", "width_mm": 80, "height_mm": 80}],
        }
    )

    warehouse_names = [
        panel.warehouse_combo.itemText(i) for i in range(panel.warehouse_combo.count())
    ]
    label_size_names = [
        panel.label_size_combo.itemText(i) for i in range(panel.label_size_combo.count())
    ]
    assert warehouse_names == ["Second"]
    assert label_size_names == ["80x80mm"]
