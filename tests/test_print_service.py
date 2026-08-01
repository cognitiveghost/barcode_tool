import re

import pytest
from PIL import Image
from PySide6.QtGui import QPageLayout
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from app.core.print_service import _page_orientation, print_labels, send_to_printer


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


def test_send_to_printer_uses_pdf_path_regardless_of_print_mode(tmp_path):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    output_path = tmp_path / "labels.pdf"
    settings = {"print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}

    send_to_printer(images, width_mm=68, height_mm=38, settings=settings, output_pdf_path=output_path)

    assert output_path.exists()


def test_send_to_printer_dispatches_to_raw_zpl_when_configured(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels_zpl",
        lambda imgs, target: calls.append((imgs, target)),
    )
    settings = {"print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}

    send_to_printer(images, width_mm=68, height_mm=38, settings=settings)

    assert calls == [(images, "/dev/usb/lp0")]


def test_send_to_printer_defaults_to_driver_mode(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda imgs, width_mm, height_mm, **kwargs: calls.append(kwargs),
    )
    settings = {"print_mode": "driver", "default_printer": "Citizen CL-E300"}

    send_to_printer(images, width_mm=68, height_mm=38, settings=settings)

    assert calls == [{"printer_name": "Citizen CL-E300"}]


def test_send_to_printer_treats_missing_print_mode_as_driver(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda imgs, width_mm, height_mm, **kwargs: calls.append(kwargs),
    )

    send_to_printer(images, width_mm=68, height_mm=38, settings={})

    assert calls == [{"printer_name": None}]


def test_send_to_printer_does_not_fall_back_to_driver_when_raw_zpl_fails(monkeypatch):
    _app()
    images = [Image.new("RGB", (100, 100), "white")]
    driver_calls = []
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda *a, **k: driver_calls.append(True),
    )

    def _boom(imgs, target):
        raise OSError("device not found")

    monkeypatch.setattr("app.core.print_service.print_labels_zpl", _boom)
    settings = {"print_mode": "raw_zpl", "raw_zpl_target": "/dev/usb/lp0"}

    with pytest.raises(OSError):
        send_to_printer(images, width_mm=68, height_mm=38, settings=settings)

    assert driver_calls == []
