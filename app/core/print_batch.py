from __future__ import annotations

import logging
import shutil
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.core.audit_log import append_print_log
from app.core.config import LOGGER_NAME, sanitize_filename_component
from app.core.config import shared_folder as resolve_shared_folder
from app.core.print_service import printer_display, send_to_printer
from app.core.template_renderer import TemplatePreset

DEFAULT_ARCHIVE_RETENTION_DAYS = 90

_ARCHIVE_FILENAME_PATTERN = re.compile(r"^\d{8}_\d{6}_\d{6}_.+\.pdf$")

logger = logging.getLogger(LOGGER_NAME)


@dataclass
class BatchResult:
    count: int
    archive_path: Path | None
    warnings: list[str] = field(default_factory=list)


def print_batch(
    images: list[Image.Image],
    preset: TemplatePreset,
    settings: dict,
    *,
    mode: str,
    warehouse_prefix: str,
    description: str,
    copies: int = 1,
    output_pdf_path: Path | None = None,
) -> BatchResult:
    if not images:
        raise ValueError("Nothing to print - generate labels first")
    if not warehouse_prefix:
        raise ValueError("No warehouse selected - add one in Settings first")
    if preset is None:
        raise ValueError(
            "No label template selected - check the shared folder's templates directory"
        )
    if copies < 1:
        raise ValueError("copies must be at least 1")

    printer = printer_display(settings)
    logger.info(
        "Print requested: mode=%s preset=%s printer=%s warehouse=%s count=%d copies=%d description=%r",
        mode, preset.name, printer, warehouse_prefix, len(images), copies, description,
    )

    try:
        if output_pdf_path is not None:
            # An explicit output path is a one-shot export (e.g. "Save as PDF"):
            # copies doesn't apply to a file, and there is exactly one render.
            send_to_printer(
                images,
                width_mm=preset.width_mm,
                height_mm=preset.height_mm,
                settings=settings,
                output_pdf_path=output_pdf_path,
            )
        else:
            for _ in range(copies):
                send_to_printer(
                    images,
                    width_mm=preset.width_mm,
                    height_mm=preset.height_mm,
                    settings=settings,
                    output_pdf_path=None,
                )
    except Exception:
        logger.exception("Print failed: mode=%s preset=%s printer=%s", mode, preset.name, printer)
        raise

    folder = resolve_shared_folder(settings)
    total_count = len(images) * copies
    warnings: list[str] = []
    archive_path: Path | None = _archive_path(folder, mode, warehouse_prefix, description)

    try:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if output_pdf_path is not None:
            # The export IS the PDF already - copy it, never re-render it.
            # (This is the double-render bug the plan calls out: the old
            # per-panel code called send_to_printer twice - once to the
            # caller's output path, once again to build the archive copy.)
            shutil.copy2(output_pdf_path, archive_path)
        else:
            send_to_printer(
                images,
                width_mm=preset.width_mm,
                height_mm=preset.height_mm,
                settings=settings,
                output_pdf_path=archive_path,
            )
    except OSError as error:
        message = f"Labels printed, but the PDF archive failed: {error}. Do not reprint this batch."
        logger.warning(message)
        warnings.append(message)
        archive_path = None

    try:
        append_print_log(
            folder,
            mode=mode,
            warehouse_prefix=warehouse_prefix,
            count=total_count,
            description=description,
            preset=preset.name,
            printer=printer,
        )
    except OSError as error:
        message = f"Labels printed, but the audit log entry failed: {error}. Do not reprint this batch."
        logger.warning(message)
        warnings.append(message)

    return BatchResult(count=total_count, archive_path=archive_path, warnings=warnings)


def _archive_path(folder: Path, mode: str, warehouse_prefix: str, description: str) -> Path:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
    filename = (
        f"{timestamp}_{mode}_{sanitize_filename_component(warehouse_prefix)}"
        f"_{sanitize_filename_component(description)}.pdf"
    )
    return folder / "printed_pdfs" / now.strftime("%Y-%m") / filename


def prune_archive(settings: dict) -> int:
    """Delete archive PDFs older than archive_retention_days. Best-effort,
    never raises, and only ever touches files inside printed_pdfs/ whose
    name matches the pattern this module itself writes - a misconfigured
    shared_folder must never be able to delete something this app didn't
    create. Returns the number of files removed.
    """
    retention_days = settings.get("archive_retention_days", DEFAULT_ARCHIVE_RETENTION_DAYS)
    if not retention_days:  # 0 (or missing/None) means keep forever
        return 0

    printed_pdfs_dir = resolve_shared_folder(settings) / "printed_pdfs"
    if not printed_pdfs_dir.exists():
        return 0

    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    pruned = 0
    try:
        month_dirs = [p for p in printed_pdfs_dir.iterdir() if p.is_dir()]
    except OSError:
        return 0

    for month_dir in month_dirs:
        try:
            candidates = list(month_dir.glob("*.pdf"))
        except OSError:
            continue
        for pdf_path in candidates:
            if not _ARCHIVE_FILENAME_PATTERN.match(pdf_path.name):
                continue
            try:
                if pdf_path.stat().st_mtime < cutoff:
                    pdf_path.unlink()
                    pruned += 1
            except OSError:
                continue

    return pruned
