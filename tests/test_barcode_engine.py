from PIL import Image

from app.core.barcode_engine import generate_barcode_image


def test_generate_barcode_image_returns_image():
    img = generate_barcode_image("C001H029A")
    assert isinstance(img, Image.Image)
    assert img.width > 0
    assert img.height > 0


def test_different_data_produces_different_image():
    img_a = generate_barcode_image("C001H029A")
    img_b = generate_barcode_image("C001H030A")
    assert img_a.tobytes() != img_b.tobytes()
