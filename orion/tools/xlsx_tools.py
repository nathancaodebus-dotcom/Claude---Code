"""Create and edit Excel spreadsheets by voice or text."""
from __future__ import annotations

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Font, PatternFill

from core.attachments import push as push_attachment
from core.store import Store
from tools.base import Tool
from tools.document_utils import kind_collision_warning, resolve_path, slugify


class CreateSpreadsheetTool(Tool):
    name = "create_spreadsheet"
    description = (
        "Create a new Excel spreadsheet with a header row and data rows. Returns the "
        "document name to use in later add_spreadsheet_row calls."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": ["string", "number"]}},
                "description": "Each item is one row, a list of cell values matching the headers.",
            },
            "document_name": {"type": "string", "description": "Derived from the title if omitted."},
        },
        "required": ["title", "headers"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, title: str, headers: list[str], rows: list[list] | None = None, document_name: str | None = None) -> str:
        document_name = document_name or slugify(title)
        path = resolve_path(document_name, "xlsx")

        wb = Workbook()
        sheet = wb.active
        sheet.title = title[:31]  # Excel sheet name limit
        sheet.append(headers)
        for row in rows or []:
            sheet.append(row)
        wb.save(path)

        previous = self._store.register_document("xlsx", document_name, str(path))
        push_attachment(str(path))
        return (
            f"Created spreadsheet '{document_name}' with {len(rows or [])} data rows, saved to {path}."
            f"{kind_collision_warning(previous, 'xlsx')}"
        )


class AddSpreadsheetRowTool(Tool):
    name = "add_spreadsheet_row"
    description = "Append a row of values to an existing spreadsheet."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "row": {"type": "array", "items": {"type": ["string", "number"]}},
        },
        "required": ["document_name", "row"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, document_name: str, row: list) -> str:
        doc = self._store.get_document(document_name)
        if not doc or doc.kind != "xlsx":
            return f"No spreadsheet named '{document_name}'. Use create_spreadsheet first."

        wb = load_workbook(doc.path)
        wb.active.append(row)
        wb.save(doc.path)

        self._store.touch_document(document_name)
        push_attachment(doc.path)
        return f"Added row to '{document_name}'."


class SetSpreadsheetFormulaTool(Tool):
    name = "set_spreadsheet_formula"
    description = (
        "Set a cell to an Excel formula, e.g. cell='C2', formula='=A2*B2' or "
        "formula='=SUM(B2:B10)'. The formula is stored as-is and Excel evaluates it on open."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "cell": {"type": "string", "description": "Cell reference, e.g. 'C2'."},
            "formula": {"type": "string", "description": "Must start with '='."},
        },
        "required": ["document_name", "cell", "formula"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, document_name: str, cell: str, formula: str) -> str:
        doc = self._store.get_document(document_name)
        if not doc or doc.kind != "xlsx":
            return f"No spreadsheet named '{document_name}'. Use create_spreadsheet first."

        wb = load_workbook(doc.path)
        wb.active[cell] = formula
        wb.save(doc.path)

        self._store.touch_document(document_name)
        push_attachment(doc.path)
        return f"Set {cell} = {formula} in '{document_name}'."


