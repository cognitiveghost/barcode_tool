import csv
import json
import re
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from app.core import print_service
from app.core.print_batch import BatchResult
from app.ui.mode_inventory_panel import (
    TABLE_COLUMNS,
    InventoryModePanel,
    _describe_skus,
)

SETTINGS = {
    "warehouses": [{"name": "Main", "prefix": "C001"}],
}


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings_dir(monkeypatch, tmp_path):
    # Prevents the shared_folder="" fallback path from touching the real
    # ~/.barcode_tool directory (and seeding example templates into it)
    # during tests.
    monkeypatch.setattr(
        "app.core.config.default_settings_path",
        lambda: tmp_path / "settings.json",
    )


def _write_preset(
    shared_folder: Path, slug: str, name: str, width_mm: float, height_mm: float
) -> None:
    preset_dir = Path(shared_folder) / "templates" / "inventory" / slug
    preset_dir.mkdir(parents=True)
    (preset_dir / "meta.json").write_text(
        json.dumps({"name": name, "width_mm": width_mm, "height_mm": height_mm})
    )
    (preset_dir / "template.html").write_text(
        '<div><img src="{{ label_tools.qr_code(sku) }}"><div>{{ name }}</div></div>'
    )
    (preset_dir / "style.css").write_text(
        f"@page {{ size: {width_mm}mm {height_mm}mm; margin: 0; }}"
    )


def test_load_items_populates_table():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "name": "Widget", "position_code": "H011A"},
        {"sku": "SKU2", "name": "Gadget", "position_code": "H012A"},
    ]

    items = panel.load_items(rows)

    assert [item.sku for item in items] == ["SKU1", "SKU2"]
    assert panel.items_table.rowCount() == 2
    assert panel.items_table.item(0, 1).text() == "SKU1"
    assert panel.result_label.text() == "2 items imported"


def test_data_cells_are_not_editable():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    for column in range(1, len(TABLE_COLUMNS)):
        cell = panel.items_table.item(0, column)
        assert not (cell.flags() & Qt.ItemFlag.ItemIsEditable)


def test_load_items_reports_skipped_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "", "position_code": "H012A"},
    ]

    panel.load_items(rows)

    assert "1 item imported" in panel.result_label.text()
    assert "1 row skipped" in panel.result_label.text()
    assert "show details" in panel.result_label.text()


def test_skipped_rows_link_opens_detail_dialog(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "", "position_code": "H012A"},
    ]
    panel.load_items(rows)

    opened = []

    class FakeDialog:
        def __init__(self, skipped_rows, raw_rows, parent=None):
            opened.append((skipped_rows, raw_rows))

        def exec(self):
            return None

    monkeypatch.setattr("app.ui.mode_inventory_panel.SkippedRowsDialog", FakeDialog)

    panel.result_label.linkActivated.emit("#")

    assert len(opened) == 1
    assert len(opened[0][0]) == 1
    assert opened[0][1] == rows


def test_load_items_raises_when_no_valid_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    rows = [{"sku": "", "position_code": "H011A"}]

    with pytest.raises(ValueError):
        panel.load_items(rows)


def test_rows_are_checked_by_default():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    assert panel.checked_items()[0].sku == "SKU1"


def test_select_none_then_select_all():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )

    panel.select_none_button.click()
    assert panel.checked_items() == []

    panel.select_all_button.click()
    assert [item.sku for item in panel.checked_items()] == ["SKU1", "SKU2"]


def test_unchecking_one_row_excludes_it_from_checked_items():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )

    panel.items_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)

    assert [item.sku for item in panel.checked_items()] == ["SKU2"]


def test_import_csv_button_opens_dialog_and_loads_items(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    fake_rows = [{"sku": "SKU1", "position_code": "H011A"}]

    class FakeDialog:
        def __init__(self, fields, parent=None, **kwargs):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return fake_rows

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert [item.sku for item in panel.items] == ["SKU1"]


def test_import_csv_button_does_nothing_when_dialog_cancelled(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None, **kwargs):
            pass

        def exec(self):
            return False

        def get_mapped_rows(self):
            raise AssertionError("should not be called when the dialog is cancelled")

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)

    panel.import_csv_button.click()

    assert panel.items == []


