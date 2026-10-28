from __future__ import annotations

from pathlib import Path

from barcode.errors import BarcodeError
from PIL import Image
from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.core.position_generator import (
    NUMBER_MAX,
    codes_from_csv_rows,
    display_position_code,
    generate_position_codes,
)
from app.core.print_batch import BatchResult, print_batch
from app.core.template_renderer import TemplatePreset
from app.ui.csv_import_dialog import CsvImportDialog
from app.ui.mode_panel import ModePanel
from app.ui.print_preview_dialog import PrintPreviewDialog
from app.ui.skipped_rows_dialog import SkippedRowsDialog

# A Qt input mask (setInputMask) filters keystrokes in a code path that does
# not reliably see input delivered via IME/TSF - the norm on Windows for
# non-US keyboard layouts - so the corridor/height boxes could silently
# reject every real keypress while still working fine in tests (which
# inject synthetic key events that bypass IME entirely). A validator goes
# through QLineEdit's normal insert path instead, which both routes see.
_LETTER_VALIDATOR = QRegularExpressionValidator(QRegularExpression("[A-Za-z]"))


def _uppercase_as_typed(edit: QLineEdit) -> None:
    def _apply(text: str) -> None:
        if text != text.upper():
            edit.setText(text.upper())

    edit.textChanged.connect(_apply)


POSITION_CSV_FIELDS = [
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]


class GenerationCancelled(Exception):
    """Raised when the operator declines the large-batch confirmation or
    cancels mid-render. Caught silently at both call sites - cancelling is
    an expected, deliberate action, not an error to report."""


def _validate_position_mapping(mapping: dict[str, int | None]) -> str | None:
    has_position_code = mapping.get("position_code") is not None
    has_components = mapping.get("corridor") is not None and mapping.get("number") is not None
    if has_position_code or has_components:
        return None
    return "Map Position code, or both Corridor and Number"


