from tools.file_manager_tools import FindDuplicateFilesTool, FindLargeFilesTool, SummarizeDirectoryTool


def test_find_large_files(tmp_path):
    small = tmp_path / "small.txt"
    small.write_bytes(b"x" * 100)
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (2 * 1024 * 1024))

    result = FindLargeFilesTool().run(directory=str(tmp_path), min_size_mb=1)
    assert "big.bin" in result
    assert "small.txt" not in result


def test_find_large_files_missing_directory():
    result = FindLargeFilesTool().run(directory="/no/such/dir")
    assert "not a directory" in result


def test_find_duplicate_files(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"same content")
    (tmp_path / "b.txt").write_bytes(b"same content")
    (tmp_path / "c.txt").write_bytes(b"different")

    result = FindDuplicateFilesTool().run(directory=str(tmp_path))
    assert "a.txt" in result
    assert "b.txt" in result
    assert "c.txt" not in result


def test_find_duplicate_files_none_found(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"unique 1")
    (tmp_path / "b.txt").write_bytes(b"unique 2")

    result = FindDuplicateFilesTool().run(directory=str(tmp_path))
    assert "No duplicate" in result


def test_summarize_directory(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 10)
    (tmp_path / "b.txt").write_bytes(b"x" * 20)
    (tmp_path / "c.jpg").write_bytes(b"x" * 30)

    result = SummarizeDirectoryTool().run(directory=str(tmp_path))
    assert "3 files" in result
    assert ".txt" in result
    assert ".jpg" in result
