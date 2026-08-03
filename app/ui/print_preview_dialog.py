from __future__ import annotations

from pathlib import Path
from typing import Callable

from barcode.errors import BarcodeError
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.print_batch import BatchResult
from app.core.print_service import printer_display
from app.core.template_renderer import TemplatePreset
from app.core.zpl_print_service import windows_print_errors

PREVIEW_BOX_SIZE = 350


class PrintPreviewDialog(QDialog):
    def __init__(
        self,
        count: int,
        render_page: Callable[[int], Image.Image],
        preset: TemplatePreset,
        settings: dict,
        warehouse_display: str,
        on_confirm: Callable[[int, Path | None], BatchResult],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Print preview")
        self._count = count
        self._render_page = render_page
        self._on_confirm = on_confirm
        self._page_index = 0

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(PREVIEW_BOX_SIZE, PREVIEW_BOX_SIZE)

        self._prev_button = QPushButton("<")
        self._prev_button.clicked.connect(self._show_previous_page)
        self._next_button = QPushButton(">")
        self._next_button.clicked.connect(self._show_next_page)
        self._page_indicator = QLabel()

        pager = QHBoxLayout()
        pager.addStretch()
        pager.addWidget(self._prev_button)
        pager.addWidget(self._page_indicator)
        pager.addWidget(self._next_button)
        pager.addStretch()

        printer = printer_display(settings)
        summary = QLabel(
            f"{count} label{'s' if count != 1 else ''} - "
            f"{preset.width_mm:g}x{preset.height_mm:g}mm - "
            f"Template: {preset.name} - Warehouse: {warehouse_display} - "
            f"Printer: {printer}"
        )
        summary.setWordWrap(True)
        self._summary_label = summary

        self._copies_spin = QSpinBox()
        self._copies_spin.setRange(1, 999)
        self._copies_spin.setValue(1)

        print_button = QPushButton("Print")
        print_button.clicked.connect(self._on_print_clicked)
        save_button = QPushButton("Save as PDF...")
        save_button.clicked.connect(self._on_save_as_pdf_clicked)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Copies:"))
        actions.addWidget(self._copies_spin)
        actions.addStretch()
        actions.addWidget(print_button)
        actions.addWidget(save_button)
        actions.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(self.preview_label)
        layout.addLayout(pager)
        layout.addLayout(actions)

        self._show_page(0)

    def _show_page(self, index: int) -> None:
        image = self._render_page(index)
        self._page_index = index
        pixmap = QPixmap.fromImage(ImageQt(image)).scaled(
            PREVIEW_BOX_SIZE,
            PREVIEW_BOX_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)
        self._page_indicator.setText(f"{index + 1} / {self._count}")
        self._prev_button.setEnabled(index > 0)
        self._next_button.setEnabled(index < self._count - 1)

    def _show_previous_page(self) -> None:
        if self._page_index > 0:
            self._show_page_safely(self._page_index - 1)

    def _show_next_page(self) -> None:
        if self._page_index < self._count - 1:
            self._show_page_safely(self._page_index + 1)

    def _show_page_safely(self, index: int) -> None:
        try:
            self._show_page(index)
        except (ValueError, OSError, BarcodeError) as error:
            QMessageBox.warning(self, "Preview failed", str(error))

    def _on_print_clicked(self) -> None:
        self._confirm(self._copies_spin.value(), None)

    def _on_save_as_pdf_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save as PDF", filter="PDF files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self._confirm(1, Path(path))

    def _confirm(self, copies: int, output_pdf_path: Path | None) -> None:
        try:
            result = self._on_confirm(copies, output_pdf_path)
        except (ValueError, OSError, *windows_print_errors()) as error:
            QMessageBox.warning(self, "Print failed", str(error))
            return
        if result.warnings:
            QMessageBox.warning(self, "Printed with warnings", "\n\n".join(result.warnings))
        self.accept()
