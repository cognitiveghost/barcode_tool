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


_MARGIN_MM = 5


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

    margin = mm_to_px(_MARGIN_MM, dpi)
    content_x0, content_y0 = margin, margin
    content_width = width_px - 2 * margin
    content_height = height_px - 2 * margin

    primary_size = round(content_height * 0.42)   # SKU / Position QR side
    secondary_size = round(content_height * 0.30)  # Expiry / Batch QR side
    gap = max(2, round(content_height * 0.02))

    bold_font = load_font(font_size_for_height(primary_size), bold=True)
    caption_font = load_font(font_size_for_height(secondary_size))

    left_x = content_x0
    right_x = content_x0 + content_width - secondary_size
    divider_left = content_x0 + primary_size
    divider_right = right_x

    # SKU: top of the left column, bold caption below it.
    sku_qr = generate_qr_image(sku).resize((primary_size, primary_size))
    canvas.paste(sku_qr, (left_x, content_y0))
    draw.text((left_x, content_y0 + primary_size + gap), sku, fill="black", font=bold_font)

    # Position: bottom of the left column, bold caption above it.
    position_qr_y = content_y0 + content_height - primary_size
    position_bbox = draw.textbbox((0, 0), position_code, font=bold_font)
    position_caption_height = position_bbox[3] - position_bbox[1]
    draw.text(
        (left_x, position_qr_y - position_caption_height - gap),
        position_code,
        fill="black",
        font=bold_font,
    )
    position_qr = generate_qr_image(position_data).resize((primary_size, primary_size))
    canvas.paste(position_qr, (left_x, position_qr_y))

    # Expiry: top of the right column, caption below it. Omitted if blank.
    if expiry:
        expiry_qr = generate_qr_image(expiry).resize((secondary_size, secondary_size))
        canvas.paste(expiry_qr, (right_x, content_y0))
        draw.text(
            (right_x + gap, content_y0 + secondary_size + gap),
            expiry,
            fill="black",
            font=caption_font,
        )

    # Batch: bottom of the right column, caption above it. Omitted if blank.
    if batch:
        batch_qr_y = content_y0 + content_height - secondary_size
        batch_bbox = draw.textbbox((0, 0), batch, font=caption_font)
        batch_caption_height = batch_bbox[3] - batch_bbox[1]
        draw.text(
            (right_x + gap, batch_qr_y - batch_caption_height - gap),
            batch,
            fill="black",
            font=caption_font,
        )
        batch_qr = generate_qr_image(batch).resize((secondary_size, secondary_size))
        canvas.paste(batch_qr, (right_x, batch_qr_y))

    # Divider lines: two verticals for the full content height, one
    # horizontal splitting the middle column only (not the QR columns).
    divider_width = 3
    mid_split_y = content_y0 + content_height // 2
    draw.line(
        [(divider_left, content_y0), (divider_left, content_y0 + content_height)],
        fill="black", width=divider_width,
    )
    draw.line(
        [(divider_right, content_y0), (divider_right, content_y0 + content_height)],
        fill="black", width=divider_width,
    )
    draw.line(
        [(divider_left, mid_split_y), (divider_right, mid_split_y)],
        fill="black", width=divider_width,
    )

    # Middle column, top half: plain readable field list.
    middle_x = divider_left + gap * 2
    middle_right = divider_right - gap * 2
    text_lines: list[tuple[str, object]] = []
    if name:
        text_lines.append((name, bold_font))
    for label, value in (
        ("Expiry", expiry),
        ("Batch", batch),
        ("SKU", sku),
        ("Position", position_code),
    ):
        if value:
            text_lines.append((f"{label}: {value}", caption_font))

    line_y = content_y0 + gap
    for line, font in text_lines:
        draw.text((middle_x, line_y), line, fill="black", font=font)
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_y += (line_bbox[3] - line_bbox[1]) + gap

    # Middle column, bottom half: Client name, centered.
    if client:
        client_bbox = draw.textbbox((0, 0), client, font=caption_font)
        client_width = client_bbox[2] - client_bbox[0]
        client_x = middle_x + max(0, (middle_right - middle_x - client_width) // 2)
        draw.text((client_x, mid_split_y + gap * 2), client, fill="black", font=caption_font)

    # Generation date: small text, bottom-right corner of the middle
    # column's bottom half (not the label's absolute corner, so it never
    # collides with the Batch QR in the right column).
    date_font = load_font(max(8, font_size_for_height(secondary_size) - 2))
    date_bbox = draw.textbbox((0, 0), generated_date, font=date_font)
    draw.text(
        (middle_right - date_bbox[2] - 2, content_y0 + content_height - date_bbox[3] - 2),
        generated_date,
        fill="black",
        font=date_font,
    )

    return canvas
