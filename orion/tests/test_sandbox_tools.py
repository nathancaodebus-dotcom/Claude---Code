from tools.sandbox_tools import RunPythonSnippetTool


def test_run_python_snippet_captures_stdout():
    result = RunPythonSnippetTool().run(code="print(2 + 2)")
    assert result.strip() == "4"


def test_run_python_snippet_captures_errors():
    result = RunPythonSnippetTool().run(code="raise ValueError('boom')")
    assert "exit code" in result
    assert "boom" in result


def test_run_python_snippet_times_out():
    result = RunPythonSnippetTool().run(code="import time; time.sleep(5)", timeout_seconds=1)
    assert "Timed out" in result


def test_run_python_snippet_no_output():
    result = RunPythonSnippetTool().run(code="x = 1")
    assert result == "(no output)"
