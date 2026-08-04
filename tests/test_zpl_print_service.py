import sys
import types

from PIL import Image

from app.core.zpl_print_service import (
    image_to_zpl,
    print_labels_zpl,
    send_raw_linux,
    send_raw_windows,
    windows_print_errors,
)


def test_image_to_zpl_returns_a_complete_zpl_block():
    image = Image.new("RGB", (100, 100), "white")

    zpl = image_to_zpl(image)

    assert zpl.startswith("^XA")
    assert zpl.rstrip().endswith("^XZ")


def test_image_to_zpl_prints_black_content_as_set_bits():
    # ZPL's ^GFA graphic field treats a set bit as a printed (black) dot.
    # PIL's mode "1" does the opposite (a set bit is white), so a fully
    # black source image must come out as all-ones graphic-field data, not
    # all-zeros - otherwise every print comes out with colors swapped.
    black = Image.new("L", (16, 8), 0).convert("1")

    zpl = image_to_zpl(black)

    assert "GFA,32,16,2,ffffffffffffffffffffffffffffffff" in zpl


def test_image_to_zpl_declares_print_width_and_label_length():
    # Without ^PW/^LL the printer falls back to whatever label size it last
    # had calibrated, which - unless it happens to match this image -
    # prints misaligned or rotated-looking output.
    image = Image.new("RGB", (200, 120), "white")

    zpl = image_to_zpl(image)

    assert "^PW200" in zpl
    assert "^LL120" in zpl


def test_image_to_zpl_rotate_swaps_print_width_and_label_length():
    # Raw ZPL has no printer driver to reconcile a landscape-designed
    # template against a portrait-mounted label roll - the roll's physical
    # (fixed) width becomes whichever axis the printer receives as ^PW.
    # rotate=True is the operator's way of telling us the roll is mounted
    # 90 degrees from how the template was designed, so content must be
    # turned to match, not just relabelled.
    image = Image.new("RGB", (200, 120), "white")

    zpl = image_to_zpl(image, rotate=True)

    assert "^PW120" in zpl
    assert "^LL200" in zpl


def test_image_to_zpl_rotate_false_by_default():
    image = Image.new("RGB", (200, 120), "white")

    zpl = image_to_zpl(image)

    assert "^PW200" in zpl
    assert "^LL120" in zpl


def test_print_labels_zpl_passes_rotate_through_to_image_to_zpl(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "app.core.zpl_print_service.image_to_zpl",
        lambda image, rotate=False: seen.append(rotate) or "^XA^XZ",
    )
    monkeypatch.setattr(
        "app.core.zpl_print_service.send_raw_linux", lambda target, data: None
    )
    images = [Image.new("RGB", (10, 10), "white")]

    print_labels_zpl(images, "/dev/usb/lp0", rotate=True)

    assert seen == [True]


def test_send_raw_linux_writes_bytes_to_the_device_path(tmp_path):
    device_path = tmp_path / "lp0"

    send_raw_linux(str(device_path), b"^XA^XZ")

    assert device_path.read_bytes() == b"^XA^XZ"


def test_windows_print_errors_empty_when_pywintypes_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pywintypes", None)

    assert windows_print_errors() == ()


def test_windows_print_errors_includes_pywintypes_error_when_available(monkeypatch):
    fake_pywintypes = types.ModuleType("pywintypes")
    fake_pywintypes.error = type("error", (Exception,), {})
    monkeypatch.setitem(sys.modules, "pywintypes", fake_pywintypes)

    assert windows_print_errors() == (fake_pywintypes.error,)


def test_send_raw_windows_opens_a_raw_job_and_writes_bytes(monkeypatch):
    calls = []

    def _open_printer(name):
        calls.append(("OpenPrinter", name))
        return "HANDLE"

    def _start_doc_printer(handle, level, doc_info):
        calls.append(("StartDocPrinter", handle, level, doc_info))

    def _start_page_printer(handle):
        calls.append(("StartPagePrinter", handle))

    def _write_printer(handle, data):
        calls.append(("WritePrinter", handle, data))

    def _end_page_printer(handle):
        calls.append(("EndPagePrinter", handle))

    def _end_doc_printer(handle):
        calls.append(("EndDocPrinter", handle))

    def _close_printer(handle):
        calls.append(("ClosePrinter", handle))

    fake_win32print = types.ModuleType("win32print")
    fake_win32print.OpenPrinter = _open_printer
    fake_win32print.StartDocPrinter = _start_doc_printer
    fake_win32print.StartPagePrinter = _start_page_printer
    fake_win32print.WritePrinter = _write_printer
    fake_win32print.EndPagePrinter = _end_page_printer
    fake_win32print.EndDocPrinter = _end_doc_printer
    fake_win32print.ClosePrinter = _close_printer
    monkeypatch.setitem(sys.modules, "win32print", fake_win32print)

    send_raw_windows("ZPL-RAW-Printer", b"^XA^XZ")

    call_names = [call[0] for call in calls]
    assert call_names == [
        "OpenPrinter",
        "StartDocPrinter",
        "StartPagePrinter",
        "WritePrinter",
        "EndPagePrinter",
        "EndDocPrinter",
        "ClosePrinter",
    ]
    assert calls[0][1] == "ZPL-RAW-Printer"
    assert calls[1][3] == ("ZPL label", "", "RAW")
    assert calls[3][2] == b"^XA^XZ"


def test_print_labels_zpl_dispatches_to_linux_transport(monkeypatch):
    monkeypatch.setattr("app.core.zpl_print_service.sys.platform", "linux")
    sent = []
    monkeypatch.setattr(
        "app.core.zpl_print_service.send_raw_linux",
        lambda target, data: sent.append((target, data)),
    )
    monkeypatch.setattr(
        "app.core.zpl_print_service.image_to_zpl", lambda image, rotate=False: "^XA^XZ"
    )
    images = [Image.new("RGB", (10, 10), "white"), Image.new("RGB", (10, 10), "white")]

    print_labels_zpl(images, "/dev/usb/lp0")

    assert sent == [("/dev/usb/lp0", b"^XA^XZ"), ("/dev/usb/lp0", b"^XA^XZ")]


def test_print_labels_zpl_dispatches_to_windows_transport(monkeypatch):
    monkeypatch.setattr("app.core.zpl_print_service.sys.platform", "win32")
    sent = []
    monkeypatch.setattr(
        "app.core.zpl_print_service.send_raw_windows",
        lambda target, data: sent.append((target, data)),
    )
    monkeypatch.setattr(
        "app.core.zpl_print_service.image_to_zpl", lambda image, rotate=False: "^XA^XZ"
    )
    images = [Image.new("RGB", (10, 10), "white")]

    print_labels_zpl(images, "ZPL-RAW-Printer")

    assert sent == [("ZPL-RAW-Printer", b"^XA^XZ")]
