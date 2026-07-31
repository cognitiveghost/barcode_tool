import pytest
from PIL import Image

from app.core.label_renderer import (
    font_size_for_height,
    mm_to_px,
    render_inventory_label,
    render_label,
)


def test_mm_to_px_at_203_dpi():
    assert mm_to_px(25.4, dpi=203) == 203


def test_font_size_scales_with_label_height():
    assert font_size_for_height(1198) > font_size_for_height(304) > font_size_for_height(100)


def test_render_label_returns_image_of_expected_size():
    img = render_label("C001H029A", "H029A", width_mm=68, height_mm=38, dpi=203)
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(68, 203), mm_to_px(38, 203))


def test_render_label_visible_text_differs_from_barcode_data_changes_output():
    img_with_prefix_text = render_label("C001H029A", "C001H029A", width_mm=68, height_mm=38)
    img_without_prefix_text = render_label("C001H029A", "H029A", width_mm=68, height_mm=38)
    assert img_with_prefix_text.tobytes() != img_without_prefix_text.tobytes()


def test_render_inventory_label_returns_image_of_expected_size():
    img = render_inventory_label("SKU1", "Widget\nBatch 4471", "C001H011A", width_mm=68, height_mm=38, dpi=203)
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(68, 203), mm_to_px(38, 203))


def test_render_inventory_label_changes_with_sku_data():
    img_a = render_inventory_label("SKU1", "Widget", "C001H011A", width_mm=68, height_mm=38)
    img_b = render_inventory_label("SKU2", "Widget", "C001H011A", width_mm=68, height_mm=38)
    assert img_a.tobytes() != img_b.tobytes()


def test_render_inventory_label_changes_with_position_data():
    img_a = render_inventory_label("SKU1", "Widget", "C001H011A", width_mm=68, height_mm=38)
    img_b = render_inventory_label("SKU1", "Widget", "C001H099Z", width_mm=68, height_mm=38)
    assert img_a.tobytes() != img_b.tobytes()


def test_render_inventory_label_changes_with_text():
    img_a = render_inventory_label("SKU1", "Widget", "C001H011A", width_mm=68, height_mm=38)
    img_b = render_inventory_label("SKU1", "Gadget", "C001H011A", width_mm=68, height_mm=38)
    assert img_a.tobytes() != img_b.tobytes()


@pytest.mark.parametrize(
    ("width_mm", "height_mm"),
    [(100, 150), (68, 38), (80, 80)],
)
def test_render_inventory_label_composes_at_all_built_in_sizes(width_mm, height_mm):
    img = render_inventory_label(
        "SKU1", "Widget\nBatch 4471", "C001H011A", width_mm=width_mm, height_mm=height_mm
    )
    assert img.size == (mm_to_px(width_mm), mm_to_px(height_mm))
