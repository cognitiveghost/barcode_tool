import json
import os
import stat
import sys
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image

from app.core.template_renderer import (
    DEFAULT_DPI,
    FONT_CSS,
    TemplatePreset,
    list_presets,
    render_records,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "templates" / "sample"


def test_list_presets_seeds_examples_into_empty_shared_folder(tmp_path):
    presets = list_presets(tmp_path, "positions")

    assert len(presets) == 1
    assert presets[0].name == "Default 150x100mm"
    assert presets[0].width_mm == 150
    assert presets[0].height_mm == 100
    assert (tmp_path / "templates" / "positions" / "default" / "template.html").exists()


def test_list_presets_seeds_inventory_examples_too(tmp_path):
    presets = list_presets(tmp_path, "inventory")

    assert len(presets) == 1
    assert presets[0].name == "Default 150x100mm"


def test_list_presets_keeps_custom_presets_alongside_the_default(tmp_path):
    mode_dir = tmp_path / "templates" / "inventory" / "custom"
    mode_dir.mkdir(parents=True)
    (mode_dir / "meta.json").write_text(
        json.dumps({"name": "Custom", "width_mm": 80, "height_mm": 80})
    )
    (mode_dir / "template.html").write_text("<div>{{ sku }}</div>")
    (mode_dir / "style.css").write_text("@page { size: 80mm 80mm; }")

    presets = list_presets(tmp_path, "inventory")

    assert [p.name for p in presets] == ["Custom", "Default 150x100mm"]
    assert (mode_dir / "template.html").read_text() == "<div>{{ sku }}</div>"


def test_list_presets_refreshes_a_stale_seeded_default(tmp_path):
    # A shared folder seeded by an older build must pick up shipped fixes,
    # otherwise every existing install keeps rendering the old label.
    default_dir = tmp_path / "templates" / "positions" / "default"
    default_dir.mkdir(parents=True)
    (default_dir / "meta.json").write_text(
        json.dumps({"name": "Stale", "width_mm": 100, "height_mm": 50})
    )
    (default_dir / "template.html").write_text("<div>STALE_MARKER</div>")
    (default_dir / "style.css").write_text("@page { size: 100mm 50mm; }")

    presets = list_presets(tmp_path, "positions")

    assert [p.name for p in presets] == ["Default 150x100mm"]
    assert "STALE_MARKER" not in (default_dir / "template.html").read_text()


def test_list_presets_leaves_an_unchanged_default_alone(tmp_path):
    # write_text truncates before writing, so rewriting identical content on
    # every launch is a window where another machine on the same shared
    # folder reads a half-written template.
    list_presets(tmp_path, "positions")
    template = tmp_path / "templates" / "positions" / "default" / "template.html"
    before = template.stat().st_mtime_ns

    list_presets(tmp_path, "positions")

    assert template.stat().st_mtime_ns == before


def test_list_presets_seeds_a_readme_explaining_the_overwrite(tmp_path):
    list_presets(tmp_path, "positions")

    readme = (tmp_path / "templates" / "positions" / "README.txt").read_text()
    assert "REWRITTEN" in readme


# One condition, not two decorators: both are evaluated at import time, so a
# separate skipif still calls os.geteuid() on Windows, where it does not exist.
@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="needs POSIX permission bits, and root ignores them",
)
def test_list_presets_survives_a_read_only_shared_folder(tmp_path):
    # Shared folders are often mounted read-only for most operators. Failing
    # to reseed must degrade to "list what is there", not crash app startup.
    list_presets(tmp_path, "positions")
    mode_dir = tmp_path / "templates" / "positions"
    default_dir = mode_dir / "default"
    (default_dir / "template.html").write_text("<div>stale</div>")
    for target in (default_dir, mode_dir):
        target.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        presets = list_presets(tmp_path, "positions")
    finally:
        for target in (mode_dir, default_dir):
            target.chmod(stat.S_IRWXU)

    assert [p.name for p in presets] == ["Default 150x100mm"]


