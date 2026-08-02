import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

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
    audit_files = list((tmp_path / "audit").glob("*.csv"))
    assert len(audit_files) == 1
    log_lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
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

    assert len(list((tmp_path / "audit").glob("*.csv"))) == 1


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
    _write_preset(tmp_path, "positions", "a", "80x80mm", 80, 80)
    panel = PositionsModePanel(SETTINGS)

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
    assert preset_names == ["80x80mm", "Default 150x100mm"]


def test_refresh_with_no_presets_does_not_crash_without_a_main_window(monkeypatch):
    _app()
    monkeypatch.setattr("app.ui.mode_positions_panel.list_presets", lambda *a, **k: [])

    panel = PositionsModePanel(SETTINGS)  # constructed standalone, no QMainWindow

    assert panel.preset_combo.count() == 0


def test_refresh_shows_status_bar_warning_when_no_presets_found(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr("app.ui.mode_positions_panel.list_presets", lambda *a, **k: [])
    window = QMainWindow()
    panel = PositionsModePanel(SETTINGS)
    window.setCentralWidget(panel)

    panel.refresh_from_settings({**SETTINGS, "shared_folder": str(tmp_path)})

    assert window.statusBar().currentMessage() != ""


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
    audit_files = list((tmp_path / "audit").glob("*.csv"))
    assert len(audit_files) == 1
    log_lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
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


def test_generate_without_warehouse_raises():
    _app()
    panel = PositionsModePanel({**SETTINGS, "warehouses": []})
    panel.corridor_edit.setText("H")
    panel.number_from_edit.setText("029")

    with pytest.raises(ValueError, match="warehouse"):
        panel.generate()


def test_generate_from_rows_without_warehouse_raises():
    _app()
    panel = PositionsModePanel({**SETTINGS, "warehouses": []})

    with pytest.raises(ValueError, match="warehouse"):
        panel.generate_from_rows([{"corridor": "H", "number": "029"}])
