from __future__ import annotations

import codecs
import csv
import io
from pathlib import Path


def _decode_csv_bytes(data: bytes, path: Path) -> tuple[str, str]:
    # BOM sniff first: a UTF-16 BOM must be caught before falling through to
    # cp1251, which (being a single-byte encoding covering nearly all 256
    # values) rarely raises and would otherwise silently decode UTF-16's
    # interleaved NUL bytes into mojibake instead of an error.
    if data[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        # A BOM is an unambiguous, explicit signal - if the bytes after it
        # aren't valid UTF-16, the file is truncated/corrupt, not some other
        # encoding to keep guessing at. Fail clearly here rather than
        # falling through to cp1251, which would misdecode it silently.
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError as error:
            raise ValueError(
                f"{path.name}: has a UTF-16 byte-order mark but is not valid "
                f"UTF-16 ({error}). The file may be truncated or corrupted."
            ) from error
    try:
        return data.decode("utf-8-sig"), "utf-8-sig"  # handles a UTF-8 BOM or plain UTF-8
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1251"), "cp1251"
    except UnicodeDecodeError as error:
        raise ValueError(
            f"{path.name}: could not decode as UTF-8, UTF-16, or CP1251 "
            f"({error}). Re-export the file as UTF-8, or pick its encoding "
            "manually."
        ) from error


def _sniff_delimiter(text: str) -> str:
    sample = text[:2048]  # a representative sample is enough for Sniffer
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","  # Sniffer raises on a single-column or ambiguous sample


def read_csv(
    path: Path,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
) -> tuple[list[str], list[list[str]], str, str]:
    """Returns (header, rows, delimiter_used, encoding_used).

    Both delimiter and encoding are auto-detected when not given explicitly;
    passing either lets a caller override a wrong guess without re-reading
    the file from scratch differently.
    """
    data = path.read_bytes()
    if encoding is not None:
        text = data.decode(encoding)
        encoding_used = encoding
    else:
        text, encoding_used = _decode_csv_bytes(data, path)

    delimiter_used = delimiter if delimiter is not None else _sniff_delimiter(text)

    all_rows = list(csv.reader(io.StringIO(text), delimiter=delimiter_used))
    if not all_rows:
        return [], [], delimiter_used, encoding_used
    return all_rows[0], all_rows[1:], delimiter_used, encoding_used


def apply_mapping(
    header: list[str],
    rows: list[list[str]],
    mapping: dict[str, str | None],
) -> list[dict[str, str]]:
    column_indexes = {
        field: header.index(column) if column in header else None
        for field, column in mapping.items()
    }

    mapped_rows = []
    for row in rows:
        mapped_row = {}
        for field, index in column_indexes.items():
            mapped_row[field] = row[index] if index is not None and index < len(row) else ""
        mapped_rows.append(mapped_row)
    return mapped_rows
