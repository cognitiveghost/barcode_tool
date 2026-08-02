from __future__ import annotations

import re

NUMBER_WIDTH = 3
NUMBER_MAX = 10**NUMBER_WIDTH - 1


def format_position_code(corridor: str, number: str, height: str = "") -> str:
    if not corridor.isascii():
        raise ValueError("corridor must contain only ASCII characters (Code128 can't encode this)")
    if not number.isdigit():
        raise ValueError("number must be digits")
    if int(number) > NUMBER_MAX:
        raise ValueError(f"position numbers must be at most {NUMBER_MAX}")
    if height and (len(height) != 1 or not height.isascii()):
        raise ValueError("height must be a single ASCII character")
    return f"{corridor}{number.zfill(NUMBER_WIDTH)}{height}"


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

    return [
        format_position_code(corridor, str(number), height)
        for number in range(start, end + 1)
        for height in heights
    ]


def codes_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[str], list[int]]:
    codes: list[str] = []
    skipped_rows: list[int] = []
    for row_number, row in enumerate(rows, start=1):
        position_code = (row.get("position_code") or "").strip()
        try:
            if position_code:
                if not position_code.isascii():
                    raise ValueError("position code must be ASCII")
                codes.append(position_code)
            else:
                corridor = (row.get("corridor") or "").strip()
                number = (row.get("number") or "").strip()
                height = (row.get("height") or "").strip()
                codes.append(format_position_code(corridor, number, height))
        except ValueError:
            skipped_rows.append(row_number)
    return codes, skipped_rows


_POSITION_CODE_PATTERN = re.compile(r"[A-Za-z][0-9]+[A-Za-z]?")


def parse_position_code(code: str) -> tuple[str, str, str]:
    if not _POSITION_CODE_PATTERN.fullmatch(code):
        raise ValueError(
            f"position code {code!r} must be a letter, digits, and an "
            "optional trailing letter (e.g. H011A)"
        )
    corridor = code[0]
    height = code[-1] if code[-1].isalpha() else ""
    number = code[1:-1] if height else code[1:]
    if int(number) > NUMBER_MAX:
        raise ValueError(f"position numbers must be at most {NUMBER_MAX}")
    return corridor, number, height


def display_position_code(code: str) -> str:
    """Operator-facing position: corridor - number - height, e.g. "D-002-E".

    Free-form codes imported from CSV may not parse; they are shown as-is
    rather than dropped, since the barcode still carries the real payload.
    """
    try:
        corridor, number, height = parse_position_code(code)
    except ValueError:
        return code.upper()
    parts = [corridor, number.zfill(NUMBER_WIDTH)] + ([height] if height else [])
    return "-".join(parts).upper()
