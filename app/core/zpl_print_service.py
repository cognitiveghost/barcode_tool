from __future__ import annotations

from PIL import Image
from zebrafy import ZebrafyImage


def image_to_zpl(image: Image.Image) -> str:
    return ZebrafyImage(image).to_zpl()
