import base64
import re

import qrcode

from app.core.label_tools import barcode, fit_font, fit_font_block, qr_code


def _decoded(data_uri: str) -> str:
    return base64.b64decode(data_uri.split(",", 1)[1]).decode()


def _qr_grid_size(svg: str) -> int:
    """Modules across the emitted symbol, quiet zone included."""
    return round(float(re.search(r'viewBox="0 0 (\d+(?:\.\d+)?)', svg).group(1)))


def _linear_geometry(svg: str) -> tuple[float, float, float]:
    """(left quiet zone mm, narrow element mm, right quiet zone mm)."""
    total = float(re.search(r'width="([\d.]+)mm"', svg).group(1))
    bars = [
        (float(x), float(w))
        for x, w in re.findall(r'<rect[^>]*x="([\d.]+)mm"[^>]*width="([\d.]+)mm"', svg)
        if float(w) < 5
    ]
    first = min(x for x, _ in bars)
    last = max(x + w for x, w in bars)
    return first, min(w for _, w in bars), total - last


def test_barcode_is_vector_so_it_stays_sharp_at_print_resolution():
    assert _decoded(barcode("C002d002e")).lstrip().startswith("<?xml")


def test_barcode_omits_the_human_readable_payload():
    # The payload carries the warehouse prefix, which must never be printed.
    assert "<text" not in _decoded(barcode("C002d002e"))


def test_barcode_can_still_be_asked_for_its_text():
    assert "<text" in _decoded(barcode("C002d002e", write_text=True))


def test_qr_code_is_vector():
    assert "<svg" in _decoded(qr_code("ART-4471"))


def test_qr_code_encodes_the_given_data():
    assert _decoded(qr_code("ART-4471")) != _decoded(qr_code("ART-4472"))


def test_qr_code_carries_the_iso_18004_quiet_zone():
    # ISO/IEC 18004 6.3.7 - 4 clear modules on every side. The CSS box is
    # only what the layout reserves, so on the inventory label a code drawn
    # edge to edge ends up with a solid black chip against its finders.
    data = "C002d002e"
    symbol = qrcode.QRCode(border=0)
    symbol.add_data(data)
    symbol.make()

    assert _qr_grid_size(_decoded(qr_code(data))) == symbol.modules_count + 2 * 4


def test_qr_code_quiet_zone_still_leaves_scannable_modules_at_203dpi():
    # Smallest code on the inventory label is a 20mm box; the quiet zone eats
    # into it, so check what is left is still several print-head dots wide.
    grid = _qr_grid_size(_decoded(qr_code("2027-05-31")))
    module_dots = 20 / grid / 25.4 * 203

    assert module_dots >= 4


def test_barcode_carries_the_iso_15417_quiet_zone():
    # ISO/IEC 15417 - Code 128 needs at least 10x the narrow element width
    # clear on both sides.
    left, narrow, right = _linear_geometry(_decoded(barcode("C002d002e")))

    assert left / narrow >= 10
    assert right / narrow >= 10


def test_barcode_quiet_zone_follows_a_custom_module_width():
    # A hard-coded 2.0mm quiet zone is 10x only at the default module width;
    # a template widening the bars would silently drop below spec.
    left, narrow, right = _linear_geometry(_decoded(barcode("C002d002e", module_width=0.5)))

    assert narrow == 0.5
    assert left / narrow >= 10
    assert right / narrow >= 10


def test_fit_font_keeps_the_maximum_size_for_short_text():
    assert fit_font("D-002-E", 136, 18) == 18


def test_fit_font_shrinks_text_that_would_overflow():
    assert fit_font("SOLARIX-FACE-1000ML-REFILL", 45, 9.5) < 9.5


def test_fit_font_result_actually_fits_the_box():
    text = "SOLARIX-FACE-1000ML-REFILL"
    size = fit_font(text, 45, 9.5, letter_spacing_mm=0.3)

    assert len(text) * (size * 0.6 + 0.3) <= 45


def test_fit_font_accounts_for_letter_spacing():
    assert fit_font("ABCDEFGHIJ", 20, 9) > fit_font("ABCDEFGHIJ", 20, 9, letter_spacing_mm=0.5)


def test_fit_font_handles_empty_and_missing_text():
    assert fit_font("", 45, 9.5) == 9.5
    assert fit_font(None, 45, 9.5) == 9.5


def test_fit_font_never_goes_below_the_minimum():
    assert fit_font("x" * 500, 45, 9.5, min_mm=2.0) == 2.0


def test_fit_font_block_shrinks_until_the_wrapped_text_fits():
    text = "SOLARIX+ ultra moisturising face cream, 1000 ml refill pack"
    size = fit_font_block(text, 41, 19, 4.6)

    assert size < 4.6
    chars_per_line = int(41 / (size * 0.6))
    lines = -(-len(text) // chars_per_line)
    assert lines * size * 1.25 <= 19 * 1.05
