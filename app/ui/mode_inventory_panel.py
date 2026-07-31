from __future__ import annotations

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

from app.core.audit_log import append_print_log
from app.core.config import default_settings_path
from app.core.inventory_import import (
    INVENTORY_CSV_FIELDS,
    InventoryItem,
    items_from_csv_rows,
)
from app.core.label_renderer import render_inventory_label
from app.core.print_service import print_labels
from app.ui.csv_import_dialog import CsvImportDialog

TABLE_COLUMNS = ["", "SKU", "Name", "Position", "Batch", "Expiry"]


class InventoryModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.items: list[InventoryItem] = []

        self.warehouse_combo = QComboBox()
        self.label_size_combo = QComboBox()
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
        form.addRow("Label size", self.label_size_combo)

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

        self.label_size_combo.clear()
        for size in settings.get("label_sizes", []):
            self.label_size_combo.addItem(size["name"], size)

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

            values = [item.sku, item.name, item.position_code, item.batch, item.expiry]
            for column, value in enumerate(values, start=1):
                self.items_table.setItem(row_index, column, QTableWidgetItem(value))

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
            self.print_checked_items()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Print failed", str(error))

    def print_checked_items(self, output_pdf_path: Path | None = None) -> None:
        checked = self.checked_items()
        if not checked:
            raise ValueError("Nothing to print - import a CSV and check at least one row")

        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")

        warehouse_prefix = self.warehouse_combo.currentData() or ""

        images = []
        for item in checked:
            text_lines = [item.name] if item.name else []
            if item.batch:
                text_lines.append(f"Batch {item.batch}")
            if item.expiry:
                text_lines.append(f"Exp {item.expiry}")
            image = render_inventory_label(
                item.sku,
                "\n".join(text_lines),
                f"{warehouse_prefix}{item.position_code}",
                width_mm=label_size["width_mm"],
                height_mm=label_size["height_mm"],
            )
            images.append(image)

        print_labels(
            images,
            width_mm=label_size["width_mm"],
            height_mm=label_size["height_mm"],
            printer_name=self._settings.get("default_printer") or None,
            output_pdf_path=output_pdf_path,
        )

        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        log_path = Path(shared_folder) / "audit_log.csv"
        skus = [item.sku for item in checked]
        description = f"{skus[0]}..{skus[-1]}" if len(skus) > 1 else skus[0]
        append_print_log(
            log_path,
            mode="inventory",
            warehouse_prefix=warehouse_prefix,
            count=len(checked),
            description=description,
        )
