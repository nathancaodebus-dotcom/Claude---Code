import pytest

from tools.chart_tool import GenerateChartTool


@pytest.fixture(autouse=True)
def in_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("chart_type", ["bar", "line", "scatter", "pie"])
def test_generates_html_file(chart_type):
    result = GenerateChartTool().run(
        title="Test Chart", chart_type=chart_type, labels=["A", "B"], values=[1, 2]
    )
    assert "Test Chart" in result

    from pathlib import Path

    files = list(Path("outputs").glob("*.html"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "plotly" in content.lower()