def test_list_presets_skips_a_preset_with_malformed_meta(tmp_path):
    # meta.json is hand-edited in a folder several machines share - one typo
    # must cost that preset, not everyone else's app launch.
    broken = tmp_path / "templates" / "positions" / "broken"
    broken.mkdir(parents=True)
    (broken / "meta.json").write_text('{"name": "Broken", "width_mm": 50,}')

    presets = list_presets(tmp_path, "positions")

    assert [p.name for p in presets] == ["Default 150x100mm"]


def test_list_presets_skips_a_preset_missing_meta_keys(tmp_path):
    incomplete = tmp_path / "templates" / "positions" / "incomplete"
    incomplete.mkdir(parents=True)
    (incomplete / "meta.json").write_text(json.dumps({"name": "No size"}))

    presets = list_presets(tmp_path, "positions")

    assert [p.name for p in presets] == ["Default 150x100mm"]


def test_list_presets_returns_empty_for_a_mode_with_no_examples(tmp_path):
    assert list_presets(tmp_path, "not_a_mode") == []


def test_list_presets_lists_multiple_presets_sorted_by_folder_name(tmp_path):
    for slug, name in (("b_preset", "B"), ("a_preset", "A")):
        mode_dir = tmp_path / "templates" / "positions" / slug
        mode_dir.mkdir(parents=True)
        (mode_dir / "meta.json").write_text(
            json.dumps({"name": name, "width_mm": 50, "height_mm": 50})
        )
        (mode_dir / "template.html").write_text("<div></div>")
        (mode_dir / "style.css").write_text("@page { size: 50mm 50mm; }")

    presets = list_presets(tmp_path, "positions")

    assert [p.name for p in presets] == ["A", "B", "Default 150x100mm"]


def _sample_preset() -> TemplatePreset:
    return TemplatePreset(
        name="Sample",
        mode="test",
        width_mm=40,
        height_mm=30,
        template_path=FIXTURE_DIR / "template.html",
        stylesheet_path=FIXTURE_DIR / "style.css",
    )


def test_render_records_returns_one_image_per_record():
    images = render_records(
        _sample_preset(),
        [{"code": "A1", "label": "A1"}, {"code": "A2", "label": "A2"}],
    )

    assert len(images) == 2
    assert all(isinstance(img, Image.Image) for img in images)


def test_render_records_image_size_matches_preset_mm_at_dpi():
    images = render_records(_sample_preset(), [{"code": "A1", "label": "A1"}], dpi=203)

    expected_width = round(40 / 25.4 * 203)
    expected_height = round(30 / 25.4 * 203)
    assert abs(images[0].width - expected_width) <= 1
    assert abs(images[0].height - expected_height) <= 1


def test_render_records_defaults_to_the_print_head_resolution():
    # ZPL maps one image pixel to one dot, so the default has to match the
    # heads in the field or raw-ZPL labels come out the wrong size.
    assert DEFAULT_DPI == 203
    image = render_records(_sample_preset(), [{"code": "A1", "label": "A1"}])[0]

    assert abs(image.width - round(40 / 25.4 * 203)) <= 1


def test_render_records_output_reflects_record_data():
    img_a = render_records(_sample_preset(), [{"code": "A1", "label": "A1"}])[0]
    img_b = render_records(_sample_preset(), [{"code": "A2", "label": "A2"}])[0]

    assert img_a.tobytes() != img_b.tobytes()


def test_render_records_returns_bilevel_images_for_thermal_heads():
    assert render_records(_sample_preset(), [{"code": "A1", "label": "A1"}])[0].mode == "1"


