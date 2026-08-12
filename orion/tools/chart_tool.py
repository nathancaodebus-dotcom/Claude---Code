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
    description = (
        "Generate an interactive chart (bar, line, scatter, pie, or histogram) from labeled data "
        "and save it as an HTML file. Pass 'series' instead of 'values' to plot multiple data "
        "series on the same bar/line/scatter chart (e.g. comparing two years side by side)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "chart_type": {"type": "string", "enum": ["bar", "line", "scatter", "pie", "histogram"]},
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "X-axis / category labels. Not used for 'histogram'.",
            },
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Single-series data. For 'histogram', the raw values to bin. "
                "Omit if passing 'series' instead.",
            },
            "series": {
                "type": "array",
                "description": "Multiple named series sharing the same 'labels', for comparison charts "
                "(bar/line/scatter only). Overrides 'values'/'series_name' if given.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "values": {"type": "array", "items": {"type": "number"}},
                    },
                    "required": ["name", "values"],
                },
            },
            "series_name": {"type": "string", "description": "Default 'Series 1'. Ignored if 'series' is given."},
        },
        "required": ["title", "chart_type"],
    }

    def run(
        self,
        title: str,
        chart_type: str,
        labels: list[str] | None = None,
        values: list[float] | None = None,
        series: list[dict] | None = None,
        series_name: str = "Series 1",
    ) -> str:
        if chart_type == "histogram":
            if not values:
                return "'histogram' needs 'values' (the raw data points to bin)."
            traces = [go.Histogram(x=values, name=series_name)]
        elif series:
            if chart_type not in ("bar", "line", "scatter"):
                return "Multiple series are only supported for bar, line, or scatter charts."
            traces = [_CHART_BUILDERS[chart_type](labels, s["values"], s["name"]) for s in series]
        else:
            if not labels or values is None:
                return "Need both 'labels' and 'values' (or 'series') for this chart type."
            traces = [_CHART_BUILDERS[chart_type](labels, values, series_name)]

        fig = go.Figure(data=traces)
        fig.update_layout(title=title, barmode="group")

        path = resolve_path(slugify(title), "html")
        fig.write_html(path)

        push_attachment(str(path))
        return f"Generated {chart_type} chart '{title}', saved to {path}."
