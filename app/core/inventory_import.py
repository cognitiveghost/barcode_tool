from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.position_generator import (
    SkippedRow,
    format_position_code,
    parse_position_code,
)

_DATE_FORMATS = (
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d.%m.%y",
    "%Y/%m",
    "%Y-%m",
    "%m/%Y",
    "%m.%Y",
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


def _is_date(value: str) -> bool:
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
        except ValueError:
            continue
        return True
    return False


def _split_expiry_batch(value: str) -> tuple[str, str]:
    """Split a combined Exp/Bat value into (expiry, batch).

    A bare date stays whole. Otherwise split on the last "/" only when the
    left side is a date and the right side is not ("2027-03/4471"). Anything
    else is all expiry with no batch ("1-Jan", "ABC/123").
    """
    if _is_date(value):
        return value, ""
    if "/" in value:
        left, right = value.rsplit("/", 1)
        if _is_date(left) and not _is_date(right):
            return left.strip(), right.strip()
    return value, ""


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
            # CSV import dialog - an explicit, deliberate signal.
            if expiry and expiry == batch:
                expiry, batch = _split_expiry_batch(expiry)

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
