from __future__ import annotations

import csv
import io
from pathlib import Path


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1251")
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        return [], []
    return all_rows[0], all_rows[1:]


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