class AddSpreadsheetChartTool(Tool):
    name = "add_spreadsheet_chart"
    description = "Add a bar, line, or pie chart to a spreadsheet, plotting a range of data against category labels."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
            "data_range": {"type": "string", "description": "Cell range for the values, e.g. 'B1:B10'."},
            "category_range": {"type": "string", "description": "Cell range for category labels, e.g. 'A2:A10'."},
            "title": {"type": "string"},
            "anchor_cell": {"type": "string", "description": "Top-left cell to place the chart. Default 'E2'."},
        },
        "required": ["document_name", "chart_type", "data_range", "category_range"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self,
        document_name: str,
        chart_type: str,
        data_range: str,
        category_range: str,
        title: str = "",
        anchor_cell: str = "E2",
    ) -> str:
        doc = self._store.get_document(document_name)
        if not doc or doc.kind != "xlsx":
            return f"No spreadsheet named '{document_name}'. Use create_spreadsheet first."

        wb = load_workbook(doc.path)
        sheet = wb.active

        chart_classes = {"bar": BarChart, "line": LineChart, "pie": PieChart}
        chart = chart_classes[chart_type]()
        if title:
            chart.title = title

        data = Reference(sheet, range_string=f"{sheet.title}!{data_range}")
        categories = Reference(sheet, range_string=f"{sheet.title}!{category_range}")
        chart.add_data(data, titles_from_data=False)
        chart.set_categories(categories)
        sheet.add_chart(chart, anchor_cell)

        wb.save(doc.path)
        self._store.touch_document(document_name)
        push_attachment(doc.path)
        return f"Added a {chart_type} chart to '{document_name}'."


class FormatSpreadsheetCellsTool(Tool):
    name = "format_spreadsheet_cells"
    description = "Apply bold, a text color, a fill (background) color, and/or a number format to a range of cells."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "cell_range": {"type": "string", "description": "e.g. 'A1:C1' or a single cell like 'B2'."},
            "bold": {"type": "boolean"},
            "font_color": {"type": "string", "description": "Hex color without '#', e.g. 'FF0000'."},
            "fill_color": {"type": "string", "description": "Hex color without '#', e.g. 'FFFF00'."},
            "number_format": {
                "type": "string",
                "description": "Excel number format code, e.g. '0.00', '#,##0', '0%', '$#,##0.00'.",
            },
        },
        "required": ["document_name", "cell_range"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self,
        document_name: str,
        cell_range: str,
        bold: bool | None = None,
        font_color: str | None = None,
        fill_color: str | None = None,
        number_format: str | None = None,
    ) -> str:
        doc = self._store.get_document(document_name)
        if not doc or doc.kind != "xlsx":
            return f"No spreadsheet named '{document_name}'. Use create_spreadsheet first."

        wb = load_workbook(doc.path)
        sheet = wb.active
        target = sheet[cell_range]
        rows = target if isinstance(target, tuple) else ((target,),)
        for row in rows:
            for cell in row:
                if bold is not None or font_color is not None:
                    cell.font = Font(bold=bool(bold), color=font_color)
                if fill_color is not None:
                    cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
                if number_format is not None:
                    cell.number_format = number_format

        wb.save(doc.path)
        self._store.touch_document(document_name)
        push_attachment(doc.path)
        return f"Formatted {cell_range} in '{document_name}'."


class AddSpreadsheetSheetTool(Tool):
    name = "add_spreadsheet_sheet"
    description = "Add a new sheet (tab) to an existing spreadsheet, optionally with a header row."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "sheet_name": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["document_name", "sheet_name"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, document_name: str, sheet_name: str, headers: list[str] | None = None) -> str:
        doc = self._store.get_document(document_name)
        if not doc or doc.kind != "xlsx":
            return f"No spreadsheet named '{document_name}'. Use create_spreadsheet first."

        wb = load_workbook(doc.path)
        if sheet_name in wb.sheetnames:
            return f"'{document_name}' already has a sheet named '{sheet_name}'."

        sheet = wb.create_sheet(title=sheet_name[:31])
        if headers:
            sheet.append(headers)
        wb.save(doc.path)

        self._store.touch_document(document_name)
        push_attachment(doc.path)
        return f"Added sheet '{sheet_name}' to '{document_name}' (now {len(wb.sheetnames)} sheets)."


class ListSpreadsheetsTool(Tool):
    name = "list_spreadsheets"
    description = "List all spreadsheets Orion has created."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        docs = self._store.list_documents(kind="xlsx")
        if not docs:
            return "No spreadsheets yet."
        return "\n".join(f"- {d.name} ({d.path})" for d in docs)
