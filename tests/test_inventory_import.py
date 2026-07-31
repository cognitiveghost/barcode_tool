from app.core.inventory_import import InventoryItem, items_from_csv_rows


def test_items_from_csv_rows_builds_items_with_position_code_column():
    rows = [
        {
            "sku": "SKU1",
            "name": "Widget",
            "batch": "4471",
            "expiry": "2027-03",
            "position_code": "H011A",
        },
    ]

    items, skipped = items_from_csv_rows(rows)

    assert items == [
        InventoryItem(sku="SKU1", name="Widget", batch="4471", expiry="2027-03", position_code="H011A")
    ]
    assert skipped == []


def test_items_from_csv_rows_builds_position_from_components():
    rows = [{"sku": "SKU1", "corridor": "H", "number": "11", "height": "A"}]

    items, skipped = items_from_csv_rows(rows)

    assert items[0].position_code == "H011A"
    assert skipped == []


def test_items_from_csv_rows_optional_fields_default_empty():
    rows = [{"sku": "SKU1", "position_code": "H011A"}]

    items, skipped = items_from_csv_rows(rows)

    assert items[0].name == ""
    assert items[0].batch == ""
    assert items[0].expiry == ""


def test_items_from_csv_rows_skips_missing_sku():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "", "position_code": "H012A"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.sku for item in items] == ["SKU1"]
    assert skipped == [2]


def test_items_from_csv_rows_skips_malformed_position_code():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU2", "position_code": "not-a-position"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.sku for item in items] == ["SKU1"]
    assert skipped == [2]


def test_items_from_csv_rows_keeps_multiple_positions_for_same_sku():
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU1", "position_code": "H014B"},
    ]

    items, skipped = items_from_csv_rows(rows)

    assert [item.position_code for item in items] == ["H011A", "H014B"]
    assert skipped == []
