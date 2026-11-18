import io

import pytest
from docx import Document

from app.services.extraction import ExtractionError
from app.services.extraction.docx_reader import read_docx


def build_docx() -> bytes:
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "Meera Pillai — Full Stack Developer"
    doc.sections[0].footer.paragraphs[0].text = "Page 1"
    doc.add_paragraph("Summary")
    doc.add_paragraph("Full stack developer.")
    table = doc.add_table(rows=2, cols=2)
    title = table.rows[0].cells
    title[0].merge(title[1]).text = "Work Experience"  # one cell spanning two columns
    table.rows[1].cells[0].text = "Feb 2022 – Present"
    table.rows[1].cells[1].text = "Full Stack Developer | Hooli Commerce"
    doc.add_paragraph("Built the storefront in React.", style="List Bullet")
    doc.add_paragraph("Education")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_reads_header_first_then_body_in_order_then_footer() -> None:
    lines = [line for line in read_docx(build_docx()).split("\n") if line]

    assert lines == [
        "Meera Pillai — Full Stack Developer",
        "Summary",
        "Full stack developer.",
        "Work Experience",  # merged cell appears once, not twice
        "Feb 2022 – Present",
        "Full Stack Developer | Hooli Commerce",
        "- Built the storefront in React.",  # Word list item gets a visible bullet
        "Education",
        "Page 1",
    ]


def test_a_damaged_docx_is_reported_not_crashed() -> None:
    with pytest.raises(ExtractionError) as exc:
        read_docx(b"PK\x03\x04 definitely not a word document")
    assert exc.value.code == "corrupt_file"
