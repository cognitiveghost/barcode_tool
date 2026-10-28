import base64
import io
import shutil

from PIL import Image, ImageDraw

from app.core.template_renderer import (
    EXAMPLES_ROOT,
    TemplatePreset,
    find_black_block,
    find_thermal_black_block,
    render_records,
)
from tests.test_template_renderer import POSITION_RECORD

INVERTED_BAR_CSS = (
    ".position-name { left: 3mm; top: 71mm; width: 144mm; height: 26mm; "
    "background: #000; color: #fff; }"
)


def _label_with_square(w, h, x=100, y=50, size=(1218, 812)):
    img = Image.new("1", size, 1)
    ImageDraw.Draw(img).rectangle((x, y, x + w - 1, y + h - 1), fill=0)
    return img


def test_finds_a_24_dot_square():
    found = find_black_block(_label_with_square(24, 24))
    assert found is not None
    assert abs(found[0] - 100) <= 1 and abs(found[1] - 50) <= 1


def test_ignores_a_square_one_dot_short_either_way():
    assert find_black_block(_label_with_square(23, 24)) is None
    assert find_black_block(_label_with_square(24, 23)) is None


def test_finds_a_square_touching_the_label_edge():
    assert find_black_block(_label_with_square(24, 24, x=0, y=0)) is not None


def test_white_label_and_thin_long_line_are_clean():
    assert find_black_block(Image.new("1", (1218, 812), 1)) is None
    assert find_black_block(_label_with_square(1000, 4)) is None  # 0.5 mm line


def _copy_position_preset(tmp_path, extra_css=""):
    folder = tmp_path / "default"
    shutil.copytree(EXAMPLES_ROOT / "positions" / "default", folder)
    if extra_css:
        style = folder / "style.css"
        style.write_text(style.read_text(encoding="utf-8") + "\n" + extra_css, encoding="utf-8")
    return TemplatePreset(
        name="Default 150x100mm",
        mode="positions",
        width_mm=150,
        height_mm=100,
        template_path=folder / "template.html",
        stylesheet_path=folder / "style.css",
    )


def test_thermal_check_ignores_barcodes(tmp_path):
    preset = _copy_position_preset(tmp_path)
    style = preset.stylesheet_path
    css = style.read_text(encoding="utf-8")
    css = css.replace("background: #000;\n  color: #fff;", "color: #000;")
    style.write_text(css, encoding="utf-8")

    assert find_thermal_black_block(preset, [POSITION_RECORD]) is None


def test_thermal_check_ignores_a_solid_black_code_image(tmp_path):
    # A visible barcode is never a solid block, so prove code images are hidden
    # with an image that is one: a 5 mm black square.
    buffer = io.BytesIO()
    Image.new("L", (60, 60), 0).save(buffer, format="PNG")
    src = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    template = tmp_path / "template.html"
    template.write_text(f'<div class="label"><img src="{src}"></div>', encoding="utf-8")
    style = tmp_path / "style.css"
    style.write_text(
        "@page { size: 150mm 100mm; margin: 0; }\n"
        ".label { position: relative; width: 150mm; height: 100mm; }\n"
        "img { position: absolute; left: 10mm; top: 10mm; width: 5mm; height: 5mm; }\n",
        encoding="utf-8",
    )
    preset = TemplatePreset("Square", "positions", 150, 100, template, style)

    assert find_black_block(render_records(preset, [{}])[0]) is not None
    assert find_thermal_black_block(preset, [{}]) is None


def test_thermal_check_catches_the_old_inverted_bar(tmp_path):
    preset = _copy_position_preset(tmp_path, extra_css=INVERTED_BAR_CSS)

    result = find_thermal_black_block(preset, [POSITION_RECORD])

    assert result is not None
    assert result[0] == 0
