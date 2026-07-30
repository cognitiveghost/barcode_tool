import csv

from app.core.audit_log import append_print_log


def test_append_creates_file_with_header_and_row(tmp_path):
    log_path = tmp_path / "audit.csv"

    append_print_log(log_path, mode="positions", warehouse_prefix="C001", count=2, description="H029-H030")

    with log_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]
    assert rows[1][2:] == ["positions", "C001", "2", "H029-H030"]


def test_append_twice_adds_second_row_without_duplicate_header(tmp_path):
    log_path = tmp_path / "audit.csv"

    append_print_log(log_path, mode="positions", warehouse_prefix="C001", count=1, description="H029")
    append_print_log(log_path, mode="positions", warehouse_prefix="C001", count=1, description="H030")

    with log_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert len(rows) == 3
    assert rows.count(
        ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]
    ) == 1
