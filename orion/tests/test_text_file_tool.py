from tools.text_file_tool import ReadTextFileTool


def test_read_text_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello world")

    result = ReadTextFileTool().run(path=str(path))
    assert result == "hello world"


def test_read_missing_file():
    result = ReadTextFileTool().run(path="/no/such/file.txt")
    assert "not a file" in result


def test_read_truncates_to_max_chars(tmp_path):
    path = tmp_path / "big.txt"
    path.write_text("x" * 100)

    result = ReadTextFileTool().run(path=str(path), max_chars=10)
    assert len(result) == 10
