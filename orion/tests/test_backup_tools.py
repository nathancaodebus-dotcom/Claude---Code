from pathlib import Path

import pytest

from tools import backup_tools
from tools.backup_tools import RunBackupTool


def test_backup_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("hello")
    dest = tmp_path / "dest"

    result = RunBackupTool().run(source=str(source), destination=str(dest))
    assert "Backed up" in result

    backups = list(dest.iterdir())
    assert len(backups) == 1
    assert (backups[0] / "file.txt").read_text() == "hello"


def test_backup_single_file(tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("hello")
    dest = tmp_path / "dest"

    result = RunBackupTool().run(source=str(source), destination=str(dest))
    assert "Backed up" in result
    assert any(dest.iterdir())


def test_backup_missing_source(tmp_path):
    result = RunBackupTool().run(source=str(tmp_path / "nope"), destination=str(tmp_path / "dest"))
    assert "does not exist" in result


def test_backup_no_config():
    result = RunBackupTool().run()
    assert "No source/destination configured" in result


def test_backup_failing_partway_leaves_nothing_at_the_final_or_staging_name(tmp_path, monkeypatch):
    """Regression test: a copy that fails partway (disk full, permission
    error, a source file vanishing mid-copy) used to leave a partially-
    populated directory sitting right at the final backup name —
    indistinguishable from a complete backup to a later 'restore from
    latest backup' workflow. It should now leave nothing behind at all."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("hello")
    dest = tmp_path / "dest"

    def failing_copytree(src, dst):
        Path(dst).mkdir()
        (Path(dst) / "partial-file.txt").write_text("only got this far")
        raise OSError("disk full")

    monkeypatch.setattr(backup_tools.shutil, "copytree", failing_copytree)

    with pytest.raises(OSError):
        RunBackupTool().run(source=str(source), destination=str(dest))

    assert list(dest.iterdir()) == []  # neither the final name nor a '.partial' one survives