def test_import_csv_button_shows_warning_when_no_valid_rows(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)

    class FakeDialog:
        def __init__(self, fields, parent=None, **kwargs):
            pass

        def exec(self):
            return True

        def get_mapped_rows(self):
            return [{"sku": "", "position_code": "H011A"}]

    monkeypatch.setattr("app.ui.mode_inventory_panel.CsvImportDialog", FakeDialog)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.import_csv_button.click()

    assert len(warnings) == 1


def test_refresh_from_settings_rebuilds_combos(tmp_path):
    _app()
    _write_preset(tmp_path, "a", "80x80mm", 80, 80)
    panel = InventoryModePanel(SETTINGS)

    panel.refresh_from_settings(
        {
            "warehouses": [{"name": "Second", "prefix": "C002"}],
            "shared_folder": str(tmp_path),
        }
    )

    warehouse_names = [panel.warehouse_combo.itemText(i) for i in range(panel.warehouse_combo.count())]
    preset_names = [panel.preset_combo.itemText(i) for i in range(panel.preset_combo.count())]
    assert warehouse_names == ["Second"]
    assert preset_names == ["80x80mm", "Default 150x100mm"]


def test_refresh_with_no_presets_does_not_crash_without_a_main_window(monkeypatch):
    _app()
    monkeypatch.setattr("app.ui.mode_inventory_panel.list_presets", lambda *a, **k: [])

    panel = InventoryModePanel(SETTINGS)  # constructed standalone, no QMainWindow

    assert panel.preset_combo.count() == 0


def test_refresh_shows_status_bar_warning_when_no_presets_found(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr("app.ui.mode_inventory_panel.list_presets", lambda *a, **k: [])
    window = QMainWindow()
    panel = InventoryModePanel(SETTINGS)
    window.setCentralWidget(panel)

    panel.refresh_from_settings({**SETTINGS, "shared_folder": str(tmp_path)})

    assert window.statusBar().currentMessage() != ""


def test_print_checked_items_writes_pdf_and_log(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {
                "sku": "SKU1",
                "name": "Widget",
                "batch": "4471",
                "expiry": "2027-03",
                "position_code": "H011A",
            },
            {"sku": "SKU2", "name": "Gadget", "position_code": "H012A"},
        ]
    )

    pdf_path = tmp_path / "out.pdf"
    panel.print_checked_items(output_pdf_path=pdf_path)

    assert pdf_path.exists()
    audit_files = list((tmp_path / "audit").glob("*.csv"))
    assert len(audit_files) == 1
    rows = list(csv.reader(audit_files[0].read_text(encoding="utf-8").splitlines()))
    assert len(rows) == 2  # header + one entry
    assert rows[1][2:] == ["inventory", "C001", "2", "SKU1, SKU2"]


def test_print_checked_items_creates_a_not_yet_existing_shared_folder(tmp_path):
    _app()
    shared_folder = tmp_path / "not_yet_created" / "nested"
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(shared_folder)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items(output_pdf_path=tmp_path / "explicit.pdf")

    assert len(list(shared_folder.glob("printed_pdfs/*/*.pdf"))) == 1
    assert len(list(shared_folder.glob("audit/*.csv"))) == 1


def test_print_checked_items_archives_a_pdf_without_an_explicit_output_path(monkeypatch, tmp_path):
    _app()
    # Without an output path the physical print falls through to driver mode
    # and QPrinter binds the *system default printer*. On a Linux runner
    # there is none and Qt no-ops; on Windows it is "Microsoft Print to
    # PDF", which opens a modal Save As dialog and blocks the whole run.
    # Only the driver leg is stubbed - the archive render (which always has
    # its own explicit output_pdf_path) still exercises real Qt rendering.
    real_print_labels = print_service.print_labels
    monkeypatch.setattr(
        "app.core.print_service.print_labels",
        lambda images, width_mm, height_mm, **kwargs: (
            real_print_labels(images, width_mm, height_mm, **kwargs)
            if kwargs.get("output_pdf_path")
            else None
        ),
    )
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    panel.print_checked_items()

    archived = list(tmp_path.glob("printed_pdfs/*/*.pdf"))
    assert len(archived) == 1


