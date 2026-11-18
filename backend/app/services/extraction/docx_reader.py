"""DOCX to text (design doc §5.1, step 3).

Reads paragraphs and tables in document order, and page headers *first*:
many templates put the name and contact line in the header, and the contact
parser looks at the text before the first section heading. Footers come last.

Word list paragraphs ("List Bullet") carry no bullet character in their text,
so they get a "- " prefix here; the section and role parsers rely on it.
"""

import io
import zipfile
from collections.abc import Iterator

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError

from app.services.extraction.errors import ExtractionError

BlockItem = Paragraph | Table


def _is_list_item(paragraph: Paragraph) -> bool:
    style = paragraph.style.name.lower() if paragraph.style is not None else ""
    p_pr = paragraph._p.pPr
    return style.startswith("list") or (p_pr is not None and p_pr.numPr is not None)


def _paragraph_text(paragraph: Paragraph) -> str:
    text = paragraph.text
    return f"- {text}" if text.strip() and _is_list_item(paragraph) else text


def _table_lines(table: Table) -> Iterator[str]:
    """Row by row, each cell once: merged cells repeat in python-docx's row.cells.

    Cells are compared by their XML element, and the set holds those elements: lxml
    keeps one Python proxy per element only while a reference exists, so comparing
    id()s of short-lived proxies would wrongly treat a new cell as already seen.
    """
    seen: set[object] = set()
    for row in table.rows:
        for cell in row.cells:
            if cell._tc in seen:
                continue
            seen.add(cell._tc)
            yield from _block_lines(cell.iter_inner_content())


def _block_lines(items: Iterator[BlockItem]) -> Iterator[str]:
    for item in items:
        if isinstance(item, Paragraph):
            yield _paragraph_text(item)
        else:
            yield from _table_lines(item)


def _unique_parts(parts: list[str]) -> list[str]:
    """Sections usually share one header; keep each distinct header text once."""
    unique: list[str] = []
    for part in parts:
        if part.strip() and part not in unique:
            unique.append(part)
    return unique


def read_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
    except (PackageNotFoundError, KeyError, ValueError, zipfile.BadZipFile, XMLSyntaxError) as exc:
        raise ExtractionError("corrupt_file", "The Word document could not be read.") from exc

    headers = _unique_parts(
        ["\n".join(_block_lines(s.header.iter_inner_content())) for s in document.sections]
    )
    footers = _unique_parts(
        ["\n".join(_block_lines(s.footer.iter_inner_content())) for s in document.sections]
    )
    body = "\n".join(_block_lines(document.iter_inner_content()))
    return "\n".join([*headers, body, *footers])
