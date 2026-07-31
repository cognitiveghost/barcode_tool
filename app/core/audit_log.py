from __future__ import annotations

import csv
import getpass
from datetime import datetime, timezone
from pathlib import Path

LOG_COLUMNS = ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]

_RISKY_LEADING_CHARS = ("=", "+", "-", "@")


def _escape_csv_formula(value: str) -> str:
    # Prefix with a quote so spreadsheet apps (Excel, LibreOffice) treat a
    # leading =/+/-/@ as literal text instead of executing it as a formula.
    if value.startswith(_RISKY_LEADING_CHARS):
        return f"'{value}"
    return value


def append_print_log(
    log_path: Path,
    mode: str,
    warehouse_prefix: str,
    count: int,
    description: str,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: unlocked check-then-append on a shared-network-folder file;
    # concurrent printers from two machines can race on the header write or
    # interleave rows. Add file locking if concurrent printing becomes real.
    is_new_file = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(LOG_COLUMNS)
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                getpass.getuser(),
                mode,
                _escape_csv_formula(warehouse_prefix),
                count,
                _escape_csv_formula(description),
            ]
        )
