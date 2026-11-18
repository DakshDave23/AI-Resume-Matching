"""Build small PDF and DOCX files in memory for extraction tests."""

import io

import pymupdf
from docx import Document


def make_pdf(*lines: str, **save_options: object) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + i * 16), line)
    data: bytes = pdf.tobytes(**save_options)
    return data


def make_docx(*paragraphs: str) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
