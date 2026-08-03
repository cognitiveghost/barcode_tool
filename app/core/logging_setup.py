from __future__ import annotations

import logging
import socket
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import LOGGER_NAME, sanitize_filename_component

# ponytail: fixed rotation size/count rather than a configurable setting -
# no operator has asked to tune this, and 2MB x 3 backups is generous for a
# few-hundred-byte-per-line app log. Upgrade path: expose as a settings.json
# key if a real deployment's log volume ever needs it.
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 3


def configure_logging(shared_folder: Path) -> None:
    """(Re)point the app's logger at <shared_folder>/logs/<hostname>.log.

    Per-host filename (like the audit log's per-print files) means two
    machines writing to the same shared folder never contend for the same
    file - no locking needed.

    Safe to call more than once (e.g. every time Settings changes the
    shared folder): always leaves exactly one handler attached, never
    stacks a new one on top of the last call's.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    log_dir = Path(shared_folder) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        hostname = sanitize_filename_component(socket.gethostname())
        handler = RotatingFileHandler(
            log_dir / f"{hostname}.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        # An offline/read-only shared folder must not stop the app from
        # running - it just runs without a log sink until the folder
        # recovers (the same "degrade, don't crash" rule template_renderer
        # already follows for preset discovery).
        return

    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
