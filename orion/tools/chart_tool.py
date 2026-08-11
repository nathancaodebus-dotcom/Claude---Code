"""Generate an interactive chart on demand (Plotly), saved as a standalone
HTML file — opens in any browser, gets sent back as an attachment on
Telegram. Covers the 'show me a dashboard of X' request without needing a
live Grafana/Dash server running somewhere."""
from __future__ import annotations

import plotly.graph_objects as go

from core.attachments import push as push_attachment
from tools.base import Tool
from tools.document_utils import resolve_path, slugify

_CHART_BUILDERS = {
    "bar": lambda x, y, name: go.Bar(x=x, y=y, name=name),
    "line": lambda x, y, name: go.Scatter(x=x, y=y, mode="lines+markers", name=name),
    "scatter": lambda x, y, name: go.Scatter(x=x, y=y, mode="markers", name=name),
    "pie": lambda x, y, name: go.Pie(labels=x, values=y, name=name),
}


class GenerateChartTool(Tool):
    name = "generate_chart"
    description = "Generate an interactive chart (bar, line, scatter, or pie) from labeled data and save it as an HTML file."
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "chart_type": {"type": "string", "enum": ["bar", "line", "scatter", "pie"]},
            "labels": {"type": "array", "items": {"type": "string"}, "description": "X-axis / category labels."},
            "values": {"type": "array", "items": {"type": "number"}},
            "series_name": {"type": "string", "description": "Default 'Series 1'."},
        },
        "required": ["title", "chart_type", "labels", "values"],
    }

    def run(self, title: str, chart_type: str, labels: list[str], values: list[float], series_name: str = "Series 1") -> str:
        trace = _CHART_BUILDERS[chart_type](labels, values, series_name)
        fig = go.Figure(data=[trace])
        fig.update_layout(title=title)

        path = resolve_path(slugify(title), "html")
        fig.write_html(path)

        push_attachment(str(path))
        return f"Generated {chart_type} chart '{title}', saved to {path}."
