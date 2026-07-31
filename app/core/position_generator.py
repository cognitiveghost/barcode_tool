from __future__ import annotations

NUMBER_WIDTH = 3
NUMBER_MAX = 10**NUMBER_WIDTH - 1


def generate_position_codes(
    corridor: str,
    number_from: str,
    number_to: str | None = None,
    height_from: str | None = None,
    height_to: str | None = None,
) -> list[str]:
    if number_to is None:
        number_to = number_from
    if not number_from.isdigit() or not number_to.isdigit():
        raise ValueError("number_from and number_to must be digits")
    if not corridor.isascii():
        raise ValueError("corridor must contain only ASCII characters (Code128 can't encode this)")

    start, end = int(number_from), int(number_to)
    if start > NUMBER_MAX or end > NUMBER_MAX:
        raise ValueError(f"position numbers must be at most {NUMBER_MAX}")
    if start > end:
        raise ValueError("number_from must be <= number_to")

    heights: list[str] = [""]
    if height_from is not None:
        if height_to is None:
            height_to = height_from
        if len(height_from) != 1 or len(height_to) != 1:
            raise ValueError("height letters must be single characters")
        if not height_from.isascii() or not height_to.isascii():
            raise ValueError("height letters must be ASCII characters (Code128 can't encode this)")
        if height_from > height_to:
            raise ValueError("height_from must be <= height_to")
        heights = [chr(c) for c in range(ord(height_from), ord(height_to) + 1)]

    codes = []
    for number in range(start, end + 1):
        padded = str(number).zfill(NUMBER_WIDTH)
        for height in heights:
            codes.append(f"{corridor}{padded}{height}")
    return codes
