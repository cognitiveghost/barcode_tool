from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

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


def test_consolidate_audit_log_button_reports_merged_count(monkeypatch, tmp_path):
    _app()
    from app.core.audit_log import append_print_log

    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=1, description="H029",
                      preset="Standard", printer="HP-1")

    settings = {**DEFAULT_SETTINGS, "shared_folder": str(tmp_path)}
    window = SettingsWindow(settings, settings_path=None)
    messages = []
    monkeypatch.setattr(
        "app.ui.settings_window.QMessageBox.information",
        lambda *args, **kwargs: messages.append(args),
    )

    window._consolidate_audit_log()

    assert len(messages) == 1
    assert "1" in messages[0][2]


def test_open_log_folder_creates_the_directory_if_missing(monkeypatch, tmp_path):
    _app()
    settings = {**DEFAULT_SETTINGS, "shared_folder": str(tmp_path)}
    window = SettingsWindow(settings, settings_path=None)
    calls = []
    monkeypatch.setattr(
        "app.ui.settings_window.QDesktopServices.openUrl", lambda url: calls.append(url)
    )

    window._open_log_folder()

    assert (tmp_path / "logs").is_dir()
    assert len(calls) == 1


def test_raw_zpl_mode_requires_a_target():
    # An empty target reached Path("").write_bytes and surfaced as a cryptic
    # OS error at print time instead of here.
    _app()
    window = SettingsWindow({}, None)
    window.print_mode_combo.setCurrentIndex(window.print_mode_combo.findData("raw_zpl"))
    window.raw_zpl_target_edit.setText("")

    assert "target" in window.validation_error().lower()


def test_driver_mode_does_not_require_a_zpl_target():
    _app()
    window = SettingsWindow({}, None)
    window.print_mode_combo.setCurrentIndex(window.print_mode_combo.findData("driver"))

    assert window.validation_error() is None


def test_duplicate_warehouse_prefixes_are_rejected():
    _app()
    window = SettingsWindow(
        {
            "warehouses": [
                {"name": "Main", "prefix": "C001"},
                {"name": "Spare", "prefix": "C001"},
            ]
        },
        None,
    )

    assert "prefix" in window.validation_error().lower()


def test_warehouse_with_an_empty_name_is_rejected():
    _app()
    window = SettingsWindow({"warehouses": [{"name": "", "prefix": "C001"}]}, None)

    assert "name" in window.validation_error().lower()


def test_every_field_has_a_visible_label():
    _app()
    window = SettingsWindow({}, None)

    labels = {label.text() for label in window.findChildren(QLabel)}
    assert "Shared folder" in labels
    assert "Printer" in labels
    assert "Print mode" in labels
    assert "Raw ZPL target" in labels


def test_save_and_close_shows_warning_on_oserror(monkeypatch, tmp_path):
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=tmp_path / "settings.json")
    monkeypatch.setattr(
        "app.ui.settings_window.save_settings",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    warned = []
    monkeypatch.setattr(
        "app.ui.settings_window.QMessageBox.warning",
        staticmethod(lambda *a, **k: warned.append(a[2]) or QMessageBox.StandardButton.Ok),
    )

    window._save_and_close()  # must not raise

    assert warned


def test_consolidate_audit_log_shows_warning_on_oserror(monkeypatch, tmp_path):
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=tmp_path / "settings.json")
    monkeypatch.setattr(
        "app.ui.settings_window.consolidate_audit_log",
        lambda *a, **k: (_ for _ in ()).throw(OSError("network path not found")),
    )
    warned = []
    monkeypatch.setattr(
        "app.ui.settings_window.QMessageBox.warning",
        staticmethod(lambda *a, **k: warned.append(a[2]) or QMessageBox.StandardButton.Ok),
    )

    window._consolidate_audit_log()  # must not raise

    assert warned


def test_open_log_folder_shows_warning_on_oserror(monkeypatch, tmp_path):
    _app()
    window = SettingsWindow(DEFAULT_SETTINGS, settings_path=tmp_path / "settings.json")
    monkeypatch.setattr(
        "pathlib.Path.mkdir",
        lambda *a, **k: (_ for _ in ()).throw(OSError("permission denied")),
    )
    warned = []
    monkeypatch.setattr(
        "app.ui.settings_window.QMessageBox.warning",
        staticmethod(lambda *a, **k: warned.append(a[2]) or QMessageBox.StandardButton.Ok),
    )

    window._open_log_folder()  # must not raise

    assert warned
