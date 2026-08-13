import os

import pytest
from openpyxl import load_workbook

from core.store import Store
from tools.xlsx_tools import (
    AddSpreadsheetRowTool,
    AddSpreadsheetSheetTool,
    CreateSpreadsheetTool,
    FormatSpreadsheetCellsTool,
    ListSpreadsheetsTool,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return Store(db_path=str(tmp_path / "test.db"))


def test_create_spreadsheet(store):
    result = CreateSpreadsheetTool(store).run(
        title="Budget", headers=["Item", "Price"], rows=[["Bread", 2.5]]
    )
    assert "budget" in result

    doc = store.get_document("budget")
    assert os.path.exists(doc.path)
    wb = load_workbook(doc.path)
    sheet = wb.active
    assert [c.value for c in sheet[1]] == ["Item", "Price"]
    assert [c.value for c in sheet[2]] == ["Bread", 2.5]


def test_add_spreadsheet_row(store):
    CreateSpreadsheetTool(store).run(title="Budget", headers=["Item", "Price"])
    AddSpreadsheetRowTool(store).run(document_name="budget", row=["Milk", 1.2])

    doc = store.get_document("budget")
    wb = load_workbook(doc.path)
    assert [c.value for c in wb.active[2]] == ["Milk", 1.2]


def test_add_row_unknown_document_returns_friendly_error(store):
    result = AddSpreadsheetRowTool(store).run(document_name="ghost", row=["x"])
    assert "No spreadsheet" in result


def test_list_spreadsheets(store):
    CreateSpreadsheetTool(store).run(title="Budget", headers=["A"])
    result = ListSpreadsheetsTool(store).run()
    assert "budget" in result


def test_format_cells_range(store):
    CreateSpreadsheetTool(store).run(title="Budget", headers=["Item", "Price"], rows=[["Bread", 2.5]])
    result = FormatSpreadsheetCellsTool(store).run(
        document_name="budget", cell_range="A1:B1", bold=True, fill_color="FFFF00"
    )

    assert "Formatted A1:B1" in result
    doc = store.get_document("budget")
    wb = load_workbook(doc.path)
    header_cell = wb.active["A1"]
    assert header_cell.font.bold is True
    assert header_cell.fill.start_color.rgb == "00FFFF00"


def test_format_single_cell(store):
    CreateSpreadsheetTool(store).run(title="Budget", headers=["Item", "Price"], rows=[["Bread", 2.5]])
    result = FormatSpreadsheetCellsTool(store).run(document_name="budget", cell_range="B2", number_format="0.00")

    assert "Formatted B2" in result
    doc = store.get_document("budget")
    wb = load_workbook(doc.path)
    assert wb.active["B2"].number_format == "0.00"


def test_format_cells_unknown_document(store):
    result = FormatSpreadsheetCellsTool(store).run(document_name="ghost", cell_range="A1", bold=True)
    assert "No spreadsheet" in result


def test_add_sheet(store):
    CreateSpreadsheetTool(store).run(title="Budget", headers=["Item"])
    result = AddSpreadsheetSheetTool(store).run(
        document_name="budget", sheet_name="Q2", headers=["Item", "Q2 Price"]
    )

    assert "Added sheet 'Q2'" in result
    doc = store.get_document("budget")
    wb = load_workbook(doc.path)
    assert "Q2" in wb.sheetnames
    assert [c.value for c in wb["Q2"][1]] == ["Item", "Q2 Price"]


def test_add_sheet_refuses_duplicate_name(store):
    CreateSpreadsheetTool(store).run(title="Budget", headers=["Item"])
    AddSpreadsheetSheetTool(store).run(document_name="budget", sheet_name="Q2")
    result = AddSpreadsheetSheetTool(store).run(document_name="budget", sheet_name="Q2")
    assert "already has a sheet" in result
