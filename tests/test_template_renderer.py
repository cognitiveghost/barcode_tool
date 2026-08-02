import json

from app.core.template_renderer import list_presets


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
