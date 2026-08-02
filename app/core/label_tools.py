"""Helpers exposed to blabel templates as ``label_tools``.

Wraps blabel's own helpers so codes come out as vectors instead of small
bitmaps - a thermal head at 203-300 dpi turns a resampled PNG into fuzzy
module edges, while vector paths rasterise exactly on the target grid.
"""

from __future__ import annotations

import base64
from io import BytesIO

import qrcode
import qrcode.image.svg
from blabel.label_tools import barcode as _blabel_barcode
from blabel.label_tools import (  # noqa: F401 - re-exported for templates
    datamatrix,
    hiro_square,
    now,
    pil_to_html_imgdata,
    wrap,
)

_SVG_DATA_URI = "data:image/svg+xml;charset=utf-8;base64,"

# JetBrains Mono (and any monospace) advances 0.6em per character.
_MONO_CHAR_WIDTH = 0.6

# ISO/IEC 18004 6.3.7 asks for 4 clear modules around a QR. We draw 2. The
# quiet zone is rendered inside the CSS box, so going to 4 costs ~28% of the
# symbol's printed size, and the codes were verified to read reliably at 2 on
# the scanner these labels are actually used with. What mattered was not
# drawing them edge to edge, which put them against the black chip bars.
# ponytail: below spec on purpose - if a future scanner misreads column 3,
# raise this to 4 and grow the .qr-* boxes to keep the symbol the same size.
_QR_QUIET_MODULES = 2

# ISO/IEC 15417 quiet zone for Code 128 is 10x the narrow element width.
# python-barcode expresses both in mm, so the ratio has to be applied by
# hand or a template overriding module_width silently drops below spec.
_LINEAR_QUIET_MODULES = 10
_DEFAULT_MODULE_WIDTH_MM = 0.2


def _svg_data_uri(svg: bytes) -> str:
    return _SVG_DATA_URI + base64.b64encode(svg).decode()


def qr_code(data, border: int = _QR_QUIET_MODULES, **qr_code_params) -> str:
    """Return a vector QR code as an ``<img src=...>`` data URI.

    The quiet zone is inside the SVG on purpose: the CSS box is what the
    layout reserves, so a code drawn edge to edge ends up with a chip or a
    rule right against its finder patterns.
    """
    qr = qrcode.QRCode(
        border=border, image_factory=qrcode.image.svg.SvgPathImage, **qr_code_params
    )
    qr.add_data(str(data))
    buffer = BytesIO()
    qr.make_image().save(buffer)
    return _svg_data_uri(buffer.getvalue())


def barcode(data, **writer_options) -> str:
    """Return a vector barcode, without the human-readable text by default.

    The barcode payload carries the warehouse prefix, which must never be
    shown to the operator - the label prints its own readable caption.
    """
    writer_options.setdefault("write_text", False)
    module_width = writer_options.get("module_width", _DEFAULT_MODULE_WIDTH_MM)
    writer_options.setdefault("quiet_zone", _LINEAR_QUIET_MODULES * module_width)
    return _blabel_barcode(data, fmt="svg", **writer_options)


def fit_font(
    text,
    box_width_mm: float,
    max_mm: float,
    min_mm: float = 2.0,
    letter_spacing_mm: float = 0.0,
) -> float:
    """Largest font size (mm) that keeps `text` on one line inside the box.

    Pass the rule's ``letter-spacing`` too - it is what pushed long SKUs out
    of their box even after the font had been scaled down.
    """
    length = len(str(text or ""))
    if not length:
        return max_mm
    available = box_width_mm - length * letter_spacing_mm
    return round(max(min_mm, min(max_mm, available / (length * _MONO_CHAR_WIDTH))), 2)


def fit_font_block(
    text,
    box_width_mm: float,
    box_height_mm: float,
    max_mm: float,
    min_mm: float = 2.0,
    line_height: float = 1.25,
) -> float:
    """Largest font size (mm) at which wrapped `text` still fits the box."""
    text = str(text or "")
    if not text:
        return max_mm
    size = max_mm
    while size > min_mm:
        chars_per_line = max(1, int(box_width_mm / (size * _MONO_CHAR_WIDTH)))
        lines = sum(len(wrap(part, chars_per_line).splitlines()) or 1 for part in text.splitlines())
        if lines * size * line_height <= box_height_mm:
            break
        size = round(size - 0.1, 2)
    return max(size, min_mm)
