from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings

DEFAULT_SETTINGS = {
    "shared_folder": "",
    "default_printer": "",
    "print_mode": "driver",
    "raw_zpl_target": "",
    "warehouses": [],
    "csv_mappings": {},
    "archive_retention_days": 90,
}

LOGGER_NAME = "barcode_tool"

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def default_settings_path() -> Path:
    return Path.home() / ".barcode_tool" / "settings.json"


def shared_folder(settings: dict) -> Path:
    return Path(settings.get("shared_folder") or default_settings_path().parent)


def sanitize_filename_component(value: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", value)


def atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` without ever leaving a half-written file.

    Writes to a sibling `.tmp` file first, then `os.replace`s it into place -
    `os.replace` is atomic on both POSIX and Windows, so a reader on another
    machine on the same shared folder always sees either the old complete
    file or the new complete file, never a partial one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def _defaults() -> dict:
    # Deep copy via JSON: DEFAULT_SETTINGS holds a list and a dict, and
    # callers mutate what they get back (see test_save_then_load_roundtrip).
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def load_settings(path: Path, on_recovery: Callable[[str], None] | None = None) -> dict:
    settings = _defaults()
    if not path.exists():
        return settings

    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError(f"{path.name} does not contain a JSON object")
    except (OSError, ValueError) as error:
        corrupt_path = path.with_name(path.name + ".corrupt")
        try:
            path.replace(corrupt_path)
        except OSError:
            pass
        message = (
            f"{path.name} could not be read ({error}) and has been reset "
            f"to defaults. The previous file was saved as "
            f"{corrupt_path.name}."
        )
        logging.getLogger(LOGGER_NAME).warning(message)
        if on_recovery is not None:
            on_recovery(message)
        return settings

    settings.update(loaded)
    return settings


def save_settings(path: Path, settings: dict) -> None:
    atomic_write_text(path, json.dumps(settings, indent=2, ensure_ascii=False))


def qsettings() -> QSettings:
    # Window geometry is per-machine state. It must never go into
    # settings.json, which the operator may point at a shared folder.
    return QSettings("barcode_tool", "barcode_tool")
