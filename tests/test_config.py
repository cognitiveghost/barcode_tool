import json

from app.core.config import DEFAULT_SETTINGS, load_settings, save_settings


def test_load_settings_returns_defaults_when_missing(tmp_path):
    path = tmp_path / "settings.json"
    assert load_settings(path) == DEFAULT_SETTINGS


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    settings["shared_folder"] = "/mnt/shared"
    settings["warehouses"].append({"name": "Main", "prefix": "C001"})

    save_settings(path, settings)
    loaded = load_settings(path)

    assert loaded == settings
