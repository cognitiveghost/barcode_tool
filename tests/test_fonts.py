from app.core.fonts import load_font


def test_load_font_returns_requested_size():
    font = load_font(20)
    assert font.size == 20


def test_load_font_bold_uses_a_different_file_than_regular():
    regular = load_font(20)
    bold = load_font(20, bold=True)
    assert regular.path != bold.path


def test_load_font_renders_cyrillic_glyphs():
    font = load_font(20)
    mask = font.getmask("Привет")
    assert mask.getbbox() is not None
