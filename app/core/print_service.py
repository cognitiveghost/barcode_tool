from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrinter


def _page_orientation(width_mm: float, height_mm: float) -> QPageLayout.Orientation:
    if width_mm > height_mm:
        return QPageLayout.Orientation.Landscape
    return QPageLayout.Orientation.Portrait


def print_labels(
    images: list[Image.Image],
    width_mm: float,
    height_mm: float,
    printer_name: str | None = None,
    output_pdf_path: Path | None = None,
) -> None:
    orientation = _page_orientation(width_mm, height_mm)
    # QPageSize's custom-size definition is always canonical/portrait (the
    # smaller side first); setPageOrientation does the actual landscape
    # rotation. Passing an already-wide QSizeF here *and* orientation makes
    # Qt apply the flip twice, silently handing the page back as portrait.
    canonical_size = (
        QSizeF(height_mm, width_mm)
        if orientation == QPageLayout.Orientation.Landscape
        else QSizeF(width_mm, height_mm)
    )
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(canonical_size, QPageSize.Unit.Millimeter))
    printer.setPageOrientation(orientation)
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
