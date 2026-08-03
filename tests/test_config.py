import json
import logging

import pytest

from app.core.config import (
    DEFAULT_SETTINGS,
    LOGGER_NAME,
    load_settings,
    sanitize_filename_component,
    save_settings,
    save_shared_settings,
    shared_folder,
    shared_settings_path,
    sync_shared_settings,
)


@pytest.fixture
def log_records():
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


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


def test_shared_folder_uses_configured_value(tmp_path):
    assert shared_folder({"shared_folder": str(tmp_path)}) == tmp_path


def test_shared_folder_falls_back_to_default_settings_path_parent(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.default_settings_path", lambda: tmp_path / "settings.json")
    assert shared_folder({"shared_folder": ""}) == tmp_path


def test_sanitize_filename_component_replaces_unsafe_characters():
    assert sanitize_filename_component("H029..H030") == "H029..H030"
    # Both the comma and the space are unsafe (the regex only allows
    # [A-Za-z0-9_.-]), so each becomes its own underscore.
    assert sanitize_filename_component("SKU1, SKU2") == "SKU1__SKU2"


def test_corrupted_settings_load_logs_a_warning(log_records, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")

    load_settings(path)

    assert any("could not be read" in r.getMessage() for r in log_records)


def test_shared_settings_path_is_inside_the_shared_folder(tmp_path):
    local_path = tmp_path / "local" / "settings.json"
    assert (
        shared_settings_path({"shared_folder": str(tmp_path)}, local_path) == tmp_path / "settings.json"
    )


def test_shared_settings_path_falls_back_to_the_local_path_when_unconfigured(tmp_path):
    local_path = tmp_path / "local" / "settings.json"
    assert shared_settings_path({"shared_folder": ""}, local_path) == local_path


def test_sync_shared_settings_seeds_the_shared_file_on_first_configure(tmp_path):
    shared_dir = tmp_path / "shared"
    local_path = tmp_path / "local" / "settings.json"
    settings = {
        "shared_folder": str(shared_dir),
        "warehouses": [{"name": "Main", "prefix": "C001"}],
        "csv_mappings": {"positions": {}},
    }

    sync_shared_settings(settings, local_path)

    assert (shared_dir / "settings.json").exists()
    shared = load_settings(shared_dir / "settings.json")
    assert shared["warehouses"] == [{"name": "Main", "prefix": "C001"}]


def test_sync_shared_settings_overlays_from_an_existing_shared_file(tmp_path):
    shared_dir = tmp_path / "shared"
    local_path = tmp_path / "local" / "settings.json"
    save_settings(
        shared_dir / "settings.json",
        {**DEFAULT_SETTINGS, "warehouses": [{"name": "FromOtherPC", "prefix": "C002"}]},
    )
    settings = {
        "shared_folder": str(shared_dir),
        "warehouses": [{"name": "Stale", "prefix": "C001"}],
        "csv_mappings": {},
    }

    synced = sync_shared_settings(settings, local_path)

    assert synced["warehouses"] == [{"name": "FromOtherPC", "prefix": "C002"}]


def test_sync_shared_settings_is_a_noop_without_a_configured_shared_folder(tmp_path):
    local_path = tmp_path / "settings.json"
    settings = {"shared_folder": "", "warehouses": [{"name": "Main", "prefix": "C001"}], "csv_mappings": {}}

    synced = sync_shared_settings(settings, local_path)

    assert synced["warehouses"] == [{"name": "Main", "prefix": "C001"}]
    assert not local_path.exists()  # no-op: never touched the filesystem


def test_save_shared_settings_only_touches_the_keys_it_is_given(tmp_path):
    shared_dir = tmp_path / "shared"
    local_path = tmp_path / "local" / "settings.json"
    save_shared_settings(
        {"shared_folder": str(shared_dir), "warehouses": [{"name": "Main", "prefix": "C001"}]}, local_path
    )

    save_shared_settings(
        {"shared_folder": str(shared_dir), "csv_mappings": {"positions": {"sig": {"sku": 0}}}}, local_path
    )

    shared = load_settings(shared_dir / "settings.json")
    assert shared["warehouses"] == [{"name": "Main", "prefix": "C001"}]
    assert shared["csv_mappings"] == {"positions": {"sig": {"sku": 0}}}


def test_save_shared_settings_is_a_noop_without_a_configured_shared_folder(tmp_path):
    local_path = tmp_path / "settings.json"

    save_shared_settings({"shared_folder": "", "warehouses": [{"name": "Main", "prefix": "C001"}]}, local_path)

    assert not local_path.exists()
