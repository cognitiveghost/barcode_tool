import pytest

from app.core.position_generator import generate_position_codes


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


def test_zero_padding_matches_input_width():
    codes = generate_position_codes("H", "005", "006")
    assert codes == ["H005", "H006"]
