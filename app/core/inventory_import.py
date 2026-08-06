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
    ("quantity", "Quantity (optional, defaults to 1)"),
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
    quantity: int = 1


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
            # Some WMS exports carry expiry and batch combined in a single
            # "Exp/Bat" column (e.g. "2027-03/4471"). The operator maps both
            # the expiry and batch fields to that same source column in the
            # CSV import dialog - an explicit, deliberate signal, unlike the
            # old "split on / whenever one side is empty" heuristic that got
            # deleted for shredding real dates like "2026/08/02". Split on
            # the last "/" so a date that itself contains slashes still
            # comes out intact on the left. Some rows in that combined column
            # have no batch at all (just a bare date, e.g. "1-Jan") - without
            # a "/" there is nothing to split, so batch must be cleared
            # rather than left duplicating the expiry value.
            if expiry and expiry == batch:
                if "/" in expiry:
                    expiry, batch = expiry.rsplit("/", 1)
                    expiry, batch = expiry.strip(), batch.strip()
                else:
                    batch = ""

            quantity_raw = (row.get("quantity") or "").strip()
            if quantity_raw:
                try:
                    quantity = int(quantity_raw)
                except ValueError:
                    raise ValueError("quantity must be a positive whole number") from None
                if quantity <= 0:
                    raise ValueError("quantity must be a positive whole number")
            else:
                quantity = 1

            items.append(
                InventoryItem(
                    sku=sku,
                    name=(row.get("name") or "").strip(),
                    batch=batch,
                    expiry=expiry,
                    position_code=position_code,
                    client=(row.get("client") or "").strip(),
                    quantity=quantity,
                )
            )
        except ValueError as error:
            skipped_rows.append(SkippedRow(row_number, str(error)))
    return items, skipped_rows
