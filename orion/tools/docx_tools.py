"""Create and edit Word documents by voice or text."""
from __future__ import annotations

from pathlib import Path

from docx import Document as WordDocument
from docx.shared import Inches

from core.attachments import push as push_attachment
from core.store import Store
from tools.base import Tool
from tools.document_utils import kind_collision_warning, resolve_path, slugify


class CreateWordDocumentTool(Tool):
    requires_network = False
    name = "create_word_document"
    description = (
        "Create a new Word document with a title and a list of paragraphs (or headings). "
        "Returns the document name to use in later append_to_word_document calls."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "paragraphs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Body paragraphs, added in order after the title.",
            },
            "document_name": {"type": "string", "description": "Derived from the title if omitted."},
        },
        "required": ["title"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, title: str, paragraphs: list[str] | None = None, document_name: str | None = None) -> str:
        document_name = document_name or slugify(title)
        path = resolve_path(document_name, "docx")

        doc = WordDocument()
        doc.add_heading(title, level=0)
        for paragraph in paragraphs or []:
            doc.add_paragraph(paragraph)
        doc.save(path)

        previous = self._store.register_document("docx", document_name, str(path))
        push_attachment(str(path))
        return f"Created Word document '{document_name}', saved to {path}.{kind_collision_warning(previous, 'docx')}"


class AppendToWordDocumentTool(Tool):
    requires_network = False
    name = "append_to_word_document"
    description = "Append a paragraph or heading to an existing Word document."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "text": {"type": "string"},
            "as_heading": {"type": "boolean", "description": "Add as a level-1 heading instead of body text."},
            "page_break_before": {
                "type": "boolean",
                "description": "Start a new page before adding this text.",
            },
        },
        "required": ["document_name", "text"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self, document_name: str, text: str, as_heading: bool = False, page_break_before: bool = False
    ) -> str:
        doc_record = self._store.get_document(document_name)
        if not doc_record or doc_record.kind != "docx":
            return f"No Word document named '{document_name}'. Use create_word_document first."

        doc = WordDocument(doc_record.path)
        if page_break_before:
            doc.add_page_break()
        if as_heading:
            doc.add_heading(text, level=1)
        else:
            doc.add_paragraph(text)
        doc.save(doc_record.path)

        self._store.touch_document(document_name)
        push_attachment(doc_record.path)
        return f"Appended to '{document_name}'."


class AddTableToWordDocumentTool(Tool):
    requires_network = False
    name = "add_table_to_word_document"
    description = "Append a table to an existing Word document, with a header row and data rows."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "Each item is one row, a list of cell values matching the headers.",
            },
        },
        "required": ["document_name", "headers"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, document_name: str, headers: list[str], rows: list[list[str]] | None = None) -> str:
        doc_record = self._store.get_document(document_name)
        if not doc_record or doc_record.kind != "docx":
            return f"No Word document named '{document_name}'. Use create_word_document first."

        doc = WordDocument(doc_record.path)
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Light Grid Accent 1"
        for cell, header in zip(table.rows[0].cells, headers):
            cell.text = header
        for row in rows or []:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = str(value)
        doc.save(doc_record.path)

        self._store.touch_document(document_name)
        push_attachment(doc_record.path)
        return f"Added a {len(headers)}-column table ({len(rows or [])} rows) to '{document_name}'."


class AddImageToWordDocumentTool(Tool):
    requires_network = False
    name = "add_image_to_word_document"
    description = (
        "Insert an image (e.g. one made with generate_image or edit_image) into an existing "
        "Word document, at the end."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "image_path": {"type": "string"},
            "width_inches": {"type": "number", "description": "Default 6.0."},
        },
        "required": ["document_name", "image_path"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, document_name: str, image_path: str, width_inches: float = 6.0) -> str:
        doc_record = self._store.get_document(document_name)
        if not doc_record or doc_record.kind != "docx":
            return f"No Word document named '{document_name}'. Use create_word_document first."
        if not Path(image_path).is_file():
            return f"'{image_path}' is not a file."

        doc = WordDocument(doc_record.path)
        doc.add_picture(image_path, width=Inches(width_inches))
        doc.save(doc_record.path)

        self._store.touch_document(document_name)
        push_attachment(doc_record.path)
        return f"Added image '{image_path}' to '{document_name}'."


class ListWordDocumentsTool(Tool):
    requires_network = False
    name = "list_word_documents"
    description = "List all Word documents Orion has created."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        docs = self._store.list_documents(kind="docx")
        if not docs:
            return "No Word documents yet."
        return "\n".join(f"- {d.name} ({d.path})" for d in docs)
