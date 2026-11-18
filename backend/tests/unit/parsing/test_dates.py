from datetime import date

import pytest

from app.services.parsing.dates import YearMonth, find_date_ranges, months_between

TODAY = date(2026, 11, 18)


def one_range(text: str) -> tuple[YearMonth, YearMonth | None, str]:
    found = find_date_ranges(text, today=TODAY)
    assert len(found) == 1, found
    return found[0].start, found[0].end, found[0].precision


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("Jan 2020 – Present", (2020, 1), None),
        ("January 2020 - Mar 2022", (2020, 1), (2022, 3)),
        ("Sept. 2019 to Oct 2020", (2019, 9), (2020, 10)),
        ("Sep 2019 — Oct 2020", (2019, 9), (2020, 10)),  # em dash
        ("June 2018 – February 2020", (2018, 6), (2020, 2)),
        ("March, 2020 – Till date", (2020, 3), None),
        ("03/2018 – 06/2020", (2018, 3), (2020, 6)),
        ("3/2018-6/2020", (2018, 3), (2020, 6)),
        ("06/2025 - Current", (2025, 6), None),
        ("2018-03 – 2020-06", (2018, 3), (2020, 6)),
        ("Jan '20 – Mar '22", (2020, 1), (2022, 3)),
        ("Since Jan 2021", (2021, 1), None),
        ("Feb 2022 - now", (2022, 2), None),
        ("Apr 2021 until today", (2021, 4), None),
        ("Jul 2017 – Ongoing", (2017, 7), None),
        ("aug 2019 - dec 2019", (2019, 8), (2019, 12)),  # any case
    ],
)
def test_month_precision_formats(
    text: str, start: tuple[int, int], end: tuple[int, int] | None
) -> None:
    assert one_range(text) == (YearMonth(*start), YearMonth(*end) if end else None, "month")


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("2019 – 2021", (2019, 1), (2021, 12)),  # a start year is January, an end year December
        ("2024 – Present", (2024, 1), None),
        ("Since 2021", (2021, 1), None),
        ("From 2019", (2019, 1), None),
        ("2019 – Mar 2021", (2019, 1), (2021, 3)),  # mixed: the coarser precision wins
    ],
)
def test_year_precision_formats(
    text: str, start: tuple[int, int], end: tuple[int, int] | None
) -> None:
    assert one_range(text) == (YearMonth(*start), YearMonth(*end) if end else None, "year")


def test_finds_the_range_inside_a_role_line() -> None:
    line = "Senior Software Engineer | Acme Fintech, Bengaluru | Apr 2021 – Present"
    (found,) = find_date_ranges(line, today=TODAY)
    assert found.text == "Apr 2021 – Present"
    assert line[found.span[0] : found.span[1]] == "Apr 2021 – Present"


def test_from_x_to_y_is_one_range_not_a_since() -> None:
    (found,) = find_date_ranges("From Jan 2020 to Mar 2022", today=TODAY)
    assert (found.start, found.end) == (YearMonth(2020, 1), YearMonth(2022, 3))


@pytest.mark.parametrize(
    "text",
    [
        "+1 312 555 0119",  # a phone number
        "B.Tech in Computer Science, 2021",  # a single year is not a range
        "Cut p95 latency from 480 ms to 90 ms",
        "Mar 2022 – Jan 2020",  # ends before it starts
        "2031 – 2033",  # in the future
        "1890 – 1895",  # implausibly old
        "Java 8 – 11 migration",
    ],
)
def test_things_that_are_not_date_ranges(text: str) -> None:
    assert find_date_ranges(text, today=TODAY) == []


def test_two_ranges_on_one_line() -> None:
    found = find_date_ranges("Jan 2019 – Dec 2019, Mar 2020 – Present", today=TODAY)
    assert [f.text for f in found] == ["Jan 2019 – Dec 2019", "Mar 2020 – Present"]


def test_months_are_inclusive_and_present_is_today() -> None:
    assert months_between(YearMonth(2020, 1), YearMonth(2020, 3)) == 3
    assert months_between(YearMonth(2020, 1), YearMonth(2020, 1)) == 1
    (current,) = find_date_ranges("Nov 2025 – Present", today=TODAY)
    assert current.months(TODAY) == 13  # Nov 2025 .. Nov 2026
