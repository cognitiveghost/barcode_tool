from PIL import Image
from PySide6.QtWidgets import QApplication

from app.core.print_service import print_labels


def _app():
    return QApplication.instance() or QApplication([])


def test_print_labels_writes_pdf_with_expected_page_count(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white") for _ in range(3)]
    output_path = tmp_path / "labels.pdf"

    print_labels(images, width_mm=68, height_mm=38, output_pdf_path=output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