def test_print_checked_items_skips_unchecked_rows(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {"sku": "SKU1", "position_code": "H011A"},
            {"sku": "SKU2", "position_code": "H012A"},
        ]
    )
    panel.items_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    audit_files = list((tmp_path / "audit").glob("*.csv"))
    log_lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert log_lines[1].split(",")[2:] == ["inventory", "C001", "1", "SKU1"]


def test_print_checked_items_raises_when_nothing_checked(tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])
    panel.select_none_button.click()

    with pytest.raises(ValueError):
        panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")


def test_print_checked_items_raises_without_warehouse():
    _app()
    settings = {"warehouses": []}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    with pytest.raises(ValueError):
        panel.print_checked_items()


def test_print_button_click_without_warehouse_shows_warning(monkeypatch):
    _app()
    settings = {"warehouses": []}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert len(warnings) == 1


def test_print_failure_reports_print_failed_and_skips_audit_log(monkeypatch, tmp_path):
    # Not a brief scenario: the button click now opens PrintPreviewDialog
    # rather than printing directly, so this OSError-propagation behavior is
    # exercised at the print_checked_items level (same pattern as
    # test_print_current_labels_skips_archive_when_send_to_printer_raises in
    # test_mode_positions_panel.py) - the button-click-shows-warning half of
    # this scenario is now covered generically by
    # test_confirm_failure_shows_warning_and_does_not_close in
    # test_print_preview_dialog.py.
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    def _boom(*a, **k):
        raise OSError("printer offline")

    monkeypatch.setattr("app.core.print_batch.send_to_printer", _boom)
    log_calls = []
    monkeypatch.setattr(
        "app.core.print_batch.append_print_log",
        lambda *a, **k: log_calls.append(True),
    )

    with pytest.raises(OSError):
        panel.print_checked_items()

    assert log_calls == []


def test_audit_log_failure_reports_a_warning_after_successful_print(monkeypatch, tmp_path):
    # See comment on test_print_failure_reports_print_failed_and_skips_audit_log
    # above - same reasoning, exercised at the print_checked_items level now.
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    print_calls = []

    def _log_boom(*a, **k):
        raise OSError("share unavailable")

    monkeypatch.setattr(
        "app.core.print_batch.send_to_printer",
        lambda *a, **k: print_calls.append(True),
    )
    monkeypatch.setattr("app.core.print_batch.append_print_log", _log_boom)

    result = panel.print_checked_items()

    assert print_calls == [True, True]  # physical print + archive render
    assert len(result.warnings) == 1
    assert "audit log" in result.warnings[0].lower()


def test_describe_skus_dedupes_repeated_sku():
    assert _describe_skus(["SKU1", "SKU2", "SKU1"]) == "SKU1, SKU2"


def test_describe_skus_caps_long_lists():
    skus = [f"SKU{i}" for i in range(7)]
    assert _describe_skus(skus) == "SKU0, SKU1, SKU2, SKU3, SKU4 +2 more"


def test_print_button_click_opens_preview_dialog_wired_to_print_checked_items(monkeypatch, tmp_path):
    _app()
    _write_preset(tmp_path, "a", "40x30mm", 40, 30)
    settings = {**SETTINGS, "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    calls = []

    class FakeDialog:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def exec(self):
            return True

    monkeypatch.setattr("app.ui.mode_inventory_panel.PrintPreviewDialog", FakeDialog)

    panel.print_button.click()

    assert len(calls) == 1
    assert calls[0]["count"] == 1
    assert calls[0]["on_confirm"] == panel.print_checked_items


def test_print_button_shows_warning_when_preview_dialog_construction_fails(monkeypatch, tmp_path):
    _app()
    _write_preset(tmp_path, "a", "40x30mm", 40, 30)
    settings = {**SETTINGS, "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    def _boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr("app.ui.mode_inventory_panel.PrintPreviewDialog", _boom)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()  # must not raise

    assert len(warnings) == 1
    assert warnings[0][1] == "Print failed"


def test_print_button_click_without_items_shows_warning(monkeypatch):
    _app()
    panel = InventoryModePanel(SETTINGS)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    panel.print_button.click()

    assert len(warnings) == 1


def test_checked_items_survive_sorting():
    # checked_items() used to map table row -> self.items[row]; sorting the view
    # would have printed labels for whichever items happened to land on the
    # checked rows.
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "ZZZ", "position_code": "H011A"},
        {"sku": "AAA", "position_code": "H012A"},
    ])
    panel._set_all_checked(False)
    panel.items_table.item(0, 0).setCheckState(Qt.CheckState.Checked)  # ZZZ

    panel.items_table.sortItems(1, Qt.SortOrder.AscendingOrder)

    assert [item.sku for item in panel.checked_items()] == ["ZZZ"]