class PositionsModePanel(ModePanel):
    MODE = "positions"
    LARGE_BATCH_TITLE = "Generate a large batch?"
    LARGE_BATCH_VERB = "Generate"
    CANCELLED = GenerationCancelled

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.generated_codes: list[str] = []
        self.generated_labels: list[Image.Image] = []
        self._generated_preset: TemplatePreset | None = None
        self._generated_warehouse: str | None = None
        self._last_skipped_rows: list = []
        self._last_import_rows: list[dict[str, str]] = []

        self.warehouse_combo = QComboBox()
        self.corridor_edit = QLineEdit()
        self.corridor_edit.setMaxLength(1)
        self.corridor_edit.setValidator(_LETTER_VALIDATOR)
        _uppercase_as_typed(self.corridor_edit)
        self.number_from_edit = QLineEdit()
        self.number_from_edit.setValidator(QIntValidator(0, NUMBER_MAX, self))
        self.number_to_edit = QLineEdit()
        self.number_to_edit.setValidator(QIntValidator(0, NUMBER_MAX, self))
        self.number_to_edit.setPlaceholderText("same as from (optional)")

        self.height_from_edit = QLineEdit()
        self.height_from_edit.setMaxLength(1)
        self.height_from_edit.setValidator(_LETTER_VALIDATOR)
        _uppercase_as_typed(self.height_from_edit)
        self.height_to_edit = QLineEdit()
        self.height_to_edit.setMaxLength(1)
        self.height_to_edit.setValidator(_LETTER_VALIDATOR)
        _uppercase_as_typed(self.height_to_edit)

        self.count_label = QLabel("")

        self.custom_text_edit = QLineEdit()

        self.preset_combo = QComboBox()
        self.preset_combo.activated.connect(self._on_preset_selected)
        self.refresh_from_settings(settings)

        self.result_label = QLabel("0 labels generated")
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.result_label.linkActivated.connect(self._show_skipped_rows_detail)
        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self._on_generate_clicked)

        self.import_csv_button = QPushButton("Import CSV...")
        self.import_csv_button.clicked.connect(self._on_import_csv_clicked)

        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self._on_print_clicked)
        self.print_button.setEnabled(False)

        form = QFormLayout()
        form.addRow("Warehouse", self.warehouse_combo)
        form.addRow("Corridor", self.corridor_edit)
        form.addRow("Number from", self.number_from_edit)
        form.addRow("Number to", self.number_to_edit)
        form.addRow("Height from", self.height_from_edit)
        form.addRow("Height to", self.height_to_edit)
        form.addRow("Count", self.count_label)
        form.addRow("Custom text", self.custom_text_edit)
        form.addRow("Template", self.preset_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.generate_button)
        layout.addWidget(self.import_csv_button)
        layout.addWidget(self.result_label)
        layout.addWidget(self.print_button)

        for edit in (
            self.corridor_edit,
            self.number_from_edit,
            self.number_to_edit,
            self.height_from_edit,
            self.height_to_edit,
        ):
            edit.textChanged.connect(self._update_count_preview)
        self._update_count_preview()

    def _on_generate_clicked(self) -> None:
        try:
            self.generate()
        except GenerationCancelled:
            return
        except (ValueError, BarcodeError) as error:
            QMessageBox.warning(self, "Invalid range", str(error))

    def _on_print_clicked(self) -> None:
        if not self.generated_labels:
            QMessageBox.warning(self, "Print failed", "Nothing to print - generate labels first")
            return
        try:
            dialog = PrintPreviewDialog(
                count=len(self.generated_labels),
                render_page=lambda index: self.generated_labels[index],
                preset=self._generated_preset,
                settings=self._settings,
                warehouse_display=self.warehouse_combo.currentText(),
                on_confirm=self.print_current_labels,
                parent=self,
            )
        except (ValueError, OSError, BarcodeError) as error:
            QMessageBox.warning(self, "Print failed", str(error))
            return
        if dialog.exec():
            unit = "label" if len(self.generated_labels) == 1 else "labels"
            self._show_status(f"Printed {len(self.generated_labels)} {unit}")

    def generate(self) -> list[tuple[str, Image.Image]]:
        height_from = self.height_from_edit.text() or None
        height_to = self.height_to_edit.text() or None

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

        self._last_skipped_rows = skipped_rows
        self._last_import_rows = rows
        if skipped_rows:
            unit = "row" if len(skipped_rows) == 1 else "rows"
            self.result_label.setText(
                f'{len(results)} labels generated '
                f'(<a href="#">{len(skipped_rows)} {unit} skipped - show details</a>)'
            )
        else:
            self.result_label.setText(f"{len(results)} labels generated")
        return results

    def _render_labels(self, codes: list[str]) -> list[tuple[str, Image.Image]]:
        warehouse_prefix = self.warehouse_combo.currentData()
        if not warehouse_prefix:
            raise ValueError("No warehouse selected - add one in Settings first")
        preset: TemplatePreset | None = self.preset_combo.currentData()
        if preset is None:
            raise ValueError(
                "No label template selected - check the shared folder's templates directory"
            )
        custom_text = self.custom_text_edit.text()

        # The warehouse prefix and the operator's text belong to the barcode
        # payload and the header respectively - never to the position caption.
        records = [
            {
                "code": code,
                "barcode_data": f"{warehouse_prefix}{code}",
                "visible_text": display_position_code(code),
                "user_text": custom_text,
                "warehouse_prefix": warehouse_prefix,
            }
            for code in codes
        ]
        images = self.render_labels(preset, records)
        results = list(zip(codes, images))

        self.generated_codes = codes
        self.generated_labels = images
        self._generated_preset = preset
        self._generated_warehouse = warehouse_prefix
        self.print_button.setEnabled(bool(self.generated_labels))
        return results

    def _update_count_preview(self) -> None:
        try:
            codes = generate_position_codes(
                self.corridor_edit.text(),
                self.number_from_edit.text(),
                self.number_to_edit.text() or None,
                self.height_from_edit.text() or None,
                self.height_to_edit.text() or None,
            )
        except ValueError:
            self.count_label.setText("")
            self.generate_button.setEnabled(False)
            return
        unit = "label" if len(codes) == 1 else "labels"
        self.count_label.setText(f"-> {len(codes)} {unit}")
        self.generate_button.setEnabled(bool(codes))

    def _on_import_csv_clicked(self) -> None:
        dialog = CsvImportDialog(
            POSITION_CSV_FIELDS,
            parent=self,
            settings=self._settings,
            mode="positions",
            validate_mapping=_validate_position_mapping,
            row_would_be_skipped=lambda row: len(codes_from_csv_rows([row])[0]) == 0,
        )
        if not dialog.exec():
            return
        try:
            self.generate_from_rows(dialog.get_mapped_rows())
        except GenerationCancelled:
            return
        except (ValueError, BarcodeError) as error:
            QMessageBox.warning(self, "Import failed", str(error))

    def _show_skipped_rows_detail(self, _href: str = "") -> None:
        dialog = SkippedRowsDialog(self._last_skipped_rows, self._last_import_rows, parent=self)
        dialog.exec()

    def print_current_labels(
        self, copies: int = 1, output_pdf_path: Path | None = None
    ) -> BatchResult:
        if not self.generated_labels:
            raise ValueError("Nothing to print - generate labels first")

        warehouse_prefix = self._generated_warehouse
        if len(self.generated_codes) > 1:
            description = f"{self.generated_codes[0]}..{self.generated_codes[-1]}"
        else:
            description = self.generated_codes[0]

        return print_batch(
            self.generated_labels,
            self._generated_preset,
            self._settings,
            mode="positions",
            warehouse_prefix=warehouse_prefix,
            description=description,
            copies=copies,
            output_pdf_path=output_pdf_path,
        )
