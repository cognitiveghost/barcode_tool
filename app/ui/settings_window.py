from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.audit_log import consolidate_audit_log
from app.core.config import default_settings_path, load_settings, save_settings


class SettingsWindow(QDialog):
    def __init__(self, settings: dict, settings_path: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._settings_path = settings_path

        self.shared_folder_edit = QLineEdit(settings.get("shared_folder", ""))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_shared_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.shared_folder_edit)
        folder_row.addWidget(browse_button)

        consolidate_button = QPushButton("Consolidate audit log")
        consolidate_button.clicked.connect(self._consolidate_audit_log)

        self.printer_combo = QComboBox()
        printer_names = [p.printerName() for p in QPrinterInfo.availablePrinters()]
        self.printer_combo.addItems(printer_names)
        current_printer = settings.get("default_printer", "")
        if current_printer and current_printer not in printer_names:
            # Printer may just be offline right now - keep it selected instead
            # of silently dropping it and overwriting the setting on save.
            self.printer_combo.addItem(current_printer)
        if current_printer:
            self.printer_combo.setCurrentText(current_printer)

        self.print_mode_combo = QComboBox()
        self.print_mode_combo.addItem("OS driver (QPrinter)", "driver")
        self.print_mode_combo.addItem("Raw ZPL (direct)", "raw_zpl")
        mode_index = self.print_mode_combo.findData(settings.get("print_mode", "driver"))
        if mode_index >= 0:
            self.print_mode_combo.setCurrentIndex(mode_index)

        self.raw_zpl_target_edit = QLineEdit(settings.get("raw_zpl_target", ""))
        if sys.platform == "win32":
            self.raw_zpl_target_edit.setPlaceholderText("e.g. ZPL-RAW-Printer (raw print queue name)")
        else:
            self.raw_zpl_target_edit.setPlaceholderText("e.g. /dev/usb/lp0")

        self.warehouse_table = QTableWidget(0, 2)
        self.warehouse_table.setHorizontalHeaderLabels(["Name", "Prefix"])
        for warehouse in settings.get("warehouses", []):
            self._add_warehouse_row(warehouse["name"], warehouse["prefix"])

        add_warehouse_button = QPushButton("Add warehouse")
        add_warehouse_button.clicked.connect(lambda: self._add_warehouse_row("", ""))
        remove_warehouse_button = QPushButton("Remove selected")
        remove_warehouse_button.clicked.connect(self._remove_selected_warehouse)
        warehouse_buttons = QHBoxLayout()
        warehouse_buttons.addWidget(add_warehouse_button)
        warehouse_buttons.addWidget(remove_warehouse_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(folder_row)
        layout.addWidget(consolidate_button)
        layout.addWidget(self.printer_combo)
        layout.addWidget(self.print_mode_combo)
        layout.addWidget(self.raw_zpl_target_edit)
        layout.addWidget(self.warehouse_table)
        layout.addLayout(warehouse_buttons)
        layout.addWidget(buttons)

    def _browse_shared_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select shared folder")
        if folder:
            self.shared_folder_edit.setText(folder)

    def _consolidate_audit_log(self) -> None:
        shared_folder = self.shared_folder_edit.text() or str(default_settings_path().parent)
        merged = consolidate_audit_log(Path(shared_folder))
        if merged:
            QMessageBox.information(
                self, "Audit log consolidated", f"Merged {merged} row(s) into audit_log.csv."
            )
        else:
            QMessageBox.information(
                self, "Audit log consolidated", "No per-print audit files found to merge."
            )

    def _add_warehouse_row(self, name: str, prefix: str) -> None:
        row = self.warehouse_table.rowCount()
        self.warehouse_table.insertRow(row)
        self.warehouse_table.setItem(row, 0, QTableWidgetItem(name))
        self.warehouse_table.setItem(row, 1, QTableWidgetItem(prefix))

    def _remove_selected_warehouse(self) -> None:
        for index in sorted(
            {i.row() for i in self.warehouse_table.selectedIndexes()}, reverse=True
        ):
            self.warehouse_table.removeRow(index)

    def get_current_settings(self) -> dict:
        warehouses = []
        for row in range(self.warehouse_table.rowCount()):
            name_item = self.warehouse_table.item(row, 0)
            prefix_item = self.warehouse_table.item(row, 1)
            warehouses.append(
                {
                    "name": name_item.text() if name_item else "",
                    "prefix": prefix_item.text() if prefix_item else "",
                }
            )
        return {
            "shared_folder": self.shared_folder_edit.text(),
            "default_printer": self.printer_combo.currentText(),
            "warehouses": warehouses,
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
        }

    def _save_and_close(self) -> None:
        if self._settings_path is None:
            QMessageBox.warning(self, "Cannot save", "No settings file location configured.")
            return
        full_settings = load_settings(self._settings_path)
        full_settings.update(self.get_current_settings())
        save_settings(self._settings_path, full_settings)
        self.accept()
