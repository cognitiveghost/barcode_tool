from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from barcode.errors import BarcodeError
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import qsettings, shared_folder
from app.core.inventory_import import (
    INVENTORY_CSV_FIELDS,
    InventoryItem,
    items_from_csv_rows,
)
from app.core.position_generator import display_position_code
from app.core.print_batch import BatchResult, PrintCancelled, print_batch
from app.core.template_renderer import (
    TemplatePreset,
    list_presets,
    render_records,
    render_table_pdf,
)
from app.ui.csv_import_dialog import CsvImportDialog
from app.ui.print_preview_dialog import PrintPreviewDialog
from app.ui.skipped_rows_dialog import SkippedRowsDialog

TABLE_COLUMNS = ["", "SKU", "Qty", "Name", "Client", "Position", "Batch", "Expiry"]

# A4 table-report presets live in their own mode folder, never in the
# per-label "inventory" one - keeps them out of the Print button's Template
# dropdown, where a whole-list template would render as garbage.
TABLE_PRESET_MODE = "inventory-table"

_DESCRIPTION_SKU_LIMIT = 5

LARGE_BATCH_THRESHOLD = 200
_RENDER_CHUNK_SIZE = 50
_ESTIMATED_SECONDS_PER_LABEL = 0.02


def _describe_skus(skus: list[str], limit: int = _DESCRIPTION_SKU_LIMIT) -> str:
    unique_skus = list(dict.fromkeys(skus))
    description = ", ".join(unique_skus[:limit])
    remaining = len(unique_skus) - limit
    if remaining > 0:
        description += f" +{remaining} more"
    return description


def _validate_inventory_mapping(mapping: dict[str, int | None]) -> str | None:
    if mapping.get("sku") is not None:
        return None
    return "SKU must be mapped"


def _record_for_item(item: InventoryItem, warehouse_prefix: str, generated_date: str) -> dict:
    return {
        "sku": item.sku,
        "name": item.name,
        "client": item.client,
        "batch": item.batch,
        "expiry": item.expiry,
        "position_code": display_position_code(item.position_code),
        "position_data": f"{warehouse_prefix}{item.position_code}",
        "generated_date": generated_date,
        "quantity": str(item.quantity),
    }


class InventoryModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.items: list[InventoryItem] = []
        self._last_skipped_rows: list = []
        self._last_import_rows: list[dict[str, str]] = []

        self.warehouse_combo = QComboBox()
        self.preset_combo = QComboBox()
        self.preset_combo.activated.connect(self._on_preset_selected)
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 items imported")
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.result_label.linkActivated.connect(self._show_skipped_rows_detail)

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))

        self.items_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.items_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.items_table.itemChanged.connect(lambda _item: self._update_selection_label())

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by SKU, name or position")
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.selection_label = QLabel("0 of 0 selected")

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)
        self.print_button.setEnabled(False)

        self.export_table_button = QPushButton("Export table (PDF)...")
        self.export_table_button.clicked.connect(self._on_export_table_clicked)
        self.export_table_button.setEnabled(False)

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
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.selection_label)
        layout.addWidget(self.items_table)
        layout.addWidget(self.print_button)
        layout.addWidget(self.export_table_button)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        folder = shared_folder(settings)
        self.preset_combo.clear()
        for preset in list_presets(folder, "inventory"):
            self.preset_combo.addItem(preset.name, preset)
        remembered_name = qsettings().value("inventory/last_template")
        if remembered_name is not None:
            index = self.preset_combo.findText(remembered_name)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)

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

    def _show_status(self, message: str) -> None:
        window = self.window()
        if not hasattr(window, "statusBar"):
            return  # not embedded in a QMainWindow (e.g. a standalone test)
        window.statusBar().showMessage(message, 5000)

    def _on_preset_selected(self, index: int) -> None:
        qsettings().setValue("inventory/last_template", self.preset_combo.itemText(index))

    def load_items(self, rows: list[dict[str, str]]) -> list[InventoryItem]:
        items, skipped_rows = items_from_csv_rows(rows)
        if not items:
            raise ValueError("No valid inventory rows found in the imported file")

        self.items = items
        self._populate_table(items)

        self._last_skipped_rows = skipped_rows
        self._last_import_rows = rows
        item_unit = "item" if len(items) == 1 else "items"
        if skipped_rows:
            row_unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f'{len(items)} {item_unit} imported '
                f'(<a href="#">{len(skipped_rows)} {row_unit} skipped - show details</a>)'
            )
        else:
            self.result_label.setText(f"{len(items)} {item_unit} imported")
        return items

    def _populate_table(self, items: list[InventoryItem]) -> None:
        self.items_table.setSortingEnabled(False)
        # itemChanged fires once per setItem and the handler counts every row.
        # With 2000 SKUs that is 14 000 signals x a 2000-row scan; block them
        # and update the count once at the end.
        self.items_table.blockSignals(True)
        self.items_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            # The row carries its own item: the table can be re-sorted, so the
            # row index is not a stable key into self.items.
            check_item.setData(Qt.ItemDataRole.UserRole, item)
            self.items_table.setItem(row_index, 0, check_item)

            values = [
                item.sku,
                str(item.quantity),
                item.name,
                item.client,
                item.position_code,
                item.batch,
                item.expiry,
            ]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row_index, column, cell)
        self.items_table.blockSignals(False)
        self.items_table.setSortingEnabled(True)
        self._update_selection_label()

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None:
                check_item.setCheckState(state)
        self._update_selection_label()

    def checked_items(self) -> list[InventoryItem]:
        checked = []
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            if check_item is not None and check_item.checkState() == Qt.CheckState.Checked:
                checked.append(check_item.data(Qt.ItemDataRole.UserRole))
        return checked

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.items_table.rowCount()):
            check_item = self.items_table.item(row, 0)
            item = check_item.data(Qt.ItemDataRole.UserRole) if check_item else None
            haystack = (
                f"{item.sku} {item.name} {item.position_code}".lower() if item else ""
            )
            self.items_table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _update_selection_label(self) -> None:
        total = self.items_table.rowCount()
        checked_count = len(self.checked_items())
        self.selection_label.setText(f"{checked_count} of {total} selected")
        self.print_button.setEnabled(checked_count > 0)
        self.export_table_button.setEnabled(checked_count > 0)

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(
            INVENTORY_CSV_FIELDS,
            parent=self,
            settings=self._settings,
            mode="inventory",
            validate_mapping=_validate_inventory_mapping,
            row_would_be_skipped=lambda row: len(items_from_csv_rows([row])[0]) == 0,
        )
        if not dialog.exec():
            return
        try:
            self.load_items(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def _show_skipped_rows_detail(self, _href: str = "") -> None:
        dialog = SkippedRowsDialog(self._last_skipped_rows, self._last_import_rows, parent=self)
        dialog.exec()

    def _on_print_clicked(self) -> None:
        checked = self.checked_items()
        if not checked:
            QMessageBox.warning(
                self, "Print failed", "Nothing to print - import a CSV and check at least one row"
            )
            return
        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            QMessageBox.warning(
                self, "Print failed", "No warehouse selected - add one in Settings first"
            )
            return
        preset: TemplatePreset | None = self.preset_combo.currentData()
        if preset is None:
            QMessageBox.warning(
                self, "Print failed",
                "No label template selected - check the shared folder's templates directory",
            )
            return

        generated_date = datetime.now(timezone.utc).astimezone().strftime("%Y/%m/%d")

        def render_page(index: int) -> Image.Image:
            record = _record_for_item(checked[index], warehouse_prefix, generated_date)
            return render_records(preset, [record])[0]

        try:
            dialog = PrintPreviewDialog(
                count=len(checked),
                render_page=render_page,
                preset=preset,
                settings=self._settings,
                warehouse_display=self.warehouse_combo.currentText(),
                on_confirm=self.print_checked_items,
                parent=self,
            )
        except (ValueError, OSError, BarcodeError) as error:
            QMessageBox.warning(self, "Print failed", str(error))
            return
        if dialog.exec():
            unit = "item" if len(checked) == 1 else "items"
            self._show_status(f"Printed {len(checked)} {unit}")

    def print_checked_items(
        self, copies: int = 1, output_pdf_path: Path | None = None
    ) -> BatchResult:
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
        records = [_record_for_item(item, warehouse_prefix, generated_date) for item in checked]
        if len(records) > LARGE_BATCH_THRESHOLD:
            images = self._render_with_progress(preset, records)
        else:
            images = render_records(preset, records)

        description = _describe_skus([item.sku for item in checked])
        return print_batch(
            images,
            preset,
            self._settings,
            mode="inventory",
            warehouse_prefix=warehouse_prefix,
            description=description,
            copies=copies,
            output_pdf_path=output_pdf_path,
        )

    def _render_with_progress(
        self, preset: TemplatePreset, records: list[dict]
    ) -> list[Image.Image]:
        estimated_minutes = max(1, round(len(records) * _ESTIMATED_SECONDS_PER_LABEL / 60))
        answer = QMessageBox.question(
            self,
            "Print a large batch?",
            f"Render and print {len(records)} labels? This will take about "
            f"{estimated_minutes} minute{'s' if estimated_minutes != 1 else ''}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            raise PrintCancelled()

        progress = QProgressDialog("Rendering labels...", "Cancel", 0, len(records), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        images: list[Image.Image] = []
        try:
            for start in range(0, len(records), _RENDER_CHUNK_SIZE):
                if progress.wasCanceled():
                    raise PrintCancelled()
                chunk = records[start : start + _RENDER_CHUNK_SIZE]
                images.extend(render_records(preset, chunk))
                progress.setValue(min(start + _RENDER_CHUNK_SIZE, len(records)))
        finally:
            progress.close()
        return images

    def _on_export_table_clicked(self) -> None:
        checked = self.checked_items()
        if not checked:
            QMessageBox.warning(
                self, "Export failed", "Nothing to export - import a CSV and check at least one row"
            )
            return
        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            QMessageBox.warning(
                self, "Export failed", "No warehouse selected - add one in Settings first"
            )
            return
        table_presets = list_presets(shared_folder(self._settings), TABLE_PRESET_MODE)
        if not table_presets:
            QMessageBox.warning(
                self, "Export failed",
                "No A4 table template found - check the shared folder's templates directory",
            )
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export table as PDF", filter="PDF files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        generated_date = datetime.now(timezone.utc).astimezone().strftime("%Y/%m/%d")
        records = [_record_for_item(item, warehouse_prefix, generated_date) for item in checked]
        try:
            pdf_bytes = render_table_pdf(table_presets[0], records)
            Path(path).write_bytes(pdf_bytes)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return

        unit = "item" if len(checked) == 1 else "items"
        self._show_status(f"Exported {len(checked)} {unit} to {path}")
