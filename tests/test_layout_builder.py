import json
import re
from pathlib import Path

import jinja2
import pytest
import zxingcpp

from app.core import label_tools
from app.core.layout_builder import (
    SAMPLE_RECORDS,
    black_block_mm,
    check_save_target,
    generate,
    load_layout,
    normalise_layout,
    render_sample,
    save_layout,
    slugify,
)
from app.core.template_renderer import (
    EXAMPLES_ROOT,
    TemplatePreset,
    list_presets,
    render_records,
)

REGENERATE = "run: .venv/bin/python -m app.core.layout_builder"
SHIPPED_FOLDERS = [
    pytest.param(folder, id=f"{folder.parent.name}/{folder.name}")
    for mode in ("positions", "inventory")
    for folder in sorted((EXAMPLES_ROOT / mode).iterdir())
    if folder.is_dir()
]


@pytest.mark.parametrize("folder", SHIPPED_FOLDERS)
def test_shipped_layout_files_match_generate(folder):
    assert (folder / "layout.json").exists(), REGENERATE
    expected = generate(load_layout(folder))
    for name, content in expected.items():
        assert (folder / name).read_text(encoding="utf-8") == content, f"{name} drifted - {REGENERATE}"


def _inventory_base(elements):
    return {
        "name": "X",
        "mode": "inventory",
        "width_mm": 68,
        "height_mm": 38,
        "elements": elements,
    }


def test_normalise_fills_defaults_and_clamps_thickness():
    layout = normalise_layout(
        _inventory_base(
            [
                {
                    "type": "box",
                    "x_mm": 1,
                    "y_mm": 1,
                    "w_mm": 10,
                    "h_mm": 10,
                    "thickness_mm": 2,
                },
                {
                    "type": "line",
                    "x_mm": 1,
                    "y_mm": 5,
                    "w_mm": 20,
                    "h_mm": 7,
                    "orientation": "h",
                    "thickness_mm": 0.1,
                },
                {
                    "type": "text",
                    "x_mm": 0,
                    "y_mm": 0,
                    "w_mm": 20,
                    "h_mm": 5,
                    "content": "{sku}",
                },
            ]
        )
    )

    box, line, text = layout["elements"]
    assert box["thickness_mm"] == 0.5 and line["thickness_mm"] == 0.3
    assert line["h_mm"] == 0  # off-axis size forced to 0
    assert (
        text["wrap"] is False
        and text["align"] == "left"
        and text["letter_spacing_mm"] == 0
    )


@pytest.mark.parametrize(
    "bad, message",
    [
        ({"mode": "pallets"}, "mode"),
        ({"width_mm": 5}, "width"),
        (
            {
                "elements": [
                    {"type": "circle", "x_mm": 0, "y_mm": 0, "w_mm": 5, "h_mm": 5}
                ]
            },
            "circle",
        ),
        (
            {
                "elements": [
                    {
                        "type": "qr",
                        "x_mm": 0,
                        "y_mm": 0,
                        "w_mm": 5,
                        "h_mm": 5,
                        "field": "code",
                    }
                ]
            },
            "code",
        ),
        (
            {
                "elements": [
                    {
                        "type": "text",
                        "x_mm": 0,
                        "y_mm": 0,
                        "w_mm": 5,
                        "h_mm": 5,
                        "content": "{skuu}",
                    }
                ]
            },
            "skuu",
        ),
        (
            {
                "elements": [
                    {
                        "type": "text",
                        "x_mm": -1,
                        "y_mm": 0,
                        "w_mm": 5,
                        "h_mm": 5,
                        "content": "a",
                    }
                ]
            },
            "x_mm",
        ),
    ],
)
def test_normalise_rejects(bad, message):
    with pytest.raises(ValueError, match=message):
        normalise_layout({**_inventory_base([]), **bad})


def test_literal_text_stays_literal_and_values_are_escaped():
    content = 'A "q" {{x}} {% y %} <b> {sku}'
    layout = normalise_layout(
        _inventory_base(
            [
                {
                    "type": "text",
                    "x_mm": 0,
                    "y_mm": 0,
                    "w_mm": 60,
                    "h_mm": 8,
                    "content": content,
                }
            ]
        )
    )

    html = jinja2.Template(generate(layout)["template.html"]).render(
        sku="<S>", label_tools=label_tools
    )

    assert "&#34;q&#34;" in html and '"q"' not in html
    assert "{{x}}" in html and "{% y %}" in html
    assert "&lt;b&gt;" in html and "&lt;S&gt;" in html


def test_empty_code_field_renders_no_img():
    layout = normalise_layout(
        _inventory_base(
            [
                {
                    "type": "qr",
                    "x_mm": 0,
                    "y_mm": 0,
                    "w_mm": 20,
                    "h_mm": 20,
                    "field": "batch",
                }
            ]
        )
    )
    template = jinja2.Template(generate(layout)["template.html"])

    assert "<img" not in template.render(batch="", label_tools=label_tools)
    assert "<img" in template.render(batch="B-1", label_tools=label_tools)


def test_generate_is_deterministic_and_has_no_fill():
    layout = normalise_layout(
        _inventory_base([{"type": "box", "x_mm": 1, "y_mm": 1, "w_mm": 10, "h_mm": 10}])
    )

    files = generate(layout)

    assert files == generate(layout)
    assert re.findall(r"background[^;]*;", files["style.css"]) == ["background: #fff;"]
    assert json.loads(files["meta.json"]) == {
        "name": "X",
        "width_mm": 68,
        "height_mm": 38,
    }


