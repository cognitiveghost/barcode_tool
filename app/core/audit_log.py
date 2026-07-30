from __future__ import annotations

import csv
import getpass
from datetime import datetime, timezone
from pathlib import Path

LOG_COLUMNS = ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]


def append_print_log(
    log_path: Path,
    mode: str,
    warehouse_prefix: str,
    count: int,
    description: str,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
                warehouse_prefix,
                count,
                description,
            ]
        )
