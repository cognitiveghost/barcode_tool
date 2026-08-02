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

    header, rows, _delimiter, _encoding = read_csv(path)

    assert header == ["Corridor", "Number", "Height"]
    assert rows == [["H", "029", "A"], ["H", "030", "B"]]


def test_read_csv_empty_file_returns_empty_header_and_rows(tmp_path):
    path = tmp_path / "empty.csv"
    _write_csv(path, [])

    header, rows, _delimiter, _encoding = read_csv(path)

    assert header == []
    assert rows == []


def test_apply_mapping_builds_dicts_by_target_field():
    rows = [["H", "029", "A"], ["H", "030", "B"]]
    mapping = {"corridor": 0, "number": 1, "height": 2}

    result = apply_mapping(rows, mapping)

    assert result == [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": "B"},
    ]


def test_apply_mapping_unmapped_field_is_empty_string():
    rows = [["H", "029"]]
    mapping = {"corridor": 0, "number": 1, "height": None}

    result = apply_mapping(rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_index_past_end_of_row_is_empty_string():
    rows = [["H", "029"]]  # missing the Height cell
    mapping = {"corridor": 0, "number": 1, "height": 2}

    result = apply_mapping(rows, mapping)

    assert result == [{"corridor": "H", "number": "029", "height": ""}]


def test_apply_mapping_resolves_duplicate_header_names_by_index():
    # header ['code', 'name', 'code'] used to resolve both 'code' fields to
    # column 0 via header.index(), so the third column was unreachable.
    rows = [["A1", "Widget", "B2"]]
    mapping = {"sku": 0, "name": 1, "alt_sku": 2}

    result = apply_mapping(rows, mapping)

    assert result == [{"sku": "A1", "name": "Widget", "alt_sku": "B2"}]


def test_read_csv_decodes_cp1251_cyrillic_content(tmp_path):
    path = tmp_path / "cyrillic.csv"
    path.write_bytes("sku,client\r\nSKU1,Клиент\r\n".encode("cp1251"))

    header, rows, _delimiter, _encoding = read_csv(path)

    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Клиент"]]


def test_read_csv_strips_utf8_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("﻿sku,client\r\nSKU1,Acme\r\n".encode())

    header, rows, _delimiter, _encoding = read_csv(path)

    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Acme"]]


def test_read_csv_detects_semicolon_delimiter(tmp_path):
    path = tmp_path / "semicolon.csv"
    path.write_bytes(
        "sku;name;position\r\nSKU1;Widget;H011A\r\n".encode("utf-8")
    )

    header, rows, delimiter, _encoding = read_csv(path)

    assert delimiter == ";"
    assert header == ["sku", "name", "position"]
    assert rows == [["SKU1", "Widget", "H011A"]]


def test_read_csv_detects_tab_delimiter(tmp_path):
    path = tmp_path / "tabbed.csv"
    path.write_bytes("sku\tname\r\nSKU1\tWidget\r\n".encode("utf-8"))

    header, rows, delimiter, _encoding = read_csv(path)

    assert delimiter == "\t"
    assert header == ["sku", "name"]


def test_read_csv_defaults_to_comma_when_sniffing_is_ambiguous(tmp_path):
    path = tmp_path / "single_column.csv"
    path.write_bytes(b"onlycolumn\r\nvalue1\r\nvalue2\r\n")

    header, rows, delimiter, _encoding = read_csv(path)

    assert delimiter == ","
    assert header == ["onlycolumn"]


def test_read_csv_explicit_delimiter_overrides_detection(tmp_path):
    # A comma-delimited file forced to parse as semicolon-delimited - proves
    # the override actually takes effect rather than being ignored.
    path = tmp_path / "positions.csv"
    path.write_bytes(b"sku,name\r\nSKU1,Widget\r\n")

    header, rows, delimiter, _encoding = read_csv(path, delimiter=";")

    assert delimiter == ";"
    assert header == ["sku,name"]  # the whole line is one column now


def test_read_csv_decodes_utf16_with_bom(tmp_path):
    # This is the exact bug report: Excel's "Unicode text" export is UTF-16LE
    # with a BOM, which used to decode under cp1251 into mojibake instead of
    # raising or being recognized.
    path = tmp_path / "utf16.csv"
    path.write_bytes("sku,client\r\nSKU1,Клиент\r\n".encode("utf-16"))

    header, rows, _delimiter, encoding = read_csv(path)

    assert encoding == "utf-16"
    assert header == ["sku", "client"]
    assert rows == [["SKU1", "Клиент"]]


def test_read_csv_raises_a_clear_error_for_a_corrupt_utf16_bom(tmp_path):
    # Verified by hand: b"\xff\xfe\x00\xd8A\x00" is a UTF-16LE BOM followed
    # by a lone (unpaired) high surrogate (U+D800) then a normal character -
    # data.decode("utf-16") raises UnicodeDecodeError("illegal UTF-16
    # surrogate") on this exact byte sequence. A BOM is present, so this
    # must hit the UTF-16 branch's own error path, not the cp1251 fallback.
    path = tmp_path / "garbage.csv"
    path.write_bytes(b"\xff\xfe\x00\xd8A\x00")

    import pytest
    with pytest.raises(ValueError, match="garbage.csv"):
        read_csv(path)


def test_read_csv_explicit_encoding_overrides_detection(tmp_path):
    path = tmp_path / "cyrillic.csv"
    path.write_bytes("sku,client\r\nSKU1,Клиент\r\n".encode("cp1251"))

    header, rows, _delimiter, encoding = read_csv(path, encoding="cp1251")

    assert encoding == "cp1251"
    assert rows == [["SKU1", "Клиент"]]
