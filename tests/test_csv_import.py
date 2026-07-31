import csv

from app.core.csv_import import apply_mapping, read_csv


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_read_csv_returns_header_and_rows(tmp_path):
    path = tmp_path / "positions.csv"
    _write_csv(path, [
        ["Corridor", "Number", "Height"],
        ["H", "029", "A"],
        ["H", "030", "B"],
    ])

    header, rows = read_csv(path)

    assert header == ["Corridor", "Number", "Height"]
    assert rows == [["H", "029", "A"], ["H", "030", "B"]]


def test_read_csv_empty_file_returns_empty_header_and_rows(tmp_path):
    path = tmp_path / "empty.csv"
    _write_csv(path, [])

    header, rows = read_csv(path)

    assert header == []
    assert rows == []


def test_apply_mapping_builds_dicts_by_target_field():
    header = ["Corridor", "Number", "Height"]
    rows = [["H", "029", "A"], ["H", "030", "B"]]
    mapping = {"corridor": "Corridor", "number": "Number", "height": "Height"}

    result = apply_mapping(header, rows, mapping)

    assert result == [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": "B"},
    ]


def test_apply_mapping_unmapped_field_is_empty_string():
    header = ["Corridor", "Number"]
    rows = [["H", "029"]]
    mapping = {"corridor": "Corridor", "number": "Number", "height": None}

    result = apply_mapping(header, rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_missing_column_name_is_empty_string():
    header = ["Corridor", "Number"]
    rows = [["H", "029"]]
    mapping = {"corridor": "Corridor", "number": "Number", "height": "Nonexistent"}

    result = apply_mapping(header, rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_short_row_resolves_to_empty_string():
    header = ["Corridor", "Number", "Height"]
    rows = [["H", "029"]]  # missing the Height cell
    mapping = {"corridor": "Corridor", "number": "Number", "height": "Height"}

    result = apply_mapping(header, rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_read_csv_decodes_cp1251_cyrillic_content(tmp_path):
    path = tmp_path / "cyrillic.csv"
    path.write_bytes("sku,client\r\nSKU1,Клиент\r\n".encode("cp1251"))

    header, rows = read_csv(path)

    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Клиент"]]


def test_read_csv_strips_utf8_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("﻿sku,client\r\nSKU1,Acme\r\n".encode("utf-8"))

    header, rows = read_csv(path)

    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Acme"]]
