from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import jinja2
import pypdfium2 as pdfium
from blabel import LabelWriter
from blabel.Blabel import write_pdf as _blabel_write_pdf
from PIL import Image

from app.core import label_tools
from app.core.config import LOGGER_NAME, atomic_write_text

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "templates" / "examples"
FONT_CSS = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "fonts.css"

# The label heads in the field are 203 dpi, so rendering at 203 maps one
# image pixel to one dot - no resampling anywhere between here and the head.
# Thermal heads are bilevel, so the greyscale render is thresholded here
# rather than left for the driver to dither.
DEFAULT_DPI = 203

SEEDED_FILES = ("template.html", "style.css", "meta.json")

logger = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True)
class TemplatePreset:
    name: str
    mode: str
    width_mm: float
    height_mm: float
    template_path: Path
    stylesheet_path: Path


_seeded_mode_dirs: set[str] = set()


def list_presets(shared_folder: Path, mode: str) -> list[TemplatePreset]:
    mode_dir = Path(shared_folder) / "templates" / mode
    # ponytail: seeds each mode_dir once per process instead of on every
    # panel construction and every settings save - cuts the repeated
    # multi-file-op cost against a possibly-slow shared folder. Does NOT
    # make the first seed non-blocking: a genuinely offline share still
    # stalls MainWindow construction once per process, since this runs
    # before the Qt event loop starts. Upgrade path: defer the first seed
    # via a background thread or QTimer.singleShot once the panels no
    # longer need presets populated synchronously in their own unit tests.
    key = str(mode_dir)
    if key not in _seeded_mode_dirs:
        _seed_examples(mode_dir, mode)
        _seeded_mode_dirs.add(key)

    if not mode_dir.exists():
        return []

    try:
        preset_dirs = sorted(p for p in mode_dir.iterdir() if p.is_dir())
    except OSError as error:
        # A shared folder that goes unreadable between the mkdir above and
        # here must degrade to "no presets found", not crash app startup.
        logger.warning("Could not list templates in %s: %s", mode_dir, error)
        return []

    presets = []
    for preset_dir in preset_dirs:
        meta_path = preset_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            preset = TemplatePreset(
                name=meta["name"],
                mode=mode,
                width_mm=meta["width_mm"],
                height_mm=meta["height_mm"],
                template_path=preset_dir / "template.html",
                stylesheet_path=preset_dir / "style.css",
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            # These files are hand-edited in a folder several machines share.
            # One typo must cost that preset, not everyone else's app launch.
            logger.warning("Skipping invalid preset %s: %s", preset_dir, error)
            continue
        presets.append(preset)
    return presets


def _seed_examples(mode_dir: Path, mode: str) -> None:
    """Refresh the app-owned example presets from the shipped examples.

    Rewritten on every call so shipped template fixes reach folders seeded by
    an older build. Customisations belong in a sibling folder, which is never
    touched - the seeded README says so, as do the file headers.

    Best-effort: a read-only or offline shared folder must not stop the app
    from listing the presets that are already there.
    """
    examples_for_mode = EXAMPLES_ROOT / mode
    if not examples_for_mode.exists():
        return
    try:
        for example_dir in sorted(p for p in examples_for_mode.iterdir() if p.is_dir()):
            target_dir = mode_dir / example_dir.name
            target_dir.mkdir(parents=True, exist_ok=True)
            for filename in SEEDED_FILES:
                _write_if_changed(
                    target_dir / filename, (example_dir / filename).read_text(encoding="utf-8")
                )
        _write_if_changed(
            mode_dir / "README.txt", (EXAMPLES_ROOT / "README.txt").read_text(encoding="utf-8")
        )
    except OSError as error:
        logger.warning("Could not seed example templates into %s: %s", mode_dir, error)
        return


def _write_if_changed(path: Path, content: str) -> None:
    # write_text truncates first, so an unchanged rewrite is a window where a
    # second machine reading this shared folder sees a half-written file.
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    atomic_write_text(path, content)


def render_records(
    preset: TemplatePreset,
    records: list[dict],
    dpi: int = DEFAULT_DPI,
) -> list[Image.Image]:
    writer = LabelWriter(
        str(preset.template_path),
        default_stylesheets=(str(FONT_CSS), str(preset.stylesheet_path)),
        items_per_page=1,
        encoding="utf-8",
        label_tools=label_tools,
    )
    pdf_bytes = writer.write_labels(records, target="@memory")

    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    for page in pdf:
        bitmap = page.render(scale=dpi / 72, grayscale=True)
        images.append(bitmap.to_pil().convert("1", dither=Image.Dither.NONE))

    if images:
        _check_aspect_ratio(preset, images[0])

    return images


def render_table_pdf(preset: TemplatePreset, records: list[dict]) -> bytes:
    """Render every record onto one template as a single vector PDF.

    Unlike render_records, this is not one-record-per-page: the whole list
    is handed to the template at once (as `records`) so it can build a real
    HTML table that WeasyPrint paginates natively across A4 sheets. There is
    no pdfium/bitmap step, so a multi-page report stays sharp instead of
    being rasterised at thermal-head resolution.
    """
    template = jinja2.Template(preset.template_path.read_text(encoding="utf-8"))
    html = template.render(records=records, label_tools=label_tools)
    return _blabel_write_pdf(
        html, target="@memory", extra_stylesheets=(str(FONT_CSS), str(preset.stylesheet_path))
    )


def _check_aspect_ratio(preset: TemplatePreset, image: Image.Image) -> None:
    meta_ratio = preset.width_mm / preset.height_mm
    rendered_ratio = image.width / image.height
    if abs(rendered_ratio - meta_ratio) / meta_ratio > 0.01:
        raise ValueError(
            f"Template '{preset.name}' meta.json size "
            f"({preset.width_mm}x{preset.height_mm}mm) does not match the "
            "rendered page size from the template's CSS @page rule - "
            "check that meta.json and style.css agree."
        )
