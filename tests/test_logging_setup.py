import logging
import socket

import pytest

from app.core.config import LOGGER_NAME
from app.core.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _clean_logger_state():
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_configure_logging_creates_a_per_hostname_log_file(tmp_path):
    configure_logging(tmp_path)

    hostname = socket.gethostname()
    log_path = tmp_path / "logs" / f"{hostname}.log"
    logging.getLogger(LOGGER_NAME).info("test message")

    assert log_path.exists()
    assert "test message" in log_path.read_text(encoding="utf-8")


def test_configure_logging_is_idempotent(tmp_path):
    configure_logging(tmp_path)
    configure_logging(tmp_path)

    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1


def test_configure_logging_reconfigures_to_a_new_folder(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    configure_logging(first_dir)
    configure_logging(second_dir)

    logging.getLogger(LOGGER_NAME).info("goes to second")

    assert not (first_dir / "logs" / f"{socket.gethostname()}.log").exists() or \
        "goes to second" not in (first_dir / "logs" / f"{socket.gethostname()}.log").read_text(encoding="utf-8")
    assert "goes to second" in (second_dir / "logs" / f"{socket.gethostname()}.log").read_text(encoding="utf-8")


def test_configure_logging_survives_an_unwritable_shared_folder(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("occupied by a file, not a directory")

    configure_logging(blocked)  # must not raise
