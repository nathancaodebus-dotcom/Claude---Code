"""Persistent logging for every interface's entrypoint. Before this, every
warning/error (registry group failures, background-thread exceptions, ...)
only ever went to whatever terminal happened to be open — fine for
interactive testing, useless for diagnosing a run that happened overnight
on a headless Pi or a backgrounded process, where the terminal is long
gone by the time something's noticed. configure_logging() adds a rotating
file next to the console output so that history survives.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import config

_MAX_BYTES = 5_000_000  # ~5MB per file
_BACKUP_COUNT = 3  # plus the active file: ~20MB of history kept at most

# A dedicated flag rather than "does the root logger already have handlers"
# — some dependency (a test runner's log capture, a library that calls
# logging.basicConfig() on import) could easily add its own root handler
# before this ever runs, which would make a handlers-non-empty check skip
# configuring the file handler entirely without either function ever having
# actually run.
_configured = False


def configure_logging() -> None:
    """Idempotent — safe to call more than once (e.g. a test importing
    several interfaces) without duplicating handlers."""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    Path(config.log_path).parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
