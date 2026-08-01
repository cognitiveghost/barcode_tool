from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import QApplication, QMessageBox

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


def test_save_with_no_settings_path_warns_and_does_not_close(monkeypatch):
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=None)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    accepted = []
    monkeypatch.setattr(window, "accept", lambda: accepted.append(True))

    window._save_and_close()

    assert len(warnings) == 1
    assert accepted == []


def test_offline_default_printer_is_preserved_not_overwritten(monkeypatch):
    _app()
    monkeypatch.setattr(QPrinterInfo, "availablePrinters", staticmethod(list))
    settings = {**DEFAULT_SETTINGS, "default_printer": "Citizen CL-E300"}

    window = SettingsWindow(settings, settings_path=None)

    assert window.printer_combo.currentText() == "Citizen CL-E300"
    assert window.get_current_settings()["default_printer"] == "Citizen CL-E300"


def test_settings_window_prefills_print_mode_and_raw_zpl_target():
    _app()
    settings = {**DEFAULT_SETTINGS, "print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}
    window = SettingsWindow(settings, settings_path=None)
    assert window.print_mode_combo.currentData() == "raw_zpl"
    assert window.raw_zpl_target_edit.text() == "/dev/usb/lp0"


def test_settings_window_defaults_print_mode_to_driver():
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=None)
    assert window.print_mode_combo.currentData() == "driver"


def test_save_writes_print_mode_and_raw_zpl_target_to_disk(tmp_path):
    _app()
    settings_path = tmp_path / "settings.json"
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=settings_path)
    window.print_mode_combo.setCurrentIndex(window.print_mode_combo.findData("raw_zpl"))
    window.raw_zpl_target_edit.setText("/dev/usb/lp0")
    window._save_and_close()

    saved = load_settings(settings_path)
    assert saved["print_mode"] == "raw_zpl"
    assert saved["raw_zpl_target"] == "/dev/usb/lp0"
