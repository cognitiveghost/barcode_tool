from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow

from app.core.config import default_settings_path, load_settings
from app.ui.mode_positions_panel import PositionsModePanel
from app.ui.settings_window import SettingsWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Barcode Label Generator")
        self.resize(900, 600)

        self._settings_path = default_settings_path()
        self._settings = load_settings(self._settings_path)

        self.positions_panel = PositionsModePanel(self._settings)
        self.setCentralWidget(self.positions_panel)

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        self.menuBar().addAction(settings_action)

    def _open_settings(self) -> None:
        dialog = SettingsWindow(self._settings, self._settings_path, parent=self)
        if dialog.exec():
            self._settings = load_settings(self._settings_path)
            self.positions_panel.refresh_from_settings(self._settings)
