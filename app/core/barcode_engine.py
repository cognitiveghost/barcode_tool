from __future__ import annotations

import barcode
import qrcode
from barcode.writer import ImageWriter
from PIL import Image


def generate_barcode_image(data: str) -> Image.Image:
    code = barcode.get("code128", data, writer=ImageWriter())
    return code.render(writer_options={"write_text": False})


def generate_qr_image(data: str) -> Image.Image:
    return qrcode.make(data).get_image()
