from app.core.review_sheet import build_sheet, pickable_columns


def rec(sku, pos, qty="1", batch="", expiry="", client="", name="N"):
    return {
        "sku": sku,
        "name": name,
        "client": client,
        "batch": batch,
        "expiry": expiry,
        "position_code": pos,
        "position_data": f"C001{pos}",
        "generated_date": "2026/10/28",
        "quantity": qty,
    }


def test_identical_rows_merge_and_sum_qty():
    sheet = build_sheet([rec("A", "H-001-A", "3"), rec("A", "H-001-A", "4")], "position", None)

    rows = [row for group in sheet["groups"] for row in group["rows"]]
    assert len(rows) == 1
    assert rows[0]["qty"] == 7


def test_rows_with_different_batch_stay_separate():
    sheet = build_sheet(
        [rec("A", "H-001-A", batch="B1"), rec("A", "H-001-A", batch="B2")], "position", None
    )

    rows = [row for group in sheet["groups"] for row in group["rows"]]
    assert len(rows) == 2


def test_position_view_sorts_naturally_and_groups_by_position():
    sheet = build_sheet(
        [rec("B", "H-10-A"), rec("A", "H-9-A"), rec("B", "H-9-A")], "position", None
    )

    assert [group["key"] for group in sheet["groups"]] == ["H-9-A", "H-10-A"]
    assert [row["sku"] for row in sheet["groups"][0]["rows"]] == ["A", "B"]


def test_sku_view_sorts_case_insensitively_and_groups_by_sku():
    sheet = build_sheet([rec("SKU-C", "H-001-A"), rec("sku-b", "H-001-A"), rec("SKU-A", "H-001-A")], "sku", None)

    assert [group["key"] for group in sheet["groups"]] == ["SKU-A", "sku-b", "SKU-C"]


def test_num_runs_across_groups():
    sheet = build_sheet(
        [rec("A", "H-001-A"), rec("A", "H-001-A", batch="X"), rec("B", "H-002-A")], "position", None
    )

    nums = [row["num"] for group in sheet["groups"] for row in group["rows"]]
    assert nums == [1, 2, 3]


def test_columns_follow_sheet_order_and_drop_unknown_and_view_key():
    sheet = build_sheet([rec("A", "H-001-A")], "position", ["qty", "sku", "bogus", "position", "num"])

    assert [column["key"] for column in sheet["columns"]] == ["num", "sku", "qty"]


def test_none_columns_means_all_pickable():
    assert [c["key"] for c in build_sheet([rec("A", "H-001-A")], "position", None)["columns"]] == pickable_columns(
        "position"
    )
    assert [c["key"] for c in build_sheet([rec("A", "H-001-A")], "sku", None)["columns"]] == pickable_columns("sku")
    assert "sku" not in pickable_columns("sku")
    assert "position" not in pickable_columns("position")


def test_summary():
    one = build_sheet([rec("A", "H-001-A", "5")], "position", None)
    assert one["groups"][0]["summary"] == ""

    three = [rec("A", "H-001-A", "1", batch="1"), rec("A", "H-001-A", "2", batch="2"), rec("A", "H-001-A", "3", batch="3")]
    with_qty = build_sheet(three, "position", ["sku", "qty"])
    assert with_qty["groups"][0]["summary"] == "3 rows · qty 6"

    without_qty = build_sheet(three, "position", ["sku"])
    assert without_qty["groups"][0]["summary"] == "3 rows"


def test_empty_records():
    sheet = build_sheet([], "position", None)

    assert sheet["groups"] == []
    assert sheet["generated_date"] == ""
