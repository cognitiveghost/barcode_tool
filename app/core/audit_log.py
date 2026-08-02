from __future__ import annotations

import csv
import getpass
import os
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from app.core.config import atomic_write_text, sanitize_filename_component

LOG_COLUMNS = ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]

_RISKY_LEADING_CHARS = ("=", "+", "-", "@")


def _escape_csv_formula(value: str) -> str:
    # Prefix with a quote so spreadsheet apps (Excel, LibreOffice) treat a
    # leading =/+/-/@ as literal text instead of executing it as a formula.
    if value.startswith(_RISKY_LEADING_CHARS):
        return f"'{value}"
    return value


def append_print_log(
    shared_folder: Path,
    mode: str,
    warehouse_prefix: str,
    count: int,
    description: str,
) -> None:
    audit_dir = Path(shared_folder) / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    user = sanitize_filename_component(getpass.getuser())
    filename = f"{timestamp:%Y%m%dT%H%M%S.%f}Z_{user}_{os.getpid()}.csv"

    with (audit_dir / filename).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(LOG_COLUMNS)
        writer.writerow(
            [
                timestamp.isoformat(),
                getpass.getuser(),
                mode,
                _escape_csv_formula(warehouse_prefix),
                count,
                _escape_csv_formula(description),
            ]
        )


def consolidate_audit_log(shared_folder: Path) -> int:
    """Merge every per-print audit file into one audit_log.csv.

    Returns the number of rows merged. Safe to call repeatedly - already
    consolidated rows are preserved, and successfully merged source files are
    deleted so a later call never double-counts them.
    """
    shared_folder = Path(shared_folder)
    audit_dir = shared_folder / "audit"
    per_file_paths = sorted(audit_dir.glob("*.csv")) if audit_dir.exists() else []
    if not per_file_paths:
        return 0

    consolidated_path = shared_folder / "audit_log.csv"
    existing_rows: list[list[str]] = []
    if consolidated_path.exists():
        existing_rows = list(csv.reader(consolidated_path.read_text(encoding="utf-8").splitlines()))[1:]

    new_rows: list[list[str]] = []
    for path in per_file_paths:
        rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
        new_rows.extend(rows[1:])  # skip each source file's own header

    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(LOG_COLUMNS)
    writer.writerows(existing_rows)
    writer.writerows(new_rows)
    atomic_write_text(consolidated_path, buffer.getvalue())

    for path in per_file_paths:
        path.unlink(missing_ok=True)

    return len(new_rows)
