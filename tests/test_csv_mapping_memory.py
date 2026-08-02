from app.core.csv_mapping_memory import (
    MAX_REMEMBERED_LAYOUTS,
    auto_map_fields,
    header_signature,
    recall_mapping,
    remember_mapping,
)


def test_signature_ignores_case_and_surrounding_whitespace():
    assert header_signature([" SKU ", "Name"]) == header_signature(["sku", "name"])


def test_signature_is_order_sensitive():
    assert header_signature(["sku", "name"]) != header_signature(["name", "sku"])


def test_remember_then_recall_round_trips():
    settings = {"csv_mappings": {}}
    header = ["sku", "name"]

    remember_mapping(settings, "inventory", header, {"sku": 0, "name": 1})

    assert recall_mapping(settings, "inventory", header) == {"sku": 0, "name": 1}


def test_recall_returns_none_for_an_unseen_layout():
    settings = {"csv_mappings": {}}
    remember_mapping(settings, "inventory", ["sku"], {"sku": 0})

    assert recall_mapping(settings, "inventory", ["totally", "different"]) is None


def test_recall_is_scoped_per_mode():
    settings = {"csv_mappings": {}}
    remember_mapping(settings, "inventory", ["sku"], {"sku": 0})

    assert recall_mapping(settings, "positions", ["sku"]) is None


def test_unmapped_fields_are_not_stored():
    settings = {"csv_mappings": {}}

    remember_mapping(settings, "inventory", ["sku", "name"], {"sku": 0, "name": None})

    assert recall_mapping(settings, "inventory", ["sku", "name"]) == {"sku": 0}


def test_oldest_layout_is_evicted_past_the_cap():
    settings = {"csv_mappings": {}}
    for i in range(MAX_REMEMBERED_LAYOUTS + 1):
        remember_mapping(settings, "inventory", [f"col{i}"], {"sku": 0})

    stored = settings["csv_mappings"]["inventory"]
    assert len(stored) == MAX_REMEMBERED_LAYOUTS
    assert header_signature(["col0"]) not in stored
    assert header_signature([f"col{MAX_REMEMBERED_LAYOUTS}"]) in stored


def test_re_remembering_a_layout_does_not_grow_the_store():
    settings = {"csv_mappings": {}}
    remember_mapping(settings, "inventory", ["sku"], {"sku": 0})
    remember_mapping(settings, "inventory", ["sku"], {"sku": 1})

    assert settings["csv_mappings"]["inventory"] == {header_signature(["sku"]): {"sku": 1}}


def test_missing_csv_mappings_key_is_tolerated():
    assert recall_mapping({}, "inventory", ["sku"]) is None


def test_auto_map_matches_exact_normalized_field_name():
    assert auto_map_fields(["Corridor", "Number"], ["corridor", "number", "height"]) == {
        "corridor": 0, "number": 1, "height": None,
    }


def test_auto_map_matches_via_synonym_table():
    assert auto_map_fields(["code", "lot"], ["sku", "batch"]) == {"sku": 0, "batch": 1}


def test_auto_map_leaves_unrecognized_fields_unmapped():
    assert auto_map_fields(["mystery_column"], ["sku"]) == {"sku": None}


def test_auto_map_is_case_and_whitespace_insensitive():
    assert auto_map_fields(["  SKU  "], ["sku"]) == {"sku": 0}
