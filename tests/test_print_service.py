from PIL import Image
from PySide6.QtGui import QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from app.core.print_service import _page_orientation, print_labels


def _app():
    return QApplication.instance() or QApplication([])


def test_print_labels_writes_pdf_with_expected_page_count(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white") for _ in range(3)]
    output_path = tmp_path / "labels.pdf"

    print_labels(images, width_mm=68, height_mm=38, output_pdf_path=output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_page_orientation_landscape_for_wide_size():
    assert _page_orientation(150, 100) == QPageLayout.Orientation.Landscape


def test_page_orientation_portrait_for_tall_size():
    assert _page_orientation(100, 150) == QPageLayout.Orientation.Portrait


def test_page_orientation_portrait_for_square_size():
    assert _page_orientation(80, 80) == QPageLayout.Orientation.Portrait


def test_print_labels_applies_the_computed_page_orientation(monkeypatch, tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    output_path = tmp_path / "labels.pdf"
    seen = []
    original = QPrinter.setPageOrientation

    def _spy(self, orientation):
        seen.append(orientation)
        return original(self, orientation)

    monkeypatch.setattr(QPrinter, "setPageOrientation", _spy)

    print_labels(images, width_mm=150, height_mm=100, output_pdf_path=output_path)

    assert seen == [QPageLayout.Orientation.Landscape]