POSITION_RECORD = {
    "code": "d002e",
    "barcode_data": "C002d002e",
    "visible_text": "D-002-E",
    "user_text": "GOOZE TEST",
}
INVENTORY_RECORD = {
    "sku": "SOLARIX-FACE-1000ML-REFILL",
    "name": "Гвинт М6×40 DIN933",
    "client": "ТОВ «Складсервіс»",
    "batch": "B-240815",
    "expiry": "2027-05-31",
    "position_code": "D-002-E",
    "position_data": "C002d002e",
    "generated_date": "2026/08/02",
}


@pytest.mark.parametrize(
    ("mode", "record"),
    [("positions", POSITION_RECORD), ("inventory", INVENTORY_RECORD)],
)
def test_shipped_default_renders_the_fields_the_panels_pass(tmp_path, mode, record):
    # End-to-end guard over the bundled font, the injected label_tools and
    # the template layout - a template that fails to render silently ships.
    preset = list_presets(tmp_path, mode)[-1]

    image = render_records(preset, [record], dpi=203)[0]

    assert preset.name == "Default 150x100mm"
    assert abs(image.width - round(150 / 25.4 * 203)) <= 1
    assert abs(image.height - round(100 / 25.4 * 203)) <= 1
    # getcolors() yields (count, pixel_value) pairs
    assert {pixel for _, pixel in image.getcolors()} == {0, 255}  # ink landed


@pytest.mark.parametrize(
    ("mode", "record", "expected"),
    [
        ("positions", POSITION_RECORD, {"C002d002e"}),
        (
            "inventory",
            INVENTORY_RECORD,
            {"C002d002e", "SOLARIX-FACE-1000ML-REFILL", "2027-05-31", "B-240815"},
        ),
    ],
)
def test_shipped_default_labels_actually_scan(tmp_path, mode, record, expected):
    # End-to-end smoke test: a decoder reading the bilevel image we hand the
    # print head gets every payload back, so the template, the threshold and
    # the box sizes produce a real symbol rather than a plausible-looking
    # pattern. It is deliberately not the quiet-zone guard - a decoder is far
    # more forgiving on a clean digital render than a scanner is on thermal
    # paper, so the ISO geometry is asserted directly in test_label_tools.
    preset = list_presets(tmp_path, mode)[-1]

    image = render_records(preset, [record])[0]

    symbols = zxingcpp.read_barcodes(image.convert("L"))
    assert {s.text for s in symbols} == expected
    assert all(s.valid for s in symbols)


@pytest.mark.parametrize(
    ("mode", "record"),
    [("positions", POSITION_RECORD), ("inventory", INVENTORY_RECORD)],
)
def test_shipped_default_actually_applies_the_bundled_font(tmp_path, monkeypatch, mode, record):
    # Regression test: the font used to be handed to WeasyPrint as a
    # CSS(string=...) object, which silently drops @font-face rules when it
    # is built without a font_config - so every label fell back to whatever
    # monospace the machine happened to have, which is exactly the per-machine
    # variance bundling the font was meant to remove. Swapping the bundled
    # font for an empty stylesheet must visibly change the render.
    assert FONT_CSS.exists()
    preset = list_presets(tmp_path, mode)[-1]
    with_font = render_records(preset, [record])[0]

    empty_css = tmp_path / "no-fonts.css"
    empty_css.write_text("")
    monkeypatch.setattr("app.core.template_renderer.FONT_CSS", empty_css)
    without_font = render_records(preset, [record])[0]

    assert with_font.tobytes() != without_font.tobytes()


def test_render_records_raises_when_meta_size_does_not_match_rendered_page():
    mismatched_preset = TemplatePreset(
        name="Mismatched",
        mode="positions",
        width_mm=100,  # fixture's style.css @page is 40mm x 30mm (4:3);
        height_mm=100,  # this claims 1:1 - well past the ~1% tolerance.
        template_path=FIXTURE_DIR / "template.html",
        stylesheet_path=FIXTURE_DIR / "style.css",
    )

    with pytest.raises(ValueError, match="Mismatched"):
        render_records(mismatched_preset, [{"code": "A1", "label": "A1"}])
