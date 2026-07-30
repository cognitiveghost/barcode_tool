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
