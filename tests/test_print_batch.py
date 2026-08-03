import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import LOGGER_NAME
from app.core.print_batch import print_batch, prune_archive
from app.core.template_renderer import TemplatePreset


@pytest.fixture
def log_records():
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _preset() -> TemplatePreset:
    return TemplatePreset(
        name="Test", mode="positions", width_mm=40, height_mm=30,
        template_path=Path("unused"), stylesheet_path=Path("unused"),
    )


def _settings(tmp_path) -> dict:
    return {"shared_folder": str(tmp_path), "print_mode": "driver", "default_printer": ""}


def test_raises_on_empty_batch(tmp_path):
    with pytest.raises(ValueError, match="Nothing to print"):
        print_batch([], _preset(), _settings(tmp_path), mode="positions",
                     warehouse_prefix="C001", description="H029")


def test_raises_when_no_warehouse_prefix(tmp_path):
    with pytest.raises(ValueError, match="warehouse"):
        print_batch(["fake-image"], _preset(), _settings(tmp_path), mode="positions",
                     warehouse_prefix="", description="H029")


def test_raises_when_preset_is_none(tmp_path):
    with pytest.raises(ValueError, match="template"):
        print_batch(["fake-image"], None, _settings(tmp_path), mode="positions",
                     warehouse_prefix="C001", description="H029")


def test_raises_when_copies_below_one(tmp_path):
    with pytest.raises(ValueError, match="copies"):
        print_batch(["fake-image"], _preset(), _settings(tmp_path), mode="positions",
                     warehouse_prefix="C001", description="H029", copies=0)


def test_successful_print_archives_and_logs_with_no_warnings(monkeypatch, tmp_path):
    # The real send_to_printer writes an actual PDF to disk whenever it's
    # given an output_pdf_path (see print_service.print_labels); the fake
    # here must do the same so the archive-file assertions below reflect
    # real behavior instead of the fake being a no-op.
    calls = []

    def _fake_send_to_printer(images, **kwargs):
        path = kwargs.get("output_pdf_path")
        calls.append(path)
        if path is not None:
            Path(path).write_bytes(b"fake-pdf")

    monkeypatch.setattr("app.core.print_batch.send_to_printer", _fake_send_to_printer)

    result = print_batch(["img1", "img2"], _preset(), _settings(tmp_path), mode="positions",
                          warehouse_prefix="C001", description="H029..H030")

    assert result.warnings == []
    assert result.count == 2
    assert result.archive_path is not None
    assert result.archive_path.exists()
    # One physical-print call (output_pdf_path=None) + one archive call.
    assert calls == [None, result.archive_path]
    assert result.archive_path.parent.name == datetime.now(timezone.utc).strftime("%Y-%m")


def test_archive_path_is_named_from_mode_prefix_and_description(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda images, **kwargs: None)

    result = print_batch(["img1"], _preset(), _settings(tmp_path), mode="inventory",
                          warehouse_prefix="C001", description="SKU1, SKU2")

    assert "inventory" in result.archive_path.name
    assert "C001" in result.archive_path.name
    # A comma and space in the description are not safe filename characters.
    assert "SKU1, SKU2" not in result.archive_path.name
    assert "SKU1_ SKU2" in result.archive_path.name or "SKU1__SKU2" in result.archive_path.name


def test_output_pdf_path_renders_exactly_once_and_archive_is_a_copy(monkeypatch, tmp_path):
    # Regression test for the double-render bug: an explicit output path
    # must be rendered once and copied to the archive, never re-rendered.
    render_calls = []

    def _fake_send_to_printer(images, **kwargs):
        render_calls.append(kwargs.get("output_pdf_path"))
        path = kwargs.get("output_pdf_path")
        if path is not None:
            Path(path).write_bytes(b"FAKE-PDF-CONTENT")

    monkeypatch.setattr("app.core.print_batch.send_to_printer", _fake_send_to_printer)
    export_path = tmp_path / "export.pdf"

    result = print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                          warehouse_prefix="C001", description="H029",
                          output_pdf_path=export_path)

    assert render_calls == [export_path]  # exactly one render call, not two
    assert result.archive_path.read_bytes() == b"FAKE-PDF-CONTENT"


def test_copies_repeats_the_physical_print_but_archives_once(monkeypatch, tmp_path):
    render_calls = []
    monkeypatch.setattr(
        "app.core.print_batch.send_to_printer",
        lambda images, **kwargs: render_calls.append(kwargs.get("output_pdf_path")),
    )

    result = print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                          warehouse_prefix="C001", description="H029", copies=3)

    # 3 physical-print calls (output_pdf_path=None) + 1 archive call.
    assert render_calls.count(None) == 3
    assert len([c for c in render_calls if c is not None]) == 1
    assert result.count == 3  # audit/result count reflects copies


