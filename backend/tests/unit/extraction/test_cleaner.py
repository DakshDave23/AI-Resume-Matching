import pytest

from app.services.extraction.cleaner import clean_text


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        # Ligatures and full-width characters (NFKC).
        ("ﬁnance and eﬃciency", "finance and efficiency"),
        ("Ｊａｖａ", "Java"),
        # Every bullet style becomes "- ".
        ("• Built APIs\n▪ Wrote tests\n➤ Led team", "- Built APIs\n- Wrote tests\n- Led team"),
        ("– Split a monolith\n* Cut costs", "- Split a monolith\n- Cut costs"),
        # Dashes inside a line are not bullets.
        ("Jan 2020 – Present", "Jan 2020 – Present"),
        ("3-5 years of Java", "3-5 years of Java"),
        # A word wrapped at its hyphen is rejoined, keeping the hyphen.
        ("wallet top-\nups and refunds", "wallet top-ups and refunds"),
        # A hyphen before a capitalised next line is a real line end ("Front-" then "End" title).
        ("Spring-\nBoot", "Spring-\nBoot"),
        # Whitespace: tabs, non-breaking and zero-width spaces, trailing spaces.
        ("Java\t\tSpring Boot  \nSQL​", "Java Spring Boot\nSQL"),
        ("soft­ware", "software"),
        # Line breaks are kept; runs of blank lines collapse to one.
        ("Summary\r\n\r\n\r\n\r\nExperience", "Summary\n\nExperience"),
    ],
    ids=[
        "ligatures",
        "full-width",
        "symbol-bullets",
        "dash-bullets",
        "date-dash",
        "range-hyphen",
        "wrapped-compound",
        "capitalised-next-line",
        "whitespace",
        "soft-hyphen",
        "blank-lines",
    ],
)
def test_clean_text(raw: str, clean: str) -> None:
    assert clean_text(raw) == clean


def test_control_characters_are_removed_but_newlines_kept() -> None:
    assert clean_text("Name\x00\x07\nEmail\x0b") == "Name\nEmail"
