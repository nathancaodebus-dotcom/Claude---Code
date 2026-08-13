"""configure_logging() mutates the process-global root logger and a
module-level "already configured" flag, so every test here saves/restores
both to avoid leaking state (and open file handles) into unrelated tests —
including pytest's own log-capture handler, which is already attached to
the root logger by the time these tests run, so resetting only the handler
list wouldn't be enough on its own without also resetting the flag."""
from __future__ import annotations

import dataclasses
import logging

import pytest

import core.logging_setup as logging_setup_module
from core.config import config as real_config
from core.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _isolate_root_logger(monkeypatch):
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.handlers = []
    monkeypatch.setattr(logging_setup_module, "_configured", False)
    yield
    for handler in root.handlers:
        if handler not in saved_handlers:
            handler.close()
    root.handlers = saved_handlers
    root.level = saved_level


def test_configure_logging_adds_a_console_and_a_file_handler(tmp_path, monkeypatch):
    cfg = dataclasses.replace(real_config, log_path=str(tmp_path / "orion.log"))
    monkeypatch.setattr("core.logging_setup.config", cfg)

    configure_logging()

    root = logging.getLogger()
    handler_types = {type(h).__name__ for h in root.handlers}
    assert "StreamHandler" in handler_types
    assert "RotatingFileHandler" in handler_types


def test_configure_logging_creates_the_log_file_and_writes_to_it(tmp_path, monkeypatch):
    log_path = tmp_path / "orion.log"
    cfg = dataclasses.replace(real_config, log_path=str(log_path))
    monkeypatch.setattr("core.logging_setup.config", cfg)

    configure_logging()
    logging.getLogger("orion.test").info("hello from a test")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_path.exists()
    assert "hello from a test" in log_path.read_text()


def test_configure_logging_is_idempotent(tmp_path, monkeypatch):
    cfg = dataclasses.replace(real_config, log_path=str(tmp_path / "orion.log"))
    monkeypatch.setattr("core.logging_setup.config", cfg)

    configure_logging()
    handler_count_after_first_call = len(logging.getLogger().handlers)
    configure_logging()

    assert len(logging.getLogger().handlers) == handler_count_after_first_call


def test_configure_logging_creates_parent_directories(tmp_path, monkeypatch):
    log_path = tmp_path / "nested" / "dir" / "orion.log"
    cfg = dataclasses.replace(real_config, log_path=str(log_path))
    monkeypatch.setattr("core.logging_setup.config", cfg)

    configure_logging()

    assert log_path.parent.is_dir()
