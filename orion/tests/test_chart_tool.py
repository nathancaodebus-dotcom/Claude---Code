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


def test_histogram_bins_raw_values():
    result = GenerateChartTool().run(title="Distribution", chart_type="histogram", values=[1, 2, 2, 3, 3, 3])
    assert "histogram chart" in result

    from pathlib import Path

    files = list(Path("outputs").glob("*.html"))
    assert len(files) == 1


def test_histogram_requires_values():
    result = GenerateChartTool().run(title="Distribution", chart_type="histogram")
    assert "needs 'values'" in result


def test_missing_labels_or_values_returns_friendly_error():
    result = GenerateChartTool().run(title="Test Chart", chart_type="bar", labels=["A"])
    assert "Need both" in result


@pytest.mark.parametrize("chart_type", ["bar", "line", "scatter"])
def test_multi_series_chart(chart_type):
    result = GenerateChartTool().run(
        title="Comparison",
        chart_type=chart_type,
        labels=["Jan", "Feb"],
        series=[{"name": "2024", "values": [10, 20]}, {"name": "2025", "values": [15, 25]}],
    )
    assert "Comparison" in result

    from pathlib import Path

    files = list(Path("outputs").glob("*.html"))
    content = files[0].read_text()
    assert "2024" in content
    assert "2025" in content


def test_labels_and_values_length_mismatch_returns_friendly_error():
    """Regression test: mismatched-length labels/values used to render
    misaligned/silently truncated points instead of erroring."""
    result = GenerateChartTool().run(
        title="Test Chart", chart_type="bar", labels=["A", "B", "C"], values=[1, 2]
    )
    assert "must be the same length" in result


def test_series_with_wrong_length_returns_friendly_error():
    """Regression test: every series is plotted against the same shared
    `labels` — a series with a different number of values than labels
    used to plot each point against the wrong category with no error."""
    result = GenerateChartTool().run(
        title="Comparison",
        chart_type="bar",
        labels=["Jan", "Feb", "Mar"],
        series=[{"name": "2024", "values": [10, 20]}],
    )
    assert "2024" in result
    assert "different number of values" in result


def test_series_requires_labels():
    result = GenerateChartTool().run(
        title="Comparison", chart_type="bar", series=[{"name": "2024", "values": [10, 20]}]
    )
    assert "Need 'labels'" in result


def test_multi_series_rejected_for_pie():
    result = GenerateChartTool().run(
        title="Comparison",
        chart_type="pie",
        labels=["Jan", "Feb"],
        series=[{"name": "2024", "values": [10, 20]}],
    )
    assert "only supported for bar, line, or scatter" in result
