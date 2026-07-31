from __future__ import annotations

from PIL import Image, ImageDraw

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


_MIN_MIDDLE_WIDTH_MM = 10


def render_inventory_label(
    sku: str,
    name: str,
    client: str,
    batch: str,
    expiry: str,
    position_code: str,
    position_data: str,
    generated_date: str,
    width_mm: float,
    height_mm: float,
    dpi: int = 203,
) -> Image.Image:
    width_px = mm_to_px(width_mm, dpi)
    height_px = mm_to_px(height_mm, dpi)
    canvas = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(canvas)

    short_side = min(width_px, height_px)
    sku_size = max(1, round(short_side * 0.5))
    secondary_size = max(1, round(short_side * 0.25))
    min_middle_width_px = mm_to_px(_MIN_MIDDLE_WIDTH_MM, dpi)

    secondary_chips = [value for value in (expiry, batch) if value]
    if secondary_chips and (width_px - sku_size - secondary_size) < min_middle_width_px:
        secondary_chips = []

    bold_size = font_size_for_height(sku_size)
    caption_size = font_size_for_height(secondary_size)
    bold_font = load_font(bold_size, bold=True)
    caption_font = load_font(caption_size)

    # SKU: top-left corner, bold caption underneath.
    sku_qr = generate_qr_image(sku).resize((sku_size, sku_size))
    canvas.paste(sku_qr, (0, 0))
    draw.text((0, sku_size + 2), sku, fill="black", font=bold_font)

    # Expiry then Batch: stacked top-right corner, each captioned underneath.
    right_x = width_px - secondary_size
    chip_y = 0
    for value in secondary_chips:
        chip_qr = generate_qr_image(value).resize((secondary_size, secondary_size))
        canvas.paste(chip_qr, (right_x, chip_y))
        draw.text((right_x, chip_y + secondary_size + 2), value, fill="black", font=caption_font)
        chip_y += secondary_size + caption_size + 6

    # Position: bottom-left corner, bold caption beside it (to the right).
    position_y = height_px - secondary_size
    position_qr = generate_qr_image(position_data).resize((secondary_size, secondary_size))
    canvas.paste(position_qr, (0, position_y))
    caption_bbox = draw.textbbox((0, 0), position_code, font=bold_font)
    caption_height = caption_bbox[3] - caption_bbox[1]
    draw.text(
        (secondary_size + 6, position_y + max(0, (secondary_size - caption_height) // 2)),
        position_code,
        fill="black",
        font=bold_font,
    )

    # Middle column: Product name / Client / Exp+Batch / SKU, from upper-middle.
    middle_x = sku_size + 6
    exp_batch_parts = [
        part
        for part in (f"Exp {expiry}" if expiry else "", f"Batch {batch}" if batch else "")
        if part
    ]
    text_lines = [line for line in (name, client, " · ".join(exp_batch_parts), sku) if line]
    line_y = 4
    for line in text_lines:
        draw.text((middle_x, line_y), line, fill="black", font=caption_font)
        line_bbox = draw.textbbox((0, 0), line, font=caption_font)
        line_y += (line_bbox[3] - line_bbox[1]) + 4

    # Generation date: small, bottom-right corner.
    # Positioned from the anchor-relative bbox edges (date_bbox[2]/[3]), not a
    # width/height computed from bbox[0]/[1] - those aren't 0 for every font,
    # and subtracting a plain height from the canvas edge let the glyphs'
    # true bottom edge run past height_px (clipped descenders on real fonts).
    date_font = load_font(max(8, caption_size - 2))
    date_bbox = draw.textbbox((0, 0), generated_date, font=date_font)
    draw.text(
        (width_px - date_bbox[2] - 2, height_px - date_bbox[3] - 2),
        generated_date,
        fill="black",
        font=date_font,
    )

    return canvas
