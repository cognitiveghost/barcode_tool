import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton

import app.ui.main_window as main_window_module
from app.core.config import DEFAULT_SETTINGS, save_settings
from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # MainWindow (and the panels it constructs) fall back to the real
    # default_settings_path() whenever shared_folder is unset; redirect both
    # references into tmp_path so tests never touch (or seed template
    # presets into) the developer's actual ~/.barcode_tool directory.
    monkeypatch.setattr(
        "app.ui.main_window.default_settings_path",
        lambda: tmp_path / "settings.json",
    )
    monkeypatch.setattr(
        "app.core.config.default_settings_path",
        lambda: tmp_path / "settings.json",
    )
    # MainWindow's own geometry restore, and the geometry/template-memory
    # restore each embedded panel does in refresh_from_settings, all go
    # through qsettings() (QSettings("barcode_tool", "barcode_tool") on the
    # real machine). Unpatched, a MainWindow constructed here would read
    # (and, on close, write) the developer's real ~/.config/barcode_tool
    # store - and once that store exists, every later-constructed window in
    # the same test process silently restores geometry from it, breaking
    # unrelated size assertions in full-suite runs (see Task 18's report and
    # test_csv_import_dialog.py's identical fixture). Redirect every module
    # that owns its own qsettings() import to one throwaway ini per test.
    store = QSettings(str(tmp_path / "geo.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("app.ui.main_window.qsettings", lambda: store)
    monkeypatch.setattr("app.ui.mode_positions_panel.qsettings", lambda: store)
    monkeypatch.setattr("app.ui.mode_inventory_panel.qsettings", lambda: store)


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"


def test_main_window_hosts_positions_and_inventory_tabs():
    _app()
    window = MainWindow()
    assert window.tabs.parentWidget() is window.centralWidget()
    assert window.tabs.widget(0) is window.positions_panel
    assert window.tabs.widget(1) is window.inventory_panel
    assert window.tabs.tabText(0) == "Positions"
    assert window.tabs.tabText(1) == "Inventory"


def test_banner_shown_when_no_shared_folder_configured():
    _app()
    window = MainWindow()
    assert not window._share_banner.isHidden()


def test_banner_hidden_when_shared_folder_configured(tmp_path):
    _app()
    save_settings(tmp_path / "settings.json", {"shared_folder": str(tmp_path)})

    window = MainWindow()

    assert window._share_banner.isHidden()


def test_banner_dismiss_button_hides_it():
    _app()
    window = MainWindow()

    window._share_banner._dismiss_button.click()

    assert window._share_banner.isHidden()


def test_open_settings_button_on_banner_opens_settings(monkeypatch):
    _app()
    calls = []
    monkeypatch.setattr(main_window_module.MainWindow, "_open_settings", lambda self: calls.append(True))

    window = MainWindow()
    window._share_banner._open_button.click()

    assert calls == [True]


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


def test_corrupt_settings_shows_a_warning_and_still_opens(monkeypatch, tmp_path):
    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    _app()

    window = MainWindow()

    assert len(warnings) == 1
    assert window._settings == DEFAULT_SETTINGS


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


def test_main_window_prunes_the_archive_on_startup(monkeypatch, tmp_path):
    _app()
    calls = []
    monkeypatch.setattr(
        "app.ui.main_window.prune_archive",
        lambda settings: calls.append(settings) or 0,
    )

    MainWindow()

    assert len(calls) == 1


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
    # rather than on the code. Verified to round-trip exactly (same value
    # Task 18 verified for the CSV dialog on this same platform).
    assert second.size().width() == 742
    assert second.size().height() == 531


def test_shortcuts_are_registered():
    _app()
    window = MainWindow()

    shortcuts = {a.shortcut().toString() for a in window.actions()}
    assert {"Ctrl+P", "Ctrl+O", "Ctrl+,"} <= shortcuts
