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
