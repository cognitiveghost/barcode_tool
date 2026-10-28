from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Iterable
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


def _quarantine(path: Path, error: Exception, outcome: str, on_recovery: Callable[[str], None] | None) -> None:
    # Timestamped so a second incident never overwrites the first copy.
    corrupt_path = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        path.replace(corrupt_path)
        kept = f"was moved aside as {corrupt_path.name}"
    except OSError:
        kept = "could not be moved aside"
    message = f"{path} could not be read ({error}) and {kept}. {outcome}"
    logging.getLogger(LOGGER_NAME).warning(message)
    if on_recovery is not None:
        on_recovery(message)


def _read_json_object(
    path: Path, on_recovery: Callable[[str], None] | None, outcome: str
) -> dict | None:
    """The JSON object in `path`, or None when it is missing or unreadable.
    An unreadable file is moved aside first, so the caller decides what to write next."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError(f"{path.name} does not contain a JSON object")  # noqa: TRY004 (see except (OSError, ValueError) below)
    except (OSError, ValueError) as error:
        _quarantine(path, error, outcome, on_recovery)
        return None
    return loaded


def _read_shared(path: Path, on_recovery: Callable[[str], None] | None) -> dict | None:
    return _read_json_object(
        path, on_recovery, "The shared settings were not used: this PC's own warehouses and CSV mappings stay in use."
    )


def load_settings(path: Path, on_recovery: Callable[[str], None] | None = None) -> dict:
    settings = _defaults()
    loaded = _read_json_object(path, on_recovery, "It has been reset to defaults.")
    if loaded is not None:
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


def sync_shared_settings(
    settings: dict, local_path: Path, on_recovery: Callable[[str], None] | None = None
) -> dict:
    """Overlay warehouses/csv_mappings from the shared folder's settings.json
    onto `settings`. The first time a shared folder is configured (no
    settings.json there yet), seeds it from this machine's current values
    instead of wiping them. An unreadable shared file is moved aside and this
    machine's own values are kept. No-op when no shared folder is configured."""
    path = shared_settings_path(settings, local_path)
    if path == local_path:
        return settings
    if path.exists():
        shared = _read_shared(path, on_recovery)
        if shared is not None:
            for key in SHARED_SETTINGS_KEYS:
                # A key the shared file lacks is not an empty list: keep ours.
                if key in shared:
                    settings[key] = shared[key]
    else:
        save_shared_settings(settings, local_path)
    return settings


def save_shared_settings(
    settings: dict,
    local_path: Path,
    keys: Iterable[str] = SHARED_SETTINGS_KEYS,
    on_recovery: Callable[[str], None] | None = None,
) -> None:
    """Write `settings[k]` for each `k` in `keys` that `settings` contains into
    the shared folder's settings.json, leaving every other key as it is there.
    If that file is missing or unreadable, it is seeded from `settings` (all
    shared keys it carries), never from empty defaults. No-op when no shared
    folder is configured - the local settings save already covers it then.

    ponytail: last-write-wins per key, no cross-PC locking - fine for
    occasional admin edits; upgrade to a lock file if concurrent warehouse
    edits start actually colliding.
    """
    path = shared_settings_path(settings, local_path)
    if path == local_path:
        return
    changes = {key: settings[key] for key in keys if key in settings}
    current = _read_shared(path, on_recovery)
    if current is not None and not changes:
        return
    # Shared keys the file lacks (or the whole file, when missing or
    # unreadable) are seeded from `settings`, never from empty defaults.
    seed = {key: settings[key] for key in SHARED_SETTINGS_KEYS if key in settings}
    save_settings(path, {**_defaults(), **seed, **(current or {}), **changes})


def qsettings() -> QSettings:
    # Window geometry is per-machine state. It must never go into
    # settings.json, which the operator may point at a shared folder.
    return QSettings("barcode_tool", "barcode_tool")
