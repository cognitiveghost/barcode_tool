from __future__ import annotations

from dataclasses import dataclass

from app.core.position_generator import format_position_code, parse_position_code

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


def _split_combined_expiry_batch(expiry: str, batch: str) -> tuple[str, str]:
    if not batch and "/" in expiry:
        parts = expiry.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    if not expiry and "/" in batch:
        parts = batch.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    return expiry, batch


def items_from_csv_rows(rows: list[dict[str, str]]) -> tuple[list[InventoryItem], list[int]]:
    items: list[InventoryItem] = []
    skipped_rows: list[int] = []
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
            parse_position_code(position_code)

            expiry, batch = _split_combined_expiry_batch(
                (row.get("expiry") or "").strip(),
                (row.get("batch") or "").strip(),
            )

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
        except ValueError:
            skipped_rows.append(row_number)
    return items, skipped_rows
