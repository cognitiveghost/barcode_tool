from __future__ import annotations

from dataclasses import dataclass

from app.core.position_generator import (
    SkippedRow,
    format_position_code,
    parse_position_code,
)

INVENTORY_CSV_FIELDS = [
    ("sku", "SKU (required)"),
    ("name", "Product name"),
    ("client", "Client (optional)"),
    ("batch", "Batch (optional)"),
    ("expiry", "Expiry (optional)"),
    ("position_code", "Position code (overrides corridor/number/height)"),
    ("corridor", "Corridor"),
    ("number", "Number"),
    ("height", "Height (optional)"),
]


@dataclass
class InventoryItem:
    sku: str
    name: str
    batch: str
    expiry: str
    position_code: str
    client: str = ""


def items_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[InventoryItem], list[SkippedRow]]:
    items: list[InventoryItem] = []
    skipped_rows: list[SkippedRow] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            sku = (row.get("sku") or "").strip()
            if not sku:
                raise ValueError("sku is required")

            position_code = (row.get("position_code") or "").strip()
            if not position_code:
                position_code = format_position_code(
                    (row.get("corridor") or "").strip(),
                    (row.get("number") or "").strip(),
                    (row.get("height") or "").strip(),
                )
            corridor, number, height = parse_position_code(position_code)
            position_code = format_position_code(corridor, number, height)

            expiry = (row.get("expiry") or "").strip()
            batch = (row.get("batch") or "").strip()

            items.append(
                InventoryItem(
                    sku=sku,
                    name=(row.get("name") or "").strip(),
                    batch=batch,
                    expiry=expiry,
                    position_code=position_code,
                    client=(row.get("client") or "").strip(),
                )
            )
        except ValueError as error:
            skipped_rows.append(SkippedRow(row_number, str(error)))
    return items, skipped_rows
