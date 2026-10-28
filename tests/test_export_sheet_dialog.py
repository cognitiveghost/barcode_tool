from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.core.review_sheet import pickable_columns
from app.core.template_renderer import TemplatePreset
from app.ui.export_sheet_dialog import ExportSheetDialog


def _app():
    return QApplication.instance() or QApplication([])


def _preset(name):
    return TemplatePreset(
        name=name,
        mode="inventory-table",
        width_mm=210,
        height_mm=297,
        template_path=Path("t"),
        stylesheet_path=Path("s"),
    )


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("app.ui.export_sheet_dialog.qsettings", lambda: settings)
    return settings


def test_defaults_position_view_all_columns(store):
    _app()
    dialog = ExportSheetDialog([_preset("A4 review sheet")])
    assert dialog.options()[1] == "position"
    assert dialog.options()[2] == pickable_columns("position")
    assert dialog.column_boxes["position"].isHidden()


def test_switching_view_hides_that_views_key(store):
    _app()
    dialog = ExportSheetDialog([_preset("A4 review sheet")])
    dialog.view_buttons["sku"].click()
    assert dialog.column_boxes["sku"].isHidden()
    assert not dialog.column_boxes["position"].isHidden()
    assert dialog.options()[2] == pickable_columns("sku")


def test_columns_are_remembered_per_view(store):
    _app()
    presets = [_preset("A4 review sheet")]
    dialog = ExportSheetDialog(presets)
    dialog.column_boxes["qty"].setChecked(False)
    dialog.view_buttons["sku"].click()
    dialog.column_boxes["name"].setChecked(False)
    dialog.accept()

    reopened = ExportSheetDialog(presets)
    assert reopened.options()[1] == "sku"
    assert "name" not in reopened.options()[2]
    reopened.view_buttons["position"].click()
    assert "qty" not in reopened.options()[2]


def test_nothing_written_on_cancel(store):
    _app()
    dialog = ExportSheetDialog([_preset("A4 review sheet")])
    dialog.view_buttons["sku"].click()
    dialog.column_boxes["qty"].setChecked(False)
    dialog.reject()
    assert store.allKeys() == []


def test_ok_disabled_when_no_column_checked(store):
    _app()
    dialog = ExportSheetDialog([_preset("A4 review sheet")])
    for key in pickable_columns("position"):
        dialog.column_boxes[key].setChecked(False)
    assert not dialog.ok_button.isEnabled()
    dialog.column_boxes["qty"].setChecked(True)
    assert dialog.ok_button.isEnabled()


def test_template_falls_back_to_shipped_when_remembered_is_gone(store):
    _app()
    presets = [_preset("Custom"), _preset("A4 review sheet")]
    store.setValue("inventory-table/last_template", "Deleted")
    assert ExportSheetDialog(presets).template_combo.currentText() == "A4 review sheet"

    store.setValue("inventory-table/last_template", "Custom")
    assert ExportSheetDialog(presets).template_combo.currentText() == "Custom"


def test_garbage_settings_fall_back_to_defaults(store):
    _app()
    presets = [_preset("A4 review sheet")]
    store.setValue("inventory-table/view", "bogus")
    store.setValue("inventory-table/columns/position", "bogus,,qty")
    dialog = ExportSheetDialog(presets)
    assert dialog.options()[1] == "position"
    assert dialog.options()[2] == ["qty"]

    store.setValue("inventory-table/columns/position", "")
    assert ExportSheetDialog(presets).options()[2] == pickable_columns("position")
