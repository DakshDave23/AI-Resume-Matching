import pytest

from app.services.extraction import ExtractionError, extract_text
from app.services.extraction.pdf_reader import Block, find_gutter, order_blocks, read_pdf
from tests.unit.extraction.builders import make_pdf

PAGE_WIDTH = 595.0


def block(x0: float, y0: float, x1: float, y1: float, text: str) -> Block:
    return Block(x0, y0, x1, y1, text)


# Sidebar x 40-200, main column x 225-555: like the two-column sample resume.
HEADER = block(40, 40, 300, 60, "Rahul Verma")
CONTACT = block(40, 64, 340, 76, "rahul@example.com | +1 312 555 0119 | Hyderabad, India")
SKILLS_TITLE = block(40, 100, 200, 112, "Technical Skills")
SKILLS = block(40, 114, 200, 140, "Java, Spring Boot, MySQL, REST, Docker, RabbitMQ, Git")
EDU_TITLE = block(40, 160, 200, 172, "Education")
EDU = block(40, 174, 200, 200, "B.Tech in Computer Science, Deccan Institute, 2021")
SUMMARY_TITLE = block(225, 100, 555, 112, "Summary")
SUMMARY = block(
    225, 114, 555, 140, "Java developer with 5.5 years in the industry, 4.5 in payments."
)
EXP_TITLE = block(225, 160, 555, 172, "Work Experience")
EXP = block(225, 174, 555, 260, "Java Developer, Contoso Payments, Jun 2022 – Present. " * 3)

TWO_COLUMN_PAGE = [EXP, SUMMARY, HEADER, EDU, SKILLS_TITLE, CONTACT, EDU_TITLE, SUMMARY_TITLE,
                   SKILLS, EXP_TITLE]  # fmt: skip


def texts(blocks: list[Block]) -> list[str]:
    return [b.text for b in blocks]


def test_two_columns_are_read_left_column_first() -> None:
    ordered = order_blocks(TWO_COLUMN_PAGE, PAGE_WIDTH)

    assert texts(ordered) == texts(
        [HEADER, CONTACT, SKILLS_TITLE, SKILLS, EDU_TITLE, EDU,
         SUMMARY_TITLE, SUMMARY, EXP_TITLE, EXP]
    )  # fmt: skip


def test_gutter_lies_between_the_columns() -> None:
    gutter = find_gutter(TWO_COLUMN_PAGE, PAGE_WIDTH)

    assert gutter is not None
    assert 200 <= gutter <= 225


def test_a_full_width_block_below_the_columns_is_read_after_both() -> None:
    footer = block(
        40, 300, 555, 320, "References available on request from all previous employers."
    )

    ordered = order_blocks([*TWO_COLUMN_PAGE, footer], PAGE_WIDTH)

    assert ordered[-1] == footer
    assert texts(ordered).index("Education") < texts(ordered).index("Summary")


def test_one_column_with_right_aligned_dates_keeps_line_order() -> None:
    # Dates on the right are a few short lines, not a second column.
    page = []
    for i, (role, dates) in enumerate([("Senior Engineer, Acme", "Apr 2021 – Present"),
                                       ("Engineer, Globex", "Jul 2017 – Mar 2021")]):  # fmt: skip
        top = 100 + i * 120
        page.append(block(40, top, 300, top + 12, role))
        page.append(block(460, top, 555, top + 12, dates))
        page.append(block(40, top + 16, 520, top + 100, "Built payment services in Java. " * 8))

    ordered = order_blocks(page, PAGE_WIDTH)

    assert find_gutter(page, PAGE_WIDTH) is None
    assert texts(ordered)[:3] == ["Senior Engineer, Acme", "Apr 2021 – Present", page[2].text]


def test_read_pdf_returns_text_and_page_count() -> None:
    text, pages = read_pdf(make_pdf("Arjun Mehta", "arjun.mehta@example.com"))

    assert pages == 1
    assert "Arjun Mehta" in text and "arjun.mehta@example.com" in text


def test_a_damaged_pdf_is_reported_not_crashed() -> None:
    with pytest.raises(ExtractionError) as exc:
        read_pdf(b"%PDF-1.7\nthis is not really a pdf")
    assert exc.value.code == "corrupt_file"


def test_a_password_protected_pdf_is_reported() -> None:
    import pymupdf

    locked = make_pdf("secret", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")

    with pytest.raises(ExtractionError) as exc:
        read_pdf(locked)
    assert exc.value.code == "encrypted_file"


def test_a_pdf_with_almost_no_text_is_treated_as_scanned() -> None:
    with pytest.raises(ExtractionError) as exc:
        extract_text(make_pdf("Page 1"), "pdf")
    assert exc.value.code == "scanned_pdf"
    assert exc.value.message == "Looks like a scanned image; OCR is not enabled."
