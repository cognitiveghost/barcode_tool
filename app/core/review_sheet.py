"""Sort, merge and group inventory records into the A4 review sheet context. No Qt."""

from __future__ import annotations

import re
from itertools import groupby

SHEET_COLUMNS = {
    "num": "#",
    "sku": "SKU",
    "position": "Position",
    "name": "Name",
    "client": "Client",
    "batch": "Batch",
    "expiry": "Expiry",
    "qty": "Qty",
    "sku_qr": "SKU QR",
    "position_qr": "Position QR",
}
VIEWS = {"position": "By position", "sku": "By SKU"}
VIEW_KEY = {"position": "position", "sku": "sku"}


def pickable_columns(view: str) -> list[str]:
    return [key for key in SHEET_COLUMNS if key != VIEW_KEY[view]]


def _natural(value: str) -> list:
    # ponytail: casefold + digit runs, not full Unicode collation
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def build_sheet(records: list[dict], view: str, columns: list[str] | None) -> dict:
    allowed = pickable_columns(view)
    keys = allowed if columns is None else [k for k in SHEET_COLUMNS if k in columns and k in allowed]

    merged: dict[tuple, dict] = {}
    for record in records:
        # position_data too: two raw codes can share one display code but need their own QR
        key = (
            record["sku"],
            record["position_code"],
            record["position_data"],
            record["client"],
            record["batch"],
            record["expiry"],
        )
        if key in merged:
            merged[key]["qty"] += int(record["quantity"])
            continue
        merged[key] = {
            "sku": record["sku"],
            "name": record["name"],
            "client": record["client"],
            "batch": record["batch"],
            "expiry": record["expiry"],
            "position": record["position_code"],
            "position_data": record["position_data"],
            "qty": int(record["quantity"]),
        }

    if view == "position":
        fields = ("position", "sku", "batch", "expiry")
    else:
        fields = ("sku", "position", "batch", "expiry")
    # raw value after the natural key keeps equal-natural values contiguous for groupby
    rows = sorted(merged.values(), key=lambda row: [(_natural(row[f]), row[f]) for f in fields])

    group_field = VIEW_KEY[view]
    groups = []
    num = 0
    for raw_key, members in groupby(rows, key=lambda row: row[group_field]):
        members = list(members)
        for row in members:
            num += 1
            row["num"] = num
        if len(members) == 1:
            summary = ""
        else:
            parts = [f"{len(members)} rows"]
            if "qty" in keys:
                parts.append(f"qty {sum(row['qty'] for row in members)}")
            summary = " · ".join(parts)
        groups.append({"key": raw_key, "summary": summary, "rows": members})

    return {
        "view": view,
        "view_label": VIEWS[view],
        "key_label": SHEET_COLUMNS[VIEW_KEY[view]],
        "generated_date": records[0]["generated_date"] if records else "",
        "columns": [{"key": k, "label": SHEET_COLUMNS[k]} for k in keys],
        "groups": groups,
    }
