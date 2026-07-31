from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrinter


def print_labels(
    images: list[Image.Image],
    width_mm: float,
    height_mm: float,
    printer_name: str | None = None,
    output_pdf_path: Path | None = None,
) -> None:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)

    if output_pdf_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_pdf_path))
    elif printer_name:
        printer.setPrinterName(printer_name)

    painter = QPainter(printer)
    for index, image in enumerate(images):
        if index > 0:
            printer.newPage()
        pixmap = QPixmap.fromImage(ImageQt(image))
        target = painter.viewport()
        painter.drawPixmap(target, pixmap, pixmap.rect())
    painter.end()
