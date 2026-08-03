from PySide6.QtWidgets import QApplication

from app.core.position_generator import SkippedRow
from app.ui.skipped_rows_dialog import SkippedRowsDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_dialog_shows_row_reason_and_raw_values():
    _app()
    skipped = [SkippedRow(2, "sku is required")]
    raw_rows = [{"sku": "SKU1"}, {"sku": "", "name": "Widget"}]

    dialog = SkippedRowsDialog(skipped, raw_rows)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "2"
    assert dialog.table.item(0, 1).text() == "sku is required"
    assert "Widget" in dialog.table.item(0, 2).text()


def test_copy_to_clipboard_includes_header_and_rows(monkeypatch):
    _app()
    skipped = [SkippedRow(1, "boom")]
    raw_rows = [{"sku": "X"}]
    dialog = SkippedRowsDialog(skipped, raw_rows)

    copied = []

    class FakeClipboard:
        def setText(self, text):
            copied.append(text)

    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: FakeClipboard()))

    dialog._copy_to_clipboard()

    assert len(copied) == 1
    assert "boom" in copied[0]
