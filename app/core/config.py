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
    "raw_zpl_rotate": False,
    "warehouses": [],
    "csv_mappings": {},
    "archive_retention_days": 90,
}

LOGGER_NAME = "barcode_tool"

# Kept in the shared folder's own settings.json so every PC pointed at the
# same shared folder sees the same warehouse codes and CSV mappings.
# Machine-specific settings (shared_folder itself, printer, print mode)
# stay in the local file only.
SHARED_SETTINGS_KEYS = ("warehouses", "csv_mappings")

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
            raise ValueError(f"{path.name} does not contain a JSON object")  # noqa: TRY004 (see except (OSError, ValueError) below)
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


def shared_settings_path(settings: dict, local_path: Path) -> Path:
    """Where warehouse codes and CSV mappings are synchronized: <shared
    folder>/settings.json. Returns `local_path` unchanged when no shared
    folder is configured, so callers can compare against it to detect the
    unconfigured case rather than guessing at a global fallback location."""
    folder = settings.get("shared_folder")
    return Path(folder) / "settings.json" if folder else local_path


def sync_shared_settings(settings: dict, local_path: Path) -> dict:
    """Overlay warehouses/csv_mappings from the shared folder's settings.json
    onto `settings`. The first time a shared folder is configured (no
    settings.json there yet), seeds it from this machine's current values
    instead of wiping them. No-op when no shared folder is configured."""
    path = shared_settings_path(settings, local_path)
    if path == local_path:
        return settings
    if path.exists():
        shared = load_settings(path)
        for key in SHARED_SETTINGS_KEYS:
            settings[key] = shared[key]
    else:
        save_shared_settings(settings, local_path)
    return settings


def save_shared_settings(updates: dict, local_path: Path) -> None:
    """Merge whichever of SHARED_SETTINGS_KEYS are present in `updates` into
    the shared folder's settings.json, leaving any other key (e.g. a
    warehouse edit saved from another PC, when `updates` only carries
    csv_mappings) untouched. No-op when no shared folder is configured -
    the local settings save already covers it in that case.

    ponytail: last-write-wins per key, no cross-PC locking - fine for
    occasional admin edits; upgrade to a lock file if concurrent warehouse
    edits start actually colliding.
    """
    path = shared_settings_path(updates, local_path)
    if path == local_path:
        return
    shared = load_settings(path) if path.exists() else _defaults()
    for key in SHARED_SETTINGS_KEYS:
        if key in updates:
            shared[key] = updates[key]
    save_settings(path, shared)


def qsettings() -> QSettings:
    # Window geometry is per-machine state. It must never go into
    # settings.json, which the operator may point at a shared folder.
    return QSettings("barcode_tool", "barcode_tool")
