import json
import re
from pathlib import Path

import pytest

from app.core.template_renderer import (
    EXAMPLES_ROOT,
    TemplatePreset,
    find_thermal_black_block,
)
from tests.test_template_renderer import INVENTORY_RECORD, POSITION_RECORD

PX_PER_MM = 203 / 25.4

THERMAL_FOLDERS = [
    pytest.param(folder, id=f"{mode}/{folder.name}")
    for mode in ("positions", "inventory")
    for folder in sorted((EXAMPLES_ROOT / mode).iterdir())
    if (folder / "meta.json").exists()
]

SHORT_POSITION = {**POSITION_RECORD, "visible_text": "A-1", "user_text": "W"}
SHORT_INVENTORY = {
    **INVENTORY_RECORD,
    "sku": "W8",
    "name": "M",
    "client": "W",
    "batch": "8",
    "expiry": "8",
    "position_code": "H-1",
}


def _preset(folder: Path) -> TemplatePreset:
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return TemplatePreset(
        name=meta["name"],
        mode=folder.parent.name,
        width_mm=meta["width_mm"],
        height_mm=meta["height_mm"],
        template_path=folder / "template.html",
        stylesheet_path=folder / "style.css",
    )


def _records(mode: str) -> list[dict]:
    if mode == "positions":
        return [POSITION_RECORD, SHORT_POSITION]
    return [INVENTORY_RECORD, SHORT_INVENTORY]


@pytest.mark.parametrize("folder", THERMAL_FOLDERS)
def test_shipped_thermal_preset_has_no_black_block(folder):
    preset = _preset(folder)
    found = find_thermal_black_block(preset, _records(preset.mode))
    message = ""
    if found is not None:
        index, x, y = found
        message = (
            f"{preset.mode}/{folder.name}: solid black block at record {index}, "
            f"x={x / PX_PER_MM:.1f} mm, y={y / PX_PER_MM:.1f} mm"
        )
    assert found is None, message


@pytest.mark.parametrize("folder", THERMAL_FOLDERS)
def test_shipped_thermal_css_has_no_black_background(folder):
    css = (folder / "style.css").read_text(encoding="utf-8")
    assert not re.search(r"background(-color)?\s*:\s*(#000\b|#000000\b|black\b)", css, re.IGNORECASE)