def test_filter_hides_non_matching_rows():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "WIDGET1", "position_code": "H011A"},
        {"sku": "GADGET2", "position_code": "H012A"},
    ])

    panel.filter_edit.setText("widget")

    assert not panel.items_table.isRowHidden(0)
    assert panel.items_table.isRowHidden(1)


def test_hidden_rows_are_still_printed_if_checked():
    # Filtering is a view concern. Silently dropping checked-but-filtered items
    # would be the same class of bug as the sorting one.
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "WIDGET1", "position_code": "H011A"},
        {"sku": "GADGET2", "position_code": "H012A"},
    ])

    panel.filter_edit.setText("widget")

    assert len(panel.checked_items()) == 2


def test_selection_count_updates_live():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([
        {"sku": "SKU1", "position_code": "H011A"},
        {"sku": "SKU2", "position_code": "H012A"},
    ])

    panel._set_all_checked(False)

    assert panel.selection_label.text() == "0 of 2 selected"


def test_client_column_populated_from_item():
    _app()
    panel = InventoryModePanel(SETTINGS)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A", "client": "Acme Corp"}])

    client_column = TABLE_COLUMNS.index("Client")
    assert panel.items_table.item(0, client_column).text() == "Acme Corp"


def test_print_checked_items_passes_generated_date_as_yyyy_mm_dd(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "position_code": "H011A"}])

    render_calls = []

    def _fake_render(preset, records, **kwargs):
        render_calls.append(records)
        return [Image.new("RGB", (10, 10)) for _ in records]

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_records", _fake_render)
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda *a, **k: None)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    generated_date = render_calls[0][0]["generated_date"]
    assert re.fullmatch(r"\d{4}/\d{2}/\d{2}", generated_date)


def test_print_checked_items_passes_structured_fields_to_renderer(monkeypatch, tmp_path):
    _app()
    settings = {**SETTINGS, "default_printer": "", "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items(
        [
            {
                "sku": "SKU1",
                "name": "Widget",
                "client": "Acme Corp",
                "batch": "4471",
                "expiry": "2027-03",
                "position_code": "H011A",
            }
        ]
    )

    render_calls = []

    def _fake_render(preset, records, **kwargs):
        render_calls.append(records)
        return [Image.new("RGB", (10, 10)) for _ in records]

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_records", _fake_render)
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda *a, **k: None)

    panel.print_checked_items(output_pdf_path=tmp_path / "out.pdf")

    record = render_calls[0][0]
    assert (
        record["sku"],
        record["name"],
        record["client"],
        record["batch"],
        record["expiry"],
        record["position_code"],
    ) == ("SKU1", "Widget", "Acme Corp", "4471", "2027-03", "H-011-A")
    assert record["position_data"] == "C001H011A"  # warehouse prefix + raw position_code


def test_print_preview_render_page_builds_the_same_record_shape(monkeypatch, tmp_path):
    _app()
    _write_preset(tmp_path, "a", "40x30mm", 40, 30)
    settings = {**SETTINGS, "shared_folder": str(tmp_path)}
    panel = InventoryModePanel(settings)
    panel.load_items([{"sku": "SKU1", "name": "Widget", "position_code": "H011A"}])

    render_calls = []

    def _fake_render(preset, records, **kwargs):
        render_calls.append(records)
        return [Image.new("RGB", (10, 10)) for _ in records]

    monkeypatch.setattr("app.ui.mode_inventory_panel.render_records", _fake_render)

    captured = {}

    class FakeDialog:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def exec(self):
            return True

    monkeypatch.setattr("app.ui.mode_inventory_panel.PrintPreviewDialog", FakeDialog)

    panel.print_button.click()
    captured["render_page"](0)

    record = render_calls[0][0]
    assert record["sku"] == "SKU1"
    assert record["name"] == "Widget"
    assert record["position_data"] == "C001H011A"
