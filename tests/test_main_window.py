from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"


def test_main_window_hosts_positions_panel_as_central_widget():
    _app()
    window = MainWindow()
    assert window.centralWidget() is window.positions_panel
