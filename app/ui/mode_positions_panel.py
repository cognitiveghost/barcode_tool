from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.audit_log import append_print_log
from app.core.config import default_settings_path
from app.core.label_renderer import render_label
from app.core.position_generator import generate_position_codes
from app.core.print_service import print_labels


class PositionsModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.generated_codes: list[str] = []
        self.generated_labels: list[Image.Image] = []

        self.warehouse_combo = QComboBox()
        self.corridor_edit = QLineEdit()
        self.number_from_edit = QLineEdit()
        self.number_to_edit = QLineEdit()

        self.height_enabled_check = QCheckBox("Use height")
        self.height_from_edit = QLineEdit()
        self.height_to_edit = QLineEdit()

        self.custom_text_edit = QLineEdit()

        self.label_size_combo = QComboBox()
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 labels generated")
        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(self._on_generate_clicked)

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Corridor", self.corridor_edit)
        form.addRow("Number from", self.number_from_edit)
        form.addRow("Number to", self.number_to_edit)
        form.addRow(self.height_enabled_check)
        form.addRow("Height from", self.height_from_edit)
        form.addRow("Height to", self.height_to_edit)
        form.addRow("Custom text", self.custom_text_edit)
        form.addRow("Label size", self.label_size_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(generate_button)
        layout.addWidget(self.result_label)
        layout.addWidget(self.print_button)

    def refresh_from_settings(self, settings: dict) -> None:
        self._settings = settings

        self.warehouse_combo.clear()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        self.label_size_combo.clear()
        for size in settings.get("label_sizes", []):
            self.label_size_combo.addItem(size["name"], size)

    def _on_generate_clicked(self) -> None:
        try:
            self.generate()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid range", str(error))

    def _on_print_clicked(self) -> None:
        try:
            self.print_current_labels()
        except ValueError as error:
            QMessageBox.warning(self, "Nothing to print", str(error))

    def generate(self) -> list[tuple[str, Image.Image]]:
        warehouse_prefix = self.warehouse_combo.currentData() or ""
        height_from = self.height_from_edit.text() or None
        height_to = self.height_to_edit.text() or None
        if not self.height_enabled_check.isChecked():
            height_from = height_to = None

        codes = generate_position_codes(
            self.corridor_edit.text(),
            self.number_from_edit.text(),
            self.number_to_edit.text(),
            height_from,
            height_to,
        )

        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")
        custom_text = self.custom_text_edit.text()

        results = []
        for code in codes:
            visible_text = f"{code} {custom_text}".strip()
            barcode_data = f"{warehouse_prefix}{code}"
            image = render_label(
                barcode_data,
                visible_text,
                width_mm=label_size["width_mm"],
                height_mm=label_size["height_mm"],
            )
            results.append((code, image))

        self.generated_codes = codes
        self.generated_labels = [image for _, image in results]
        self.result_label.setText(f"{len(results)} labels generated")
        return results

    def print_current_labels(self, output_pdf_path: Path | None = None) -> None:
        if not self.generated_labels:
            raise ValueError("Nothing to print - generate labels first")

        label_size = self.label_size_combo.currentData()
        printer_name = self._settings.get("default_printer") or None

        print_labels(
            self.generated_labels,
            width_mm=label_size["width_mm"],
            height_mm=label_size["height_mm"],
            printer_name=printer_name,
            output_pdf_path=output_pdf_path,
        )

        warehouse_prefix = self.warehouse_combo.currentData() or ""
        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        log_path = Path(shared_folder) / "audit_log.csv"
        if len(self.generated_codes) > 1:
            description = f"{self.generated_codes[0]}..{self.generated_codes[-1]}"
        else:
            description = self.generated_codes[0]
        append_print_log(
            log_path,
            mode="positions",
            warehouse_prefix=warehouse_prefix,
            count=len(self.generated_codes),
            description=description,
        )
