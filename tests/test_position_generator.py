import pytest

from app.core.position_generator import (
    codes_from_csv_rows,
    format_position_code,
    generate_position_codes,
    parse_position_code,
)


def test_simple_range_no_height():
    codes = generate_position_codes("H", "029", "031")
    assert codes == ["H029", "H030", "H031"]


def test_range_with_height_range():
    codes = generate_position_codes("H", "029", "030", "A", "C")
    assert codes == [
        "H029A", "H029B", "H029C",
        "H030A", "H030B", "H030C",
    ]


def test_single_height():
    codes = generate_position_codes("H", "029", "029", "A")
    assert codes == ["H029A"]


def test_invalid_number_range_raises():
    with pytest.raises(ValueError):
        generate_position_codes("H", "090", "029")


def test_invalid_height_range_raises():
    with pytest.raises(ValueError):
        generate_position_codes("H", "029", "030", "F", "A")


def test_zero_padding_always_three_digits():
    codes = generate_position_codes("H", "005", "006")
    assert codes == ["H005", "H006"]


def test_short_input_is_padded_to_three_digits():
    assert generate_position_codes("H", "45", "45") == ["H045"]
    assert generate_position_codes("H", "5", "5") == ["H005"]


def test_number_above_max_raises_value_error():
    with pytest.raises(ValueError):
        generate_position_codes("H", "029", "1000")


def test_number_to_defaults_to_number_from():
    codes = generate_position_codes("H", "029")
    assert codes == ["H029"]


def test_non_ascii_corridor_raises_value_error():
    with pytest.raises(ValueError):
        generate_position_codes("Н", "029", "030")  # Cyrillic "Н", not Code128-safe


def test_non_ascii_height_raises_value_error():
    with pytest.raises(ValueError):
        generate_position_codes("H", "029", "030", "А", "А")  # Cyrillic "А"


def test_format_position_code_pads_and_combines():
    assert format_position_code("H", "29", "A") == "H029A"


def test_format_position_code_no_height():
    assert format_position_code("H", "29") == "H029"


def test_format_position_code_rejects_non_digit_number():
    with pytest.raises(ValueError):
        format_position_code("H", "abc")


def test_format_position_code_rejects_multi_letter_height():
    with pytest.raises(ValueError):
        format_position_code("H", "29", "AB")


def test_format_position_code_rejects_number_above_max():
    with pytest.raises(ValueError):
        format_position_code("H", "1000")


def test_codes_from_csv_rows_builds_codes_from_components():
    rows = [
        {"corridor": "H", "number": "029", "height": "A"},
        {"corridor": "H", "number": "030", "height": ""},
    ]

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["H029A", "H030"]
    assert skipped == []


def test_codes_from_csv_rows_prefers_position_code_when_present():
    rows = [{"position_code": "C001H099Z", "corridor": "X", "number": "1", "height": ""}]

    codes, _skipped = codes_from_csv_rows(rows)

    assert codes == ["C001H099Z"]


def test_codes_from_csv_rows_skips_invalid_rows_and_continues():
    rows = [
        {"corridor": "H", "number": "029", "height": ""},
        {"corridor": "H", "number": "not-a-number", "height": ""},
        {"corridor": "H", "number": "030", "height": ""},
    ]

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["H029", "H030"]
    assert skipped == [2]


def test_codes_from_csv_rows_handles_missing_keys():
    rows = [{"corridor": "H", "number": "029"}]  # no "height" key at all

    codes, skipped = codes_from_csv_rows(rows)

    assert codes == ["H029"]
    assert skipped == []


def test_parse_position_code_with_height():
    assert parse_position_code("H011A") == ("H", "011", "A")


def test_parse_position_code_without_height():
    assert parse_position_code("H011") == ("H", "011", "")


def test_parse_position_code_rejects_missing_number():
    with pytest.raises(ValueError):
        parse_position_code("H")


def test_parse_position_code_rejects_multi_letter_corridor():
    with pytest.raises(ValueError):
        parse_position_code("HH011A")


def test_parse_position_code_rejects_malformed_string():
    with pytest.raises(ValueError):
        parse_position_code("not-a-position")


def test_parse_position_code_rejects_number_above_max():
    with pytest.raises(ValueError):
        parse_position_code("H1000")


def test_parse_position_code_rejects_trailing_newline():
    with pytest.raises(ValueError):
        parse_position_code("H011A\n")


def test_parse_position_code_rejects_non_ascii_digits():
    with pytest.raises(ValueError):
        parse_position_code("H٠١١A")  # Arabic-Indic digits, not "011"