def test_generated_preset_renders_and_scans(tmp_path: Path):
    layout = normalise_layout(
        _inventory_base(
            [
                {
                    "type": "barcode",
                    "x_mm": 2,
                    "y_mm": 2,
                    "w_mm": 40,
                    "h_mm": 14,
                    "field": "sku",
                },
                {
                    "type": "qr",
                    "x_mm": 46,
                    "y_mm": 2,
                    "w_mm": 20,
                    "h_mm": 20,
                    "field": "position_data",
                },
            ]
        )
    )
    files = generate(layout)
    (tmp_path / "template.html").write_text(files["template.html"], encoding="utf-8")
    (tmp_path / "style.css").write_text(files["style.css"], encoding="utf-8")
    preset = TemplatePreset(
        name="Generated",
        mode="inventory",
        width_mm=68,
        height_mm=38,
        template_path=tmp_path / "template.html",
        stylesheet_path=tmp_path / "style.css",
    )

    image = render_records(preset, [SAMPLE_RECORDS["inventory"]])[0]

    symbols = zxingcpp.read_barcodes(image.convert("L"))
    assert {s.text for s in symbols} == {"SKU-12345", "C001H029A"}


@pytest.mark.parametrize(
    "name, slug",
    [
        ("Product 68x38mm", "product-68x38mm"),
        ("  Ünïcode / A  ", "ünïcode-a"),
        ("!!!", ""),
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug


def _label(name: str, elements: list | None = None) -> dict:
    return _inventory_base(elements or []) | {"name": name}


def _shared_preset(shared: Path, folder: str, name: str) -> None:
    preset_dir = shared / "templates" / "inventory" / folder
    preset_dir.mkdir(parents=True)
    (preset_dir / "meta.json").write_text(
        json.dumps({"name": name, "width_mm": 68, "height_mm": 38})
    )
    (preset_dir / "template.html").write_text("<div></div>")
    (preset_dir / "style.css").write_text("")


def test_check_save_target_new_uses_slug(tmp_path):
    target = check_save_target(tmp_path, _label("My label"), None)

    assert target == tmp_path / "templates" / "inventory" / "my-label"


def test_check_save_target_refuses_app_owned(tmp_path):
    with pytest.raises(ValueError, match="built-in"):
        check_save_target(tmp_path, _label("Default"), None)


def test_check_save_target_refuses_existing_folder(tmp_path):
    (tmp_path / "templates" / "inventory" / "my-label").mkdir(parents=True)

    with pytest.raises(ValueError, match="already exists"):
        check_save_target(tmp_path, _label("My label"), None)


def test_check_save_target_refuses_duplicate_display_name(tmp_path):
    _shared_preset(tmp_path, "other", "My label")

    with pytest.raises(ValueError, match="already called"):
        check_save_target(tmp_path, _label("My label"), None)


def test_check_save_target_edit_keeps_folder_on_rename(tmp_path):
    edit_folder = tmp_path / "templates" / "inventory" / "mine"
    _shared_preset(tmp_path, "mine", "Mine")

    assert check_save_target(tmp_path, _label("Renamed"), edit_folder) == edit_folder
    assert check_save_target(tmp_path, _label("Mine"), edit_folder) == edit_folder


def test_check_save_target_refuses_edit_of_app_owned(tmp_path):
    edit_folder = tmp_path / "templates" / "inventory" / "default"

    with pytest.raises(ValueError, match="built-in"):
        check_save_target(tmp_path, _label("Anything"), edit_folder)


def test_check_save_target_refuses_nameless(tmp_path):
    with pytest.raises(ValueError, match="letter or digit"):
        check_save_target(tmp_path, _label("!!!"), None)


def test_save_layout_then_list_presets_and_load_round_trip(tmp_path):
    layout = _label("My label", [{"type": "box", "x_mm": 1, "y_mm": 1, "w_mm": 10, "h_mm": 10}])
    folder = check_save_target(tmp_path, layout, None)

    save_layout(layout, folder)

    assert "My label" in [p.name for p in list_presets(tmp_path, "inventory")]
    assert load_layout(folder) == normalise_layout(layout)
    assert list(folder.glob("*.tmp")) == []


def test_black_block_mm_flags_stacked_lines():
    stacked = [
        {"type": "line", "x_mm": 2, "y_mm": 10 + 0.5 * i, "w_mm": 60, "h_mm": 0, "thickness_mm": 0.5}
        for i in range(20)
    ]
    found = black_block_mm(_label("Stack", stacked), SAMPLE_RECORDS["inventory"])

    assert found is not None
    x, y = found
    assert 2 <= x <= 62 and 10 <= y <= 17
    assert black_block_mm(_label("Box", [{"type": "box", "x_mm": 1, "y_mm": 1, "w_mm": 30, "h_mm": 20}]), SAMPLE_RECORDS["inventory"]) is None


def test_render_sample_size():
    image = render_sample(_label("Blank"), SAMPLE_RECORDS["inventory"])

    assert abs(image.width - round(68 / 25.4 * 203)) <= 1
    assert abs(image.height - round(38 / 25.4 * 203)) <= 1
