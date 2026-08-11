"""Read text out of existing PDF/DOCX files (as opposed to pptx_tools.py /
docx_tools.py / xlsx_tools.py, which create and edit new ones) so they can
be summarized or questioned — 'what does this PDF say', 'summarize this
report'. Reads local file paths; combine with an interface's file-download
step (e.g. a Telegram document) to point this at a received file."""
from __future__ import annotations

from docx import Document as WordDocument
from pypdf import PdfReader

from tools.base import Tool


class ReadPdfTool(Tool):
    name = "read_pdf"
    description = "Extract text from a PDF file by its local path, for summarizing or answering questions about it."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Default 8000."},
        },
        "required": ["path"],
    }

    def run(self, path: str, max_chars: int = 8000) -> str:
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            return "No extractable text found (the PDF may be scanned images without OCR)."
        return text[:max_chars]


class ReadWordDocumentTool(Tool):
    name = "read_word_document"
    description = "Extract text from an existing Word document (.docx) by its local path."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Default 8000."},
        },
        "required": ["path"],
    }

    def run(self, path: str, max_chars: int = 8000) -> str:
        doc = WordDocument(path)
        text = "\n".join(p.text for p in doc.paragraphs)
        return text[:max_chars] if text.strip() else "No text found in this document."
