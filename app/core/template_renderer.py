from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from blabel import LabelWriter
from PIL import Image

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "templates" / "examples"


@dataclass(frozen=True)
class TemplatePreset:
    name: str
    mode: str
    width_mm: float
    height_mm: float
    template_path: Path
    stylesheet_path: Path


def list_presets(shared_folder: Path, mode: str) -> list[TemplatePreset]:
    mode_dir = Path(shared_folder) / "templates" / mode
    if not mode_dir.exists() or not any(mode_dir.iterdir()):
        _seed_examples(mode_dir, mode)

    presets = []
    for preset_dir in sorted(p for p in mode_dir.iterdir() if p.is_dir()):
        meta_path = preset_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        presets.append(
            TemplatePreset(
                name=meta["name"],
                mode=mode,
                width_mm=meta["width_mm"],
                height_mm=meta["height_mm"],
                template_path=preset_dir / "template.html",
                stylesheet_path=preset_dir / "style.css",
            )
        )
    return presets


def _seed_examples(mode_dir: Path, mode: str) -> None:
    example_dir = EXAMPLES_ROOT / mode / "default"
    if not example_dir.exists():
        return
    target_dir = mode_dir / "default"
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("template.html", "style.css", "meta.json"):
        (target_dir / filename).write_text(
            (example_dir / filename).read_text(encoding="utf-8"), encoding="utf-8"
        )


def render_records(
    preset: TemplatePreset,
    records: list[dict],
    dpi: int = 203,
) -> list[Image.Image]:
    writer = LabelWriter(
        str(preset.template_path),
        default_stylesheets=(str(preset.stylesheet_path),),
        items_per_page=1,
    )
    pdf_bytes = writer.write_labels(records, target="@memory")

    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    for page in pdf:
        bitmap = page.render(scale=dpi / 72)
        images.append(bitmap.to_pil().convert("RGB"))
    return images