def test_archive_failure_is_a_warning_not_an_exception(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda images, **kwargs: None)
    # Make the archive's parent directory uncreatable by occupying its path
    # with a file instead of a directory.
    (tmp_path / "printed_pdfs").write_text("occupied by a file, not a directory")

    result = print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                          warehouse_prefix="C001", description="H029")

    assert result.archive_path is None
    assert len(result.warnings) == 1
    assert "archive" in result.warnings[0].lower()


def test_audit_log_failure_is_a_warning_not_an_exception(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda images, **kwargs: None)

    def _boom(*args, **kwargs):
        raise OSError("share unavailable")

    monkeypatch.setattr("app.core.print_batch.append_print_log", _boom)

    result = print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                          warehouse_prefix="C001", description="H029")

    assert result.archive_path is not None  # archiving still succeeded
    assert len(result.warnings) == 1
    assert "audit log" in result.warnings[0].lower()


def test_both_archive_and_audit_failing_reports_both_warnings(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda images, **kwargs: None)
    (tmp_path / "printed_pdfs").write_text("occupied")

    def _boom(*args, **kwargs):
        raise OSError("share unavailable")

    monkeypatch.setattr("app.core.print_batch.append_print_log", _boom)

    result = print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                          warehouse_prefix="C001", description="H029")

    assert len(result.warnings) == 2


def test_successful_print_logs_a_line_with_parameters(monkeypatch, tmp_path, log_records):
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda images, **kwargs: None)

    print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                warehouse_prefix="C001", description="H029")

    message = next(r.getMessage() for r in log_records if "Print requested" in r.getMessage())
    assert "Test" in message  # preset name
    assert "positions" in message
    assert "C001" in message


def test_print_failure_is_logged_and_still_raises(monkeypatch, tmp_path, log_records):
    def _boom(images, **kwargs):
        raise OSError("printer offline")

    monkeypatch.setattr("app.core.print_batch.send_to_printer", _boom)

    with pytest.raises(OSError, match="printer offline"):
        print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                     warehouse_prefix="C001", description="H029")

    assert any("Print failed" in r.getMessage() for r in log_records)


def test_print_batch_passes_preset_name_and_printer_to_the_audit_log(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.print_batch.send_to_printer", lambda images, **kwargs: None)
    captured = {}
    monkeypatch.setattr(
        "app.core.print_batch.append_print_log",
        lambda *args, **kwargs: captured.update(kwargs),
    )

    print_batch(["img1"], _preset(), _settings(tmp_path), mode="positions",
                warehouse_prefix="C001", description="H029")

    assert captured["preset"] == "Test"
    assert captured["printer"] == "(system default)"


def _make_archive_file(base: Path, month: str, filename: str, age_days: int) -> Path:
    path = base / "printed_pdfs" / month / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"pdf")
    mtime = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
    import os
    os.utime(path, (mtime, mtime))
    return path


def test_prune_archive_removes_files_older_than_retention(tmp_path):
    old = _make_archive_file(
        tmp_path, "2020-01", "20200101_000000_000000_positions_C001_H029.pdf", age_days=200
    )
    new = _make_archive_file(
        tmp_path, "2020-01", "20200102_000000_000000_positions_C001_H030.pdf", age_days=1
    )

    pruned = prune_archive({"shared_folder": str(tmp_path), "archive_retention_days": 90})

    assert pruned == 1
    assert not old.exists()
    assert new.exists()


def test_prune_archive_zero_retention_days_keeps_everything(tmp_path):
    old = _make_archive_file(
        tmp_path, "2020-01", "20200101_000000_000000_positions_C001_H029.pdf", age_days=500
    )

    pruned = prune_archive({"shared_folder": str(tmp_path), "archive_retention_days": 0})

    assert pruned == 0
    assert old.exists()


def test_prune_archive_never_deletes_a_file_not_matching_its_own_naming(tmp_path):
    stray = _make_archive_file(tmp_path, "2020-01", "readme.pdf", age_days=500)

    pruned = prune_archive({"shared_folder": str(tmp_path), "archive_retention_days": 90})

    assert pruned == 0
    assert stray.exists()


def test_prune_archive_with_no_printed_pdfs_dir_returns_zero(tmp_path):
    assert prune_archive({"shared_folder": str(tmp_path), "archive_retention_days": 90}) == 0
