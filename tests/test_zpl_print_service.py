from PIL import Image

from app.core.zpl_print_service import image_to_zpl, send_raw_linux


def test_image_to_zpl_returns_a_complete_zpl_block():
    image = Image.new("RGB", (100, 100), "white")

    zpl = image_to_zpl(image)

    assert zpl.startswith("^XA")
    assert zpl.rstrip().endswith("^XZ")


def test_send_raw_linux_writes_bytes_to_the_device_path(tmp_path):
    device_path = tmp_path / "lp0"

    send_raw_linux(str(device_path), b"^XA^XZ")

    assert device_path.read_bytes() == b"^XA^XZ"
