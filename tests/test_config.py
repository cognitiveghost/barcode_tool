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


def test_load_settings_fills_in_keys_missing_from_an_older_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"shared_folder": "/mnt/shared"}), encoding="utf-8")

    loaded = load_settings(path)

    assert loaded["shared_folder"] == "/mnt/shared"
    assert loaded["csv_mappings"] == {}
    assert loaded["warehouses"] == []


def test_load_settings_does_not_share_mutable_defaults(tmp_path):
    first = load_settings(tmp_path / "a.json")
    first["warehouses"].append({"name": "Main", "prefix": "C001"})

    second = load_settings(tmp_path / "b.json")

    assert second["warehouses"] == []


def test_load_settings_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")

    loaded = load_settings(path)

    assert loaded == DEFAULT_SETTINGS
    assert not path.exists()
    assert (tmp_path / "settings.json.corrupt").read_text(encoding="utf-8") == "{not valid json"


def test_load_settings_calls_on_recovery_with_a_message(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json at all", encoding="utf-8")
    messages = []

    load_settings(path, on_recovery=messages.append)

    assert len(messages) == 1
    assert "settings.json" in messages[0]


def test_load_settings_recovers_when_json_is_not_an_object(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    loaded = load_settings(path)

    assert loaded == DEFAULT_SETTINGS


def test_save_settings_never_leaves_a_tmp_file_behind(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, DEFAULT_SETTINGS)

    assert path.exists()
    assert not (tmp_path / "settings.json.tmp").exists()
