from __future__ import annotations

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

from app.core.label_renderer import render_label
from app.core.position_generator import generate_position_codes


class PositionsModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.generated_codes: list[str] = []
        self.generated_labels: list[Image.Image] = []

        self.warehouse_combo = QComboBox()
        for warehouse in settings.get("warehouses", []):
            self.warehouse_combo.addItem(warehouse["name"], warehouse["prefix"])

        self.corridor_edit = QLineEdit()
        self.number_from_edit = QLineEdit()
        self.number_to_edit = QLineEdit()

        self.height_enabled_check = QCheckBox("Use height")
        self.height_from_edit = QLineEdit()
        self.height_to_edit = QLineEdit()

        self.custom_text_edit = QLineEdit()

        self.label_size_combo = QComboBox()
        for size in settings.get("label_sizes", []):
            self.label_size_combo.addItem(size["name"], size)

        self.result_label = QLabel("0 labels generated")
        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(self._on_generate_clicked)

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

    def _on_generate_clicked(self) -> None:
        try:
            self.generate()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid range", str(error))

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
