import json
from pathlib import Path

from PIL import Image

from app.core.template_renderer import TemplatePreset, list_presets, render_records

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "templates" / "sample"


def test_list_presets_seeds_examples_into_empty_shared_folder(tmp_path):
    presets = list_presets(tmp_path, "positions")

    assert len(presets) == 1
    assert presets[0].name == "Default 100x50mm"
    assert presets[0].width_mm == 100
    assert presets[0].height_mm == 50
    assert (tmp_path / "templates" / "positions" / "default" / "template.html").exists()


def test_list_presets_seeds_inventory_examples_too(tmp_path):
    presets = list_presets(tmp_path, "inventory")

    assert len(presets) == 1
    assert presets[0].name == "Default 150x100mm"


def test_list_presets_returns_existing_presets_without_reseeding(tmp_path):
    mode_dir = tmp_path / "templates" / "inventory" / "custom"
    mode_dir.mkdir(parents=True)
    (mode_dir / "meta.json").write_text(
        json.dumps({"name": "Custom", "width_mm": 80, "height_mm": 80})
    )
    (mode_dir / "template.html").write_text("<div>{{ sku }}</div>")
    (mode_dir / "style.css").write_text("@page { size: 80mm 80mm; }")

    presets = list_presets(tmp_path, "inventory")

    assert [p.name for p in presets] == ["Custom"]
    assert not (tmp_path / "templates" / "inventory" / "default").exists()


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

    assert [p.name for p in presets] == ["A", "B"]


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


def test_render_records_output_reflects_record_data():
    img_a = render_records(_sample_preset(), [{"code": "A1", "label": "A1"}])[0]
    img_b = render_records(_sample_preset(), [{"code": "A2", "label": "A2"}])[0]

    assert img_a.tobytes() != img_b.tobytes()
