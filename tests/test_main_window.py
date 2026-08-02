import pytest
from PySide6.QtWidgets import QApplication

import app.ui.main_window as main_window_module
from app.core.config import save_settings
from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # MainWindow (and the panels it constructs) fall back to the real
    # default_settings_path() whenever shared_folder is unset; redirect all
    # three references into tmp_path so tests never touch (or seed template
    # presets into) the developer's actual ~/.barcode_tool directory.
    for module in (
        "app.ui.main_window",
        "app.ui.mode_positions_panel",
        "app.ui.mode_inventory_panel",
    ):
        monkeypatch.setattr(f"{module}.default_settings_path", lambda: tmp_path / "settings.json")


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"


def test_main_window_hosts_positions_and_inventory_tabs():
    _app()
    window = MainWindow()
    assert window.centralWidget() is window.tabs
    assert window.tabs.widget(0) is window.positions_panel
    assert window.tabs.widget(1) is window.inventory_panel
    assert window.tabs.tabText(0) == "Positions"
    assert window.tabs.tabText(1) == "Inventory"


def test_open_settings_refreshes_positions_panel_combos(monkeypatch, tmp_path):
    _app()
    window = MainWindow()
    window._settings_path = tmp_path / "settings.json"
    save_settings(
        window._settings_path,
        {"warehouses": [{"name": "New", "prefix": "C999"}]},
    )

    class FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window_module, "SettingsWindow", FakeSettingsDialog)

    window._open_settings()

    warehouse_names = [
        window.positions_panel.warehouse_combo.itemText(i)
        for i in range(window.positions_panel.warehouse_combo.count())
    ]
    assert warehouse_names == ["New"]


def test_open_settings_refreshes_inventory_panel_combos(monkeypatch, tmp_path):
    _app()
    window = MainWindow()
    window._settings_path = tmp_path / "settings.json"
    save_settings(
        window._settings_path,
        {"warehouses": [{"name": "New", "prefix": "C999"}]},
    )

    class FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 1

    monkeypatch.setattr(main_window_module, "SettingsWindow", FakeSettingsDialog)

    window._open_settings()

    warehouse_names = [
        window.inventory_panel.warehouse_combo.itemText(i)
        for i in range(window.inventory_panel.warehouse_combo.count())
    ]
    assert warehouse_names == ["New"]
