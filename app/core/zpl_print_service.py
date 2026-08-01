from __future__ import annotations

from pathlib import Path

from PIL import Image
from zebrafy import ZebrafyImage


def image_to_zpl(image: Image.Image) -> str:
    return ZebrafyImage(image).to_zpl()


def send_raw_linux(device_path: str, data: bytes) -> None:
    Path(device_path).write_bytes(data)


def send_raw_windows(printer_name: str, data: bytes) -> None:
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ("ZPL label", "", "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
