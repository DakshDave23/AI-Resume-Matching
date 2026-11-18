"""Find and parse employment date ranges (design doc §5.5, step 3).

Resumes write dates in a small, closed set of ways, so a grammar is used here
instead of dateparser: dateparser fills missing parts from today ("2019" becomes
2019-<this month>), but a year-only start must mean January and a year-only end
December. Supported:

    Jan 2020 – Present        January 2020 - Mar 2022      Sept. 2019 to Oct 2020
    2019 – 2021               03/2018 – 06/2020            2018-03 – 2020-06
    Jan '20 – Mar '22         Since 2021 / Since Jan 2021  From June 2019
    Present, Current, Now, Till date, To date, Ongoing, Today

Months are whole and inclusive: Jan 2020 – Mar 2020 is 3 months.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

Precision = Literal["month", "year"]

EARLIEST_YEAR = 1950

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_NAME = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_YEAR = r"(?:19|20)\d{2}"
_APOSTROPHES = "'" + chr(0x2019)  # straight and curly (U+2019)
_SHORT_YEAR = rf"[{_APOSTROPHES}]\d{{2}}"  # Jan '20
_NUMERIC_MONTH = r"(?:0?[1-9]|1[0-2])"
_DATE = (
    rf"(?:{_MONTH_NAME},?\s*(?:{_YEAR}|{_SHORT_YEAR})"  # Jan 2020, January, 2020, Jan '20
    rf"|{_NUMERIC_MONTH}[/.-]{_YEAR}"  # 03/2018, 3-2018
    rf"|{_YEAR}[/.-]{_NUMERIC_MONTH}(?![\d/.-])"  # 2018-03
    rf"|{_YEAR})"  # 2019
)
_PRESENT = r"(?:present|current(?:ly)?|now|till\s+date|to\s+date|till\s+now|ongoing|today)"
_DASH = r"(?:\s*[–—-]+\s*|\s+(?:to|until|till)\s+)"
_EDGE_BEFORE = r"(?<![\w/.-])"
_EDGE_AFTER = r"(?![\w/])"

RANGE = re.compile(
    rf"{_EDGE_BEFORE}(?P<start>{_DATE}){_DASH}(?P<end>{_DATE}|{_PRESENT}){_EDGE_AFTER}",
    re.IGNORECASE,
)
SINCE = re.compile(
    rf"\b(?:since|from)\s+(?P<start>{_DATE}){_EDGE_AFTER}(?!{_DASH}(?:{_DATE}|{_PRESENT}))",
    re.IGNORECASE,
)
_PRESENT_ONLY = re.compile(rf"^{_PRESENT}$", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class YearMonth:
    year: int
    month: int

    @property
    def index(self) -> int:
        """Months since year 0, for arithmetic."""
        return self.year * 12 + self.month - 1

    def as_date(self) -> date:
        return date(self.year, self.month, 1)


def months_between(start: YearMonth, end: YearMonth) -> int:
    """Whole months from start to end, both included."""
    return max(0, end.index - start.index + 1)


@dataclass(frozen=True)
class DateRange:
    start: YearMonth
    end: YearMonth | None  # None while current
    precision: Precision  # "year" when either end was written as a bare year
    text: str  # as written, e.g. "Jan 2020 – Present"
    span: tuple[int, int]  # character offsets in the searched text

    @property
    def is_current(self) -> bool:
        return self.end is None

    def end_or(self, today: date) -> YearMonth:
        return self.end or YearMonth(today.year, today.month)

    def months(self, today: date) -> int:
        return months_between(self.start, self.end_or(today))


def _year(text: str, today: date) -> int:
    if text[0] in _APOSTROPHES:  # '20 -> 2020, '98 -> 1998
        short = int(text[1:])
        return 2000 + short if 2000 + short <= today.year + 1 else 1900 + short
    return int(text)


def parse_date(text: str, *, is_end: bool, today: date) -> tuple[YearMonth, Precision] | None:
    """One date from a range. A bare year is January as a start, December as an end."""
    text = text.strip().lower().replace(",", " ")
    if found := re.fullmatch(rf"({_MONTH_NAME})\s*({_YEAR}|{_SHORT_YEAR})", text):
        month, year = _MONTHS[found.group(1)[:3]], _year(found.group(2), today)
        precision: Precision = "month"
    elif found := re.fullmatch(rf"({_NUMERIC_MONTH})[/.-]({_YEAR})", text):
        month, year, precision = int(found.group(1)), int(found.group(2)), "month"
    elif found := re.fullmatch(rf"({_YEAR})[/.-]({_NUMERIC_MONTH})", text):
        year, month, precision = int(found.group(1)), int(found.group(2)), "month"
    elif re.fullmatch(_YEAR, text):
        year, month, precision = int(text), (12 if is_end else 1), "year"
    else:
        return None
    if not EARLIEST_YEAR <= year <= today.year + 1:
        return None
    return YearMonth(year, month), precision


def find_date_ranges(text: str, *, today: date) -> list[DateRange]:
    """Every employment date range in `text`, in order. Implausible ranges are skipped."""
    found: list[DateRange] = []
    for match in sorted([*RANGE.finditer(text), *SINCE.finditer(text)], key=lambda m: m.start()):
        if found and match.start() < found[-1].span[1]:
            continue  # overlaps a range already taken
        start = parse_date(match.group("start"), is_end=False, today=today)
        end_text = match.groupdict().get("end")
        if start is None:
            continue
        if end_text is None or _PRESENT_ONLY.match(end_text.strip()):
            end, end_precision = None, start[1]
        else:
            parsed_end = parse_date(end_text, is_end=True, today=today)
            if parsed_end is None or parsed_end[0] < start[0]:
                continue
            end, end_precision = parsed_end
        precision: Precision = "year" if "year" in (start[1], end_precision) else "month"
        found.append(
            DateRange(
                start[0], end, precision, match.group(0).strip(), (match.start(), match.end())
            )
        )
    return found
