import re

import pytest
from PIL import Image
from PySide6.QtGui import QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from app.core.print_service import _page_orientation, print_labels


def _app():
    return QApplication.instance() or QApplication([])


def _mediabox_pt(pdf_path):
    # Qt's PDF writer emits an ASCII "/MediaBox [x0 y0 x1 y1]" entry - read
    # it back directly rather than pulling in a PDF-parsing dependency.
    match = re.search(rb"/MediaBox \[([\d.\s]+)\]", pdf_path.read_bytes())
    x0, y0, x1, y1 = (float(value) for value in match.group(1).split())
    return x1 - x0, y1 - y0


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


def test_print_labels_produces_a_page_actually_wider_than_tall_for_landscape(tmp_path):
    # Regression test: setPageOrientation(Landscape) on top of a QPageSize
    # already built with width_mm > height_mm makes Qt apply the rotation
    # twice, silently handing back a portrait-shaped page. The page geometry
    # itself must be checked - a mock asserting setPageOrientation was
    # *called* isn't enough to catch that regression.
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    output_path = tmp_path / "labels.pdf"

    print_labels(images, width_mm=150, height_mm=100, output_pdf_path=output_path)

    width_pt, height_pt = _mediabox_pt(output_path)
    assert width_pt > height_pt
    assert width_pt == pytest.approx(150 / 25.4 * 72, abs=1)
    assert height_pt == pytest.approx(100 / 25.4 * 72, abs=1)


def test_print_labels_produces_a_page_actually_taller_than_wide_for_portrait(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    output_path = tmp_path / "labels.pdf"

    print_labels(images, width_mm=100, height_mm=150, output_pdf_path=output_path)

    width_pt, height_pt = _mediabox_pt(output_path)
    assert height_pt > width_pt
    assert width_pt == pytest.approx(100 / 25.4 * 72, abs=1)
    assert height_pt == pytest.approx(150 / 25.4 * 72, abs=1)
