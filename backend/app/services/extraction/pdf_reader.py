"""PDF to text with column-aware reading order (design doc §5.1, step 2).

PyMuPDF returns text in blocks with coordinates. Sorting blocks top to bottom
breaks two-column resumes: a sidebar line ("Education") lands between two
experience bullets. Instead we look for a vertical gutter that splits the page
into two real columns and read the left column fully before the right one.
Blocks that cross the gutter (a full-width header) are read in place and close
the current pair of columns, so a page can mix full-width and two-column parts.
"""

from dataclasses import dataclass

import pymupdf

from app.services.extraction.errors import ExtractionError

GUTTER_MIN_WIDTH = 8.0  # points of empty space required between the two columns
# Full-width blocks (name, contact lines, a footer) may cross the gutter. The side checks
# below, not this count, are what stop a one-column page from being split.
GUTTER_MAX_CROSSING_SHARE = 1 / 3
GUTTER_REGION = (0.15, 0.85)  # gutters are looked for between these fractions of page width
MIN_SIDE_SHARE = 0.08  # each column must hold at least this share of the page's text


@dataclass(frozen=True)
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def find_gutter(blocks: list[Block], page_width: float) -> float | None:
    """x-coordinate of the gap between two text columns, or None for a one-column page.

    A gap only counts as a gutter when both sides hold a real share of the text
    and have blocks side by side vertically. That rules out a single column with
    right-aligned dates, where the right "column" is a few short lines.
    """
    if len(blocks) < 4 or page_width <= 0:
        return None

    # A right-hand column starts where several blocks share a left edge, so every block's
    # x0 is a candidate column start. Keep the valid candidate crossed by the fewest blocks.
    lo, hi = GUTTER_REGION[0] * page_width, GUTTER_REGION[1] * page_width
    max_crossing = max(2, int(len(blocks) * GUTTER_MAX_CROSSING_SHARE))
    total_chars = sum(len(b.text) for b in blocks)
    best: tuple[int, float] | None = None  # (blocks crossing, gutter x)
    for column_start in sorted({round(b.x0, 1) for b in blocks}):
        if not lo <= column_start <= hi:
            continue
        left = [b for b in blocks if b.x1 <= column_start - GUTTER_MIN_WIDTH]
        right = [b for b in blocks if b.x0 >= column_start]
        crossing = len(blocks) - len(left) - len(right)
        if crossing > max_crossing or not _are_columns(left, right, total_chars):
            continue
        if best is None or crossing < best[0]:
            best = (crossing, column_start - GUTTER_MIN_WIDTH / 2)
    return best[1] if best else None


def _are_columns(left: list[Block], right: list[Block], total_chars: int) -> bool:
    """Both sides hold a real share of the text and sit side by side on the page."""
    for side in (left, right):
        if len(side) < 2 or sum(len(b.text) for b in side) < MIN_SIDE_SHARE * total_chars:
            return False
    return any(l.y0 < r.y1 and r.y0 < l.y1 for l in left for r in right)  # noqa: E741


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    """Blocks in human reading order."""
    by_position = sorted(blocks, key=lambda b: (round(b.y0, 1), b.x0))
    gutter = find_gutter(blocks, page_width)
    if gutter is None:
        return by_position

    ordered: list[Block] = []
    left: list[Block] = []
    right: list[Block] = []
    for block in by_position:
        if block.x1 <= gutter:
            left.append(block)
        elif block.x0 >= gutter:
            right.append(block)
        else:  # spans both columns: finish the columns above it first
            ordered += left + right
            left, right = [], []
            ordered.append(block)
    return ordered + left + right


def _page_blocks(page: pymupdf.Page) -> list[Block]:
    return [
        Block(x0, y0, x1, y1, text.strip("\n"))
        for x0, y0, x1, y1, text, _number, block_type in page.get_text("blocks")
        if block_type == 0 and text.strip()  # 0 = text; 1 = image
    ]


def read_pdf(data: bytes) -> tuple[str, int]:
    """Return (raw text, page count). Raises ExtractionError for damaged or locked files."""
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise ExtractionError(
            "corrupt_file", "The PDF could not be read; it may be damaged."
        ) from exc

    with document:
        if document.needs_pass:
            raise ExtractionError("encrypted_file", "The PDF is password-protected.")
        pages = []
        for number in range(document.page_count):
            page = document.load_page(number)
            blocks = order_blocks(_page_blocks(page), page.rect.width)
            pages.append("\n".join(b.text for b in blocks))
        return "\n\n".join(pages), document.page_count
