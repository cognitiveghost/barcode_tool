from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from app.core.barcode_engine import generate_barcode_image, generate_qr_image
from app.core.fonts import load_font

MM_PER_INCH = 25.4


def mm_to_px(mm: float, dpi: int = 203) -> int:
    return round(mm / MM_PER_INCH * dpi)


def font_size_for_height(height_px: int) -> int:
    return max(10, min(60, round(height_px * 0.08)))


def apply_orientation(width_mm: float, height_mm: float, orientation: str) -> tuple[float, float]:
    if orientation == "Portrait" and width_mm > height_mm:
        return height_mm, width_mm
    if orientation == "Landscape" and height_mm > width_mm:
        return height_mm, width_mm
    return width_mm, height_mm


def render_label(
    barcode_data: str,
    visible_text: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)

    canvas = Image.new("RGB", (width_px, height_px), "white")

    barcode_img = generate_barcode_image(barcode_data)
    max_barcode_height = round(height_px * 0.7)
    scale = min(width_px / barcode_img.width, max_barcode_height / barcode_img.height, 1)
    barcode_img = barcode_img.resize(
        (round(barcode_img.width * scale), round(barcode_img.height * scale))
    )

    draw = ImageDraw.Draw(canvas)
    font = load_font(font_size_for_height(height_px))
    text_bbox = draw.textbbox((0, 0), visible_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    gap = 2
    block_height = barcode_img.height + gap + text_height
    block_top = max((height_px - block_height) // 2, 0)

    barcode_x = (width_px - barcode_img.width) // 2
    canvas.paste(barcode_img, (barcode_x, block_top))

    text_x = max((width_px - text_width) // 2, 0)
    text_y = block_top + barcode_img.height + gap
    draw.text((text_x, text_y), visible_text, fill="black", font=font)

    return canvas


def render_inventory_label(
    sku_data: str,
    text: str,
    position_data: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)
    canvas = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(canvas)

    top_height = round(height_px * 0.7)
    sku_qr = generate_qr_image(sku_data)
    sku_size = max(1, min(top_height - 4, width_px // 2))
    sku_qr = sku_qr.resize((sku_size, sku_size))
    canvas.paste(sku_qr, (0, 0))

    text_font = ImageFont.load_default(size=font_size_for_height(top_height))
    draw.multiline_text((sku_size + 6, 2), text, fill="black", font=text_font)

    draw.line([(0, top_height), (width_px, top_height)], fill="black", width=1)

    bottom_height = height_px - top_height
    position_qr = generate_qr_image(position_data)
    position_size = max(1, min(bottom_height - 4, width_px // 4))
    position_qr = position_qr.resize((position_size, position_size))
    position_y = top_height + max(0, (bottom_height - position_size) // 2)
    canvas.paste(position_qr, (4, position_y))

    caption_font = ImageFont.load_default(size=font_size_for_height(bottom_height))
    draw.text((position_size + 10, top_height + 4), "shelf position", fill="black", font=caption_font)

    return canvas
