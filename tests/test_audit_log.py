import csv

from app.core.audit_log import append_print_log, consolidate_audit_log


def test_append_creates_one_file_per_call(tmp_path):
    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=2, description="H029-H030")

    audit_files = list((tmp_path / "audit").glob("*.csv"))
    assert len(audit_files) == 1
    rows = list(csv.reader(audit_files[0].read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["timestamp", "user", "mode", "warehouse_prefix", "count", "description"]
    assert rows[1][2:] == ["positions", "C001", "2", "H029-H030"]


def test_append_twice_creates_two_separate_files(tmp_path):
    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=1, description="H029")
    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=1, description="H030")

    audit_files = list((tmp_path / "audit").glob("*.csv"))
    assert len(audit_files) == 2


def test_leading_formula_characters_are_escaped(tmp_path):
    append_print_log(
        tmp_path, mode="positions", warehouse_prefix="=C001", count=1, description="=SUM(A1)"
    )

    audit_files = list((tmp_path / "audit").glob("*.csv"))
    rows = list(csv.reader(audit_files[0].read_text(encoding="utf-8").splitlines()))
    assert rows[1][3] == "'=C001"
    assert rows[1][5] == "'=SUM(A1)"


def test_consolidate_merges_all_per_file_rows_and_removes_sources(tmp_path):
    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=1, description="H029")
    append_print_log(tmp_path, mode="inventory", warehouse_prefix="C001", count=2, description="SKU1, SKU2")

    merged = consolidate_audit_log(tmp_path)

    assert merged == 2
    assert list((tmp_path / "audit").glob("*.csv")) == []
    rows = list(csv.reader((tmp_path / "audit_log.csv").read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 3  # header + 2 rows


def test_consolidate_appends_to_an_existing_consolidated_file(tmp_path):
    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=1, description="H029")
    consolidate_audit_log(tmp_path)

    append_print_log(tmp_path, mode="positions", warehouse_prefix="C001", count=1, description="H030")
    merged = consolidate_audit_log(tmp_path)

    assert merged == 1
    rows = list(csv.reader((tmp_path / "audit_log.csv").read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 3  # header + 2 total rows across both consolidations


def test_consolidate_with_nothing_to_merge_returns_zero(tmp_path):
    assert consolidate_audit_log(tmp_path) == 0
    assert not (tmp_path / "audit_log.csv").exists()
