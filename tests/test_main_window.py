from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_main_window_title():
    _app()
    window = MainWindow()
    assert window.windowTitle() == "Barcode Label Generator"
