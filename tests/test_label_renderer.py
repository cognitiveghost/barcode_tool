from PIL import Image, ImageChops, ImageDraw

from app.core.fonts import load_font
from app.core.label_renderer import (
    _fit_text,
    apply_orientation,
    font_size_for_height,
    mm_to_px,
    render_inventory_label,
    render_label,
)


def test_mm_to_px_at_203_dpi():
    assert mm_to_px(25.4, dpi=203) == 203


def test_font_size_scales_with_label_height():
    assert font_size_for_height(1198) > font_size_for_height(304) > font_size_for_height(100)


def test_apply_orientation_landscape_swaps_a_tall_size():
    assert apply_orientation(68, 100, "Landscape") == (100, 68)


def test_apply_orientation_portrait_swaps_a_wide_size():
    assert apply_orientation(150, 100, "Portrait") == (100, 150)


def test_apply_orientation_landscape_is_noop_when_already_wide():
    assert apply_orientation(150, 100, "Landscape") == (150, 100)


def test_apply_orientation_portrait_is_noop_when_already_tall():
    assert apply_orientation(100, 150, "Portrait") == (100, 150)


def test_apply_orientation_square_is_noop_either_way():
    assert apply_orientation(80, 80, "Landscape") == (80, 80)
    assert apply_orientation(80, 80, "Portrait") == (80, 80)


def test_render_label_returns_image_of_expected_size():
    img = render_label("C001H029A", "H029A", width_mm=68, height_mm=38, dpi=203)
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(68, 203), mm_to_px(38, 203))


def test_render_label_visible_text_differs_from_barcode_data_changes_output():
    img_with_prefix_text = render_label("C001H029A", "C001H029A", width_mm=68, height_mm=38)
    img_without_prefix_text = render_label("C001H029A", "H029A", width_mm=68, height_mm=38)
    assert img_with_prefix_text.tobytes() != img_without_prefix_text.tobytes()


def test_render_label_renders_cyrillic_text_without_error():
    img = render_label("C001H029A", "Полка Н029А", width_mm=68, height_mm=38)
    assert isinstance(img, Image.Image)


def test_render_label_centers_content_vertically_on_a_tall_canvas():
    img = render_label("C001H029A", "H029A", width_mm=38, height_mm=90)
    # On a canvas much taller than the barcode+text block needs, centering
    # should leave roughly equal white margin above and below the content.
    # Checked empirically: pinned-to-top code gives top=8/bottom=497 here
    # (way off); centered code gives top=263/bottom=245 (close).
    bg = Image.new("RGB", img.size, "white")
    bbox = ImageChops.difference(img, bg).getbbox()
    top_margin = bbox[1]
    bottom_margin = img.height - bbox[3]
    assert abs(top_margin - bottom_margin) < img.height * 0.1


def test_render_inventory_label_returns_image_of_expected_size():
    img = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100, dpi=203,
    )
    assert isinstance(img, Image.Image)
    assert img.size == (mm_to_px(150, 203), mm_to_px(100, 203))


def test_render_inventory_label_omits_expiry_chip_when_expiry_empty():
    img_with = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    img_without = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    assert img_with.tobytes() != img_without.tobytes()


def test_render_inventory_label_omits_batch_chip_when_batch_empty():
    img_with = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    img_without = render_inventory_label(
        "SKU1", "Widget", "Acme", "", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    assert img_with.tobytes() != img_without.tobytes()


def test_render_inventory_label_renders_with_everything_optional_blank():
    img = render_inventory_label(
        "SKU1", "", "", "", "", "H011A", "C001H011A", "31072026",
        width_mm=150, height_mm=100,
    )
    assert isinstance(img, Image.Image)


def test_fit_text_returns_text_unchanged_when_it_already_fits():
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = load_font(20)
    assert _fit_text(draw, "abc", font, 1000) == "abc"


def test_fit_text_truncates_with_ellipsis_when_too_wide():
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = load_font(20)
    fitted = _fit_text(draw, "a" * 100, font, 100)
    assert fitted != "a" * 100
    assert fitted.endswith("…")
    bbox = draw.textbbox((0, 0), fitted, font=font)
    assert bbox[2] - bbox[0] <= 100


def test_render_inventory_label_long_name_does_not_crash_and_changes_output():
    short = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    long_fields = render_inventory_label(
        "SKU-" + "1" * 60,
        "A very long product name that would overflow the label" * 3,
        "A very long client name" * 3,
        "B" * 40,
        "2027-03",
        "H011A",
        "C001H011A",
        "31072026",
        width_mm=150,
        height_mm=100,
    )
    assert isinstance(long_fields, Image.Image)
    assert long_fields.size == short.size
    assert long_fields.tobytes() != short.tobytes()


def test_render_inventory_label_position_qr_uses_prefixed_data():
    img_a = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C001H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    img_b = render_inventory_label(
        "SKU1", "Widget", "Acme", "4471", "2027-03", "H011A", "C002H011A",
        "31072026", width_mm=150, height_mm=100,
    )
    assert img_a.tobytes() != img_b.tobytes()
