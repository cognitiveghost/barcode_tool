from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from app.core.print_batch import BatchResult
from app.core.template_renderer import TemplatePreset
from app.ui.print_preview_dialog import PrintPreviewDialog


def _app():
    return QApplication.instance() or QApplication([])


def _preset():
    return TemplatePreset(
        name="Test preset",
        mode="positions",
        width_mm=68,
        height_mm=38,
        template_path=Path("template.html"),
        stylesheet_path=Path("style.css"),
    )


def _dialog(count=3, on_confirm=None, render_calls=None):
    calls = render_calls if render_calls is not None else []

    def render_page(index):
        calls.append(index)
        return Image.new("RGB", (10, 10))

    return PrintPreviewDialog(
        count=count,
        render_page=render_page,
        preset=_preset(),
        settings={"default_printer": "HP-1"},
        warehouse_display="Main",
        on_confirm=on_confirm or (lambda copies, path: BatchResult(count=1, archive_path=None)),
    )


def test_shows_first_page_on_construction():
    _app()
    calls = []
    dialog = _dialog(count=5, render_calls=calls)

    assert calls == [0]
    assert dialog._page_indicator.text() == "1 / 5"


def test_only_the_viewed_page_is_ever_rendered():
    # The core requirement: a 1000-label batch must not render all 1000
    # just to show a preview.
    _app()
    calls = []
    _dialog(count=1000, render_calls=calls)

    assert calls == [0]


def test_next_button_advances_and_renders_that_page(monkeypatch):
    _app()
    calls = []
    dialog = _dialog(count=3, render_calls=calls)

    dialog._next_button.click()

    assert calls == [0, 1]
    assert dialog._page_indicator.text() == "2 / 3"
    assert dialog._prev_button.isEnabled()


def test_prev_and_next_disabled_at_the_boundaries():
    _app()
    dialog = _dialog(count=1)

    assert not dialog._prev_button.isEnabled()
    assert not dialog._next_button.isEnabled()


def test_print_button_calls_on_confirm_with_spinbox_copies_and_no_path():
    _app()
    received = []
    dialog = _dialog(on_confirm=lambda copies, path: (
        received.append((copies, path)),
        BatchResult(count=1, archive_path=None),
    )[1])
    dialog._copies_spin.setValue(3)

    dialog._on_print_clicked()

    assert received == [(3, None)]


def test_save_as_pdf_forces_copies_to_one(monkeypatch, tmp_path):
    _app()
    received = []
    dialog = _dialog(on_confirm=lambda copies, path: (
        received.append((copies, path)),
        BatchResult(count=1, archive_path=None),
    )[1])
    dialog._copies_spin.setValue(5)  # must be ignored for the PDF path
    chosen = str(tmp_path / "out.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (chosen, "")))

    dialog._on_save_as_pdf_clicked()

    assert received == [(1, Path(chosen))]


def test_save_as_pdf_does_nothing_when_the_file_dialog_is_cancelled(monkeypatch):
    _app()
    received = []
    dialog = _dialog(on_confirm=lambda copies, path: (
        received.append(True), BatchResult(count=1, archive_path=None)
    )[1])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    dialog._on_save_as_pdf_clicked()

    assert received == []


def test_confirm_failure_shows_warning_and_does_not_close(monkeypatch):
    _app()

    def _boom(copies, path):
        raise ValueError("no warehouse selected")

    dialog = _dialog(on_confirm=_boom)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    dialog._on_print_clicked()

    assert len(warnings) == 1
    assert warnings[0][1] == "Print failed"
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_confirm_success_with_warnings_shows_combined_message_and_closes(monkeypatch):
    _app()
    dialog = _dialog(on_confirm=lambda copies, path: BatchResult(
        count=1, archive_path=None,
        warnings=["Labels printed, but the audit log entry failed: boom. Do not reprint this batch."],
    ))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    dialog._on_print_clicked()

    assert len(warnings) == 1
    assert warnings[0][1] == "Printed with warnings"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_summary_shows_batch_details():
    _app()
    dialog = _dialog(count=7)

    text = dialog._summary_label.text()

    assert "7 labels" in text
    assert "68x38mm" in text
    assert "Test preset" in text
    assert "Main" in text
    assert "HP-1" in text


def test_construction_failure_propagates_instead_of_opening_a_broken_dialog():
    _app()

    def _boom(index):
        raise ValueError("template mismatch")

    with pytest.raises(ValueError):
        PrintPreviewDialog(
            count=3,
            render_page=_boom,
            preset=_preset(),
            settings={},
            warehouse_display="Main",
            on_confirm=lambda copies, path: BatchResult(count=1, archive_path=None),
        )


def test_navigation_failure_shows_warning_and_stays_on_the_current_page(monkeypatch):
    _app()

    def render_page(index):
        if index == 1:
            raise ValueError("boom")
        return Image.new("RGB", (10, 10))

    dialog = PrintPreviewDialog(
        count=3,
        render_page=render_page,
        preset=_preset(),
        settings={},
        warehouse_display="Main",
        on_confirm=lambda copies, path: BatchResult(count=1, archive_path=None),
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    dialog._next_button.click()

    assert len(warnings) == 1
    assert warnings[0][1] == "Preview failed"
    assert dialog._page_indicator.text() == "1 / 3"
    assert dialog._page_index == 0


def test_dialog_stays_open_when_print_is_cancelled():
    from app.core.print_batch import PrintCancelled

    _app()

    def _cancelled(copies, output_pdf_path):
        raise PrintCancelled()

    dialog = _dialog(on_confirm=_cancelled)

    dialog._confirm(1, None)

    assert dialog.result() != QDialog.DialogCode.Accepted
