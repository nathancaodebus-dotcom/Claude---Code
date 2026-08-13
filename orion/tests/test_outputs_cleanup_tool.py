import os
import time

import pytest

from core.config import config
from tools.outputs_cleanup_tool import CleanOldOutputsTool


@pytest.fixture(autouse=True)
def _restore_retention_config():
    original = config.outputs_retention_days
    yield
    object.__setattr__(config, "outputs_retention_days", original)


def test_reports_nothing_deleted_without_a_retention_period(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()
    object.__setattr__(config, "outputs_retention_days", 0)

    result = CleanOldOutputsTool().run()

    assert "nothing deleted" in result.lower()


def test_deletes_old_files_when_days_is_given_explicitly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    old_file = outputs_dir / "old.png"
    old_file.write_text("x")
    now = time.time()
    os.utime(old_file, (now - 40 * 86400, now - 40 * 86400))

    result = CleanOldOutputsTool().run(days=30)

    assert "Deleted 1 file" in result
    assert not old_file.exists()


def test_falls_back_to_configured_retention_when_days_omitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    old_file = outputs_dir / "old.png"
    old_file.write_text("x")
    now = time.time()
    os.utime(old_file, (now - 40 * 86400, now - 40 * 86400))

    object.__setattr__(config, "outputs_retention_days", 30)
    result = CleanOldOutputsTool().run()

    assert "Deleted 1 file" in result
    assert not old_file.exists()


def test_reports_when_nothing_is_old_enough(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    (outputs_dir / "recent.png").write_text("x")

    result = CleanOldOutputsTool().run(days=30)

    assert "No files older than" in result
