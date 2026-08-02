from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from barcode.errors import BarcodeError
from PIL import Image
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator
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
from app.core.label_renderer import apply_orientation, render_label
from app.core.position_generator import (
    NUMBER_MAX,
    codes_from_csv_rows,
    generate_position_codes,
)
from app.core.print_service import send_to_printer
from app.core.zpl_print_service import windows_print_errors
from app.ui.csv_import_dialog import CsvImportDialog

_LETTER_VALIDATOR = QRegularExpressionValidator(QRegularExpression("[A-Za-z]"))

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename_component(value: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", value)


class ArchiveError(OSError):
    pass


POSITION_CSV_FIELDS = [
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]


class PositionsModePanel(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.generated_codes: list[str] = []
        self.generated_labels: list[Image.Image] = []
        self._generated_label_size: dict | None = None

        self.warehouse_combo = QComboBox()
        self.corridor_edit = QLineEdit()
        self.corridor_edit.setValidator(_LETTER_VALIDATOR)
        self.corridor_edit.setMaxLength(1)
        self.number_from_edit = QLineEdit()
        self.number_from_edit.setValidator(QIntValidator(0, NUMBER_MAX, self))
        self.number_to_edit = QLineEdit()
        self.number_to_edit.setValidator(QIntValidator(0, NUMBER_MAX, self))
        self.number_to_edit.setPlaceholderText("same as from (optional)")

        self.height_enabled_check = QCheckBox("Use height")
        self.height_from_edit = QLineEdit()
        self.height_from_edit.setValidator(_LETTER_VALIDATOR)
        self.height_from_edit.setMaxLength(1)
        self.height_to_edit = QLineEdit()
        self.height_to_edit.setValidator(_LETTER_VALIDATOR)
        self.height_to_edit.setMaxLength(1)

        self.custom_text_edit = QLineEdit()

        self.label_size_combo = QComboBox()
        self.refresh_from_settings(settings)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Landscape", "Portrait"])

        self.result_label = QLabel("0 labels generated")
        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(self._on_generate_clicked)

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

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
        form.addRow("Orientation", self.orientation_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(generate_button)
        layout.addWidget(self.import_csv_button)
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
        except (ValueError, BarcodeError) as error:
            QMessageBox.warning(self, "Invalid range", str(error))

    def _on_print_clicked(self) -> None:
        try:
            self.print_current_labels()
        except ArchiveError as error:
            QMessageBox.warning(
                self,
                "Archive failed",
                f"Labels printed, but the PDF archive failed: {error}\n"
                "Do not reprint this batch.",
            )
        except (ValueError, BarcodeError, OSError, *windows_print_errors()) as error:
            QMessageBox.warning(self, "Print failed", str(error))

    def generate(self) -> list[tuple[str, Image.Image]]:
        height_from = self.height_from_edit.text() or None
        height_to = self.height_to_edit.text() or None
        if not self.height_enabled_check.isChecked():
            height_from = height_to = None

        codes = generate_position_codes(
            self.corridor_edit.text(),
            self.number_from_edit.text(),
            self.number_to_edit.text() or None,
            height_from,
            height_to,
        )

        results = self._render_labels(codes)
        self.result_label.setText(f"{len(results)} labels generated")
        return results

    def generate_from_rows(self, rows: list[dict[str, str]]) -> list[tuple[str, Image.Image]]:
        codes, skipped_rows = codes_from_csv_rows(rows)
        if not codes:
            raise ValueError("No valid position codes found in the imported rows")

        results = self._render_labels(codes)

        if skipped_rows:
            unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f"{len(results)} labels generated ({len(skipped_rows)} {unit} skipped)"
            )
        else:
            self.result_label.setText(f"{len(results)} labels generated")
        return results

    def _render_labels(self, codes: list[str]) -> list[tuple[str, Image.Image]]:
        warehouse_prefix = self.warehouse_combo.currentData() or ""
        label_size = self.label_size_combo.currentData()
        if label_size is None:
            raise ValueError("No label size selected - add one in Settings first")
        width_mm, height_mm = apply_orientation(
            label_size["width_mm"], label_size["height_mm"], self.orientation_combo.currentText()
        )
        custom_text = self.custom_text_edit.text()

        results = []
        for code in codes:
            visible_text = f"{code} {custom_text}".strip()
            barcode_data = f"{warehouse_prefix}{code}"
            image = render_label(
                barcode_data,
                visible_text,
                width_mm=width_mm,
                height_mm=height_mm,
            )
            results.append((code, image))

        self.generated_codes = codes
        self.generated_labels = [image for _, image in results]
        self._generated_label_size = {"width_mm": width_mm, "height_mm": height_mm}
        return results

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(POSITION_CSV_FIELDS, parent=self)
        if not dialog.exec():
            return
        try:
            self.generate_from_rows(dialog.get_mapped_rows())
        except ValueError as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def print_current_labels(self, output_pdf_path: Path | None = None) -> None:
        if not self.generated_labels:
            raise ValueError("Nothing to print - generate labels first")

        # Use the size the labels were actually rendered at, not whatever the
        # combo currently shows - the user may have changed it after Generate.
        label_size = self._generated_label_size

        send_to_printer(
            self.generated_labels,
            width_mm=label_size["width_mm"],
            height_mm=label_size["height_mm"],
            settings=self._settings,
            output_pdf_path=output_pdf_path,
        )

        warehouse_prefix = self.warehouse_combo.currentData() or ""
        shared_folder = self._settings.get("shared_folder") or default_settings_path().parent
        if len(self.generated_codes) > 1:
            description = f"{self.generated_codes[0]}..{self.generated_codes[-1]}"
        else:
            description = self.generated_codes[0]

        log_path = Path(shared_folder) / "audit_log.csv"
        append_print_log(
            log_path,
            mode="positions",
            warehouse_prefix=warehouse_prefix,
            count=len(self.generated_codes),
            description=description,
        )

        try:
            archive_dir = Path(shared_folder) / "printed_pdfs"
            archive_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            archive_name = (
                f"{timestamp}_{_safe_filename_component(warehouse_prefix)}"
                f"_{_safe_filename_component(description)}.pdf"
            )
            send_to_printer(
                self.generated_labels,
                width_mm=label_size["width_mm"],
                height_mm=label_size["height_mm"],
                settings=self._settings,
                output_pdf_path=archive_dir / archive_name,
            )
        except OSError as error:
            raise ArchiveError(str(error)) from error
