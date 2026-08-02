from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.config import default_settings_path, load_settings
from app.core.print_batch import prune_archive
from app.ui.mode_inventory_panel import InventoryModePanel
from app.ui.mode_positions_panel import PositionsModePanel
from app.ui.settings_window import SettingsWindow


class _ShareBanner(QWidget):
    open_settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        label = QLabel("No shared folder configured - using local folder.")
        self._open_button = QPushButton("Open Settings")
        self._open_button.clicked.connect(self.open_settings_requested)
        self._dismiss_button = QPushButton("×")
        self._dismiss_button.setFixedWidth(24)
        self._dismiss_button.clicked.connect(self.hide)

        layout = QHBoxLayout(self)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(self._open_button)
        layout.addWidget(self._dismiss_button)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Barcode Label Generator")
        self.resize(900, 600)

        self._settings_path = default_settings_path()
        self._settings = load_settings(self._settings_path, on_recovery=self._warn_settings_recovered)
        prune_archive(self._settings)

        self.positions_panel = PositionsModePanel(self._settings)
        self.inventory_panel = InventoryModePanel(self._settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.positions_panel, "Positions")
        self.tabs.addTab(self.inventory_panel, "Inventory")

        self._share_banner = _ShareBanner()
        self._share_banner.open_settings_requested.connect(self._open_settings)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self._share_banner)
        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central)
        self._update_share_banner()

        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        self.menuBar().addAction(settings_action)

    def _warn_settings_recovered(self, message: str) -> None:
        QMessageBox.warning(self, "Settings reset", message)

    def _update_share_banner(self) -> None:
        if self._settings.get("shared_folder"):
            self._share_banner.hide()
        else:
            self._share_banner.show()

    def _open_settings(self) -> None:
        dialog = SettingsWindow(self._settings, self._settings_path, parent=self)
        if dialog.exec():
            self._settings = load_settings(self._settings_path)
            self.positions_panel.refresh_from_settings(self._settings)
            self.inventory_panel.refresh_from_settings(self._settings)
            self._update_share_banner()
