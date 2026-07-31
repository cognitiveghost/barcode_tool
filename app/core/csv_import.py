from __future__ import annotations

import csv
from pathlib import Path


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        all_rows = list(csv.reader(f))
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
