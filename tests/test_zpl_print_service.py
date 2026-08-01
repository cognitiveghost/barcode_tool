import sys
import types

from PIL import Image

from app.core.zpl_print_service import (
    image_to_zpl,
    print_labels_zpl,
    send_raw_linux,
    send_raw_windows,
)


def test_image_to_zpl_returns_a_complete_zpl_block():
    image = Image.new("RGB", (100, 100), "white")

    zpl = image_to_zpl(image)

    assert zpl.startswith("^XA")
    assert zpl.rstrip().endswith("^XZ")


def test_send_raw_linux_writes_bytes_to_the_device_path(tmp_path):
    device_path = tmp_path / "lp0"

    send_raw_linux(str(device_path), b"^XA^XZ")

    assert device_path.read_bytes() == b"^XA^XZ"


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
        "app.core.zpl_print_service.image_to_zpl", lambda image: "^XA^XZ"
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
        "app.core.zpl_print_service.image_to_zpl", lambda image: "^XA^XZ"
    )
    images = [Image.new("RGB", (10, 10), "white")]

    print_labels_zpl(images, "ZPL-RAW-Printer")

    assert sent == [("ZPL-RAW-Printer", b"^XA^XZ")]
