from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SETTINGS = {
    "shared_folder": "",
    "default_printer": "",
    "print_mode": "driver",
    "raw_zpl_target": "",
    "warehouses": [],
}


def default_settings_path() -> Path:
    return Path.home() / ".barcode_tool" / "settings.json"


def load_settings(path: Path) -> dict:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
