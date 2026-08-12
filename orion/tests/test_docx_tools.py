import os

import pytest
from docx import Document as WordDocument
from PIL import Image

from core.store import Store
from tools.docx_tools import (
    AddImageToWordDocumentTool,
    AddTableToWordDocumentTool,
    AppendToWordDocumentTool,
    CreateWordDocumentTool,
    ListWordDocumentsTool,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return Store(db_path=str(tmp_path / "test.db"))


def test_create_word_document(store):
    result = CreateWordDocumentTool(store).run(title="My Report", paragraphs=["first"])
    assert "my-report" in result

    doc = store.get_document("my-report")
    assert os.path.exists(doc.path)
    word_doc = WordDocument(doc.path)
    assert word_doc.paragraphs[0].text == "My Report"
    assert word_doc.paragraphs[1].text == "first"


def test_append_to_word_document(store):
    CreateWordDocumentTool(store).run(title="My Report")
    AppendToWordDocumentTool(store).run(document_name="my-report", text="second paragraph")

    doc = store.get_document("my-report")
    word_doc = WordDocument(doc.path)
    assert word_doc.paragraphs[-1].text == "second paragraph"


def test_append_unknown_document_returns_friendly_error(store):
    result = AppendToWordDocumentTool(store).run(document_name="ghost", text="x")
    assert "No Word document" in result


def test_list_word_documents(store):
    CreateWordDocumentTool(store).run(title="Report One")
    CreateWordDocumentTool(store).run(title="Report Two")

    result = ListWordDocumentsTool(store).run()
    assert "report-one" in result
    assert "report-two" in result


def test_append_with_page_break(store):
    CreateWordDocumentTool(store).run(title="My Report")
    AppendToWordDocumentTool(store).run(document_name="my-report", text="new page text", page_break_before=True)

    doc = store.get_document("my-report")
    word_doc = WordDocument(doc.path)
    # A page break is a run-level element, not its own paragraph, so check
    # the document actually grew rather than inspecting XML internals.
    assert word_doc.paragraphs[-1].text == "new page text"
    assert len(word_doc.paragraphs) == 3  # title + page-break paragraph + text


def test_add_table_to_word_document(store):
    CreateWordDocumentTool(store).run(title="My Report")
    result = AddTableToWordDocumentTool(store).run(
        document_name="my-report", headers=["Item", "Price"], rows=[["Bread", "2.50"], ["Milk", "1.20"]]
    )

    assert "2-column table" in result
    doc = store.get_document("my-report")
    word_doc = WordDocument(doc.path)
    assert len(word_doc.tables) == 1
    table = word_doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == ["Item", "Price"]
    assert [c.text for c in table.rows[1].cells] == ["Bread", "2.50"]
    assert len(table.rows) == 3  # header + 2 data rows


def test_add_table_unknown_document(store):
    result = AddTableToWordDocumentTool(store).run(document_name="ghost", headers=["A"])
    assert "No Word document" in result


def test_add_image_to_word_document(store, tmp_path):
    CreateWordDocumentTool(store).run(title="My Report")
    image_path = tmp_path / "photo.png"
    Image.new("RGB", (40, 30), color="green").save(image_path)

    result = AddImageToWordDocumentTool(store).run(document_name="my-report", image_path=str(image_path))

    assert "Added image" in result
    doc = store.get_document("my-report")
    word_doc = WordDocument(doc.path)
    assert len(word_doc.inline_shapes) == 1


def test_add_image_missing_file(store):
    CreateWordDocumentTool(store).run(title="My Report")
    result = AddImageToWordDocumentTool(store).run(document_name="my-report", image_path="nope.png")
    assert "is not a file" in result
