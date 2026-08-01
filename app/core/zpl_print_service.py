from __future__ import annotations

from pathlib import Path

from PIL import Image
from zebrafy import ZebrafyImage


def image_to_zpl(image: Image.Image) -> str:
    return ZebrafyImage(image).to_zpl()


def send_raw_linux(device_path: str, data: bytes) -> None:
    Path(device_path).write_bytes(data)
