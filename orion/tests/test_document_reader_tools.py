from docx import Document as WordDocument
from pypdf import PdfWriter

from tools.document_reader_tools import ReadPdfTool, ReadWordDocumentTool


def test_read_word_document(tmp_path):
    path = tmp_path / "test.docx"
    doc = WordDocument()
    doc.add_paragraph("Hello from a test document.")
    doc.save(path)

    result = ReadWordDocumentTool().run(path=str(path))
    assert "Hello from a test document." in result


def test_read_pdf_with_no_extractable_text(tmp_path):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        writer.write(f)

    result = ReadPdfTool().run(path=str(path))
    assert "No extractable text" in result
