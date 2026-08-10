"""Create and edit Word documents by voice or text."""
from __future__ import annotations

from docx import Document as WordDocument

from core.attachments import push as push_attachment
from core.store import Store
from tools.base import Tool
from tools.document_utils import kind_collision_warning, resolve_path, slugify


class CreateWordDocumentTool(Tool):
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
    name = "append_to_word_document"
    description = "Append a paragraph or heading to an existing Word document."
    input_schema = {
        "type": "object",
        "properties": {
            "document_name": {"type": "string"},
            "text": {"type": "string"},
            "as_heading": {"type": "boolean", "description": "Add as a level-1 heading instead of body text."},
        },
        "required": ["document_name", "text"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, document_name: str, text: str, as_heading: bool = False) -> str:
        doc_record = self._store.get_document(document_name)
        if not doc_record or doc_record.kind != "docx":
            return f"No Word document named '{document_name}'. Use create_word_document first."

        doc = WordDocument(doc_record.path)
        if as_heading:
            doc.add_heading(text, level=1)
        else:
            doc.add_paragraph(text)
        doc.save(doc_record.path)

        self._store.touch_document(document_name)
        push_attachment(doc_record.path)
        return f"Appended to '{document_name}'."


class ListWordDocumentsTool(Tool):
    name = "list_word_documents"
    description = "List all Word documents Jarvis has created."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        docs = self._store.list_documents(kind="docx")
        if not docs:
            return "No Word documents yet."
        return "\n".join(f"- {d.name} ({d.path})" for d in docs)
