from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import shared_folder
from app.core.inventory_import import (
    INVENTORY_CSV_FIELDS,
    InventoryItem,
    items_from_csv_rows,
)
from app.core.position_generator import display_position_code
from app.core.print_batch import BatchResult, print_batch
from app.core.template_renderer import TemplatePreset, list_presets, render_records
from app.core.zpl_print_service import windows_print_errors
from app.ui.csv_import_dialog import CsvImportDialog

TABLE_COLUMNS = ["", "SKU", "Name", "Client", "Position", "Batch", "Expiry"]

_DESCRIPTION_SKU_LIMIT = 5


def _describe_skus(skus: list[str], limit: int = _DESCRIPTION_SKU_LIMIT) -> str:
    unique_skus = list(dict.fromkeys(skus))
    description = ", ".join(unique_skus[:limit])
    remaining = len(unique_skus) - limit
    if remaining > 0:
        description += f" +{remaining} more"
    return description


class InventoryModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.items: list[InventoryItem] = []

        self.warehouse_combo = QComboBox()
        self.preset_combo = QComboBox()
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 items imported")

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))

        self.items_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(TABLE_COLUMNS)

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Template", self.preset_combo)

        select_buttons = QHBoxLayout()
        select_buttons.addWidget(self.select_all_button)
        select_buttons.addWidget(self.select_none_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.import_csv_button)
        layout.addWidget(self.result_label)
        layout.addLayout(select_buttons)
        layout.addWidget(self.items_table)
        layout.addWidget(self.print_button)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        folder = shared_folder(settings)
        self.preset_combo.clear()
        for preset in list_presets(folder, "inventory"):
            self.preset_combo.addItem(preset.name, preset)

        if self.preset_combo.count() == 0:
            self._warn_no_presets(folder)

    def _warn_no_presets(self, shared_folder) -> None:
        window = self.window()
        if not hasattr(window, "statusBar"):
            return  # not embedded in a QMainWindow (e.g. a standalone test)
        window.statusBar().showMessage(
            f"No label templates found in '{shared_folder}' - check the "
            "shared folder's templates directory or your permissions."
        )

    def load_items(self, rows: list[dict[str, str]]) -> list[InventoryItem]:
        items, skipped_rows = items_from_csv_rows(rows)
        if not items:
            raise ValueError("No valid inventory rows found in the imported file")

        self.items = items
        self._populate_table(items)

        item_unit = "item" if len(items) == 1 else "items"
        if skipped_rows:
            row_unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f"{len(items)} {item_unit} imported ({len(skipped_rows)} {row_unit} skipped)"
            )
        else:
            self.result_label.setText(f"{len(items)} {item_unit} imported")
        return items

    def _populate_table(self, items: list[InventoryItem]) -> None:
        self.items_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            self.items_table.setItem(row_index, 0, check_item)

            values = [item.sku, item.name, item.client, item.position_code, item.batch, item.expiry]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row_index, column, cell)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None:
                check_item.setCheckState(state)

    def checked_items(self) -> list[InventoryItem]:
        checked = []
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None and check_item.checkState() == Qt.CheckState.Checked:
                checked.append(self.items[row])
        return checked

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(INVENTORY_CSV_FIELDS, parent=self)
        if not dialog.exec():
            return
        try:
            self.load_items(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def _on_print_clicked(self) -> None:
        try:
            result = self.print_checked_items()
        except (ValueError, OSError, *windows_print_errors()) as error:
            QMessageBox.warning(self, "Print failed", str(error))
            return
        if result.warnings:
            QMessageBox.warning(self, "Printed with warnings", "\n\n".join(result.warnings))

    def print_checked_items(self, output_pdf_path: Path | None = None) -> BatchResult:
        checked = self.checked_items()
        if not checked:
            raise ValueError("Nothing to print - import a CSV and check at least one row")

        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            raise ValueError("No warehouse selected - add one in Settings first")

        preset: TemplatePreset | None = self.preset_combo.currentData()
        if preset is None:
            raise ValueError(
                "No label template selected - check the shared folder's templates directory"
            )

        generated_date = datetime.now(timezone.utc).astimezone().strftime("%Y/%m/%d")

        records = [
            {
                "sku": item.sku,
                "name": item.name,
                "client": item.client,
                "batch": item.batch,
                "expiry": item.expiry,
                "position_code": display_position_code(item.position_code),
                "position_data": f"{warehouse_prefix}{item.position_code}",
                "generated_date": generated_date,
            }
            for item in checked
        ]
        images = render_records(preset, records)

        description = _describe_skus([item.sku for item in checked])
        return print_batch(
            images,
            preset,
            self._settings,
            mode="inventory",
            warehouse_prefix=warehouse_prefix,
            description=description,
            output_pdf_path=output_pdf_path,
        )
