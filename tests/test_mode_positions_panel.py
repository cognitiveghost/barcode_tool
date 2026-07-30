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
