from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from zebrafy import ZebrafyImage


def image_to_zpl(image: Image.Image) -> str:
    # invert=True: PIL's mode "1" packs a set bit as white, but ZPL's ^GFA
    # graphic field treats a set bit as a printed (black) dot - without this
    # every raw ZPL print comes out with barcode and background swapped.
    field = ZebrafyImage(image, invert=True, complete_zpl=False).to_zpl()
    # ^PW/^LL tell the printer this job's exact width/length in dots (1
    # image pixel = 1 dot, see send_to_printer). Without them the printer
    # falls back to whatever label size it last had configured/calibrated,
    # which - when it doesn't match this image - prints misaligned or
    # rotated-looking output and can trigger the printer's own media
    # recalibration.
    return f"^XA\n^PW{image.width}\n^LL{image.height}\n{field}\n^XZ\n"


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


def print_labels_zpl(images: list[Image.Image], target: str) -> None:
    for image in images:
        data = image_to_zpl(image).encode("ascii")
        if sys.platform == "win32":
            send_raw_windows(target, data)
        else:
            send_raw_linux(target, data)


def windows_print_errors() -> tuple[type[Exception], ...]:
    """Exception types raised by win32print, for UI-layer except clauses."""
    try:
        import pywintypes
    except ImportError:
        return ()
    return (pywintypes.error,)
