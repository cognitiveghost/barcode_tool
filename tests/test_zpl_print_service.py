from PIL import Image

from app.core.zpl_print_service import image_to_zpl


def test_image_to_zpl_returns_a_complete_zpl_block():
    image = Image.new("RGB", (100, 100), "white")

    zpl = image_to_zpl(image)

    assert zpl.startswith("^XA")
    assert zpl.rstrip().endswith("^XZ")
