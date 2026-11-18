"""Work history: roles, total experience and years per skill (design doc §5.5, steps 3-5, 7).

Each date range in the Experience section anchors one role. Title and company
come from the role's header: the text on the date line itself ("Engineer | Acme
| Jan 2020 – Present"), up to two lines above it ("Engineer\\nAcme, Pune\\nJun
2022 – Present"), or, when the date stands alone at the top of an entry (table
templates), up to two lines below it. The lines after the header, up to the next
role's header, are its description.

Total experience merges overlapping date ranges, so two jobs held at once count
once. Internships are listed but left out of the total. A resume with no dates
falls back to a statement such as "7 years of experience" in the summary.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.models.enums import SkillSource
from app.services.parsing.dates import DateRange, find_date_ranges
from app.services.parsing.skills import SkillExtractor
from app.services.parsing.vocabulary import has_title_word

ExperienceSource = Literal["dates", "summary_statement"]

MAX_HEADER_LINES = 2  # above or below a date line
MAX_HEADER_WORDS = 12  # a longer line is prose, not a title or company

_INTERNSHIP = re.compile(r"\b(?:intern|internship|trainee|apprentice)\b", re.IGNORECASE)
_AT = re.compile(r"\s+at\s+")  # "Backend Engineer at Initech" (lower case "at" only)
_PIECE_SEPARATORS = re.compile(r"\s*[|•·\t]\s*|\s+[—–-]\s+")
_LEFTOVER_PUNCTUATION = " \t|,;:–—-()[]"
_LEGAL_SUFFIXES = frozenset(
    {"inc", "llc", "ltd", "pvt ltd", "co", "corp", "gmbh", "llp", "plc", "limited"}
)
# "7 years of experience", "7+ yrs of professional experience", "experience of 7 years"
_YEARS = r"(\d{1,2}(?:\.\d{1,2})?)\s*\+?\s*(?:years?|yrs?)"
_STATED = re.compile(
    rf"{_YEARS}(?:\s+of)?(?:\s+[\w-]+){{0,3}}?\s+(?:experience|exp)\b"
    rf"|\bexperience\s+of\s+(?:over\s+|about\s+)?{_YEARS}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Role:
    title: str | None
    company: str | None
    location: str | None
    dates: DateRange | None
    description: str  # the bullets under the role, as written
    is_internship: bool

    @property
    def is_current(self) -> bool:
        return self.dates is not None and self.dates.is_current

    def months(self, today: date) -> int | None:
        return self.dates.months(today) if self.dates else None


@dataclass(frozen=True)
class WorkHistory:
    roles: tuple[Role, ...]  # in resume order (usually newest first)
    total_months: int | None
    source: ExperienceSource | None  # where total_months came from
    current_title: str | None


# --- reading lines ------------------------------------------------------------


def _is_bullet(line: str) -> bool:
    return line.startswith("- ")


def _is_header_like(line: str) -> bool:
    """Could be a title or company line: not a bullet, not a wrapped sentence, not prose."""
    stripped = line.strip()
    return bool(
        stripped
        and not _is_bullet(stripped)
        and not stripped[0].islower()  # a wrapped bullet continues in lower case
        and not stripped.endswith(".")
        and len(stripped.split()) <= MAX_HEADER_WORDS
    )


def _remainder(line: str, dates: DateRange) -> str:
    """The date line without its date: "Engineer | Acme, Pune | " -> "Engineer | Acme, Pune"."""
    before, after = line[: dates.span[0]], line[dates.span[1] :]
    parts = [p.strip(_LEFTOVER_PUNCTUATION) for p in (before, after)]
    return " | ".join(p for p in parts if p)


# --- title, company, location -------------------------------------------------


def _split_company(piece: str) -> tuple[str, str | None]:
    """'Acme Fintech, Bengaluru' -> ('Acme Fintech', 'Bengaluru'); keeps 'Acme, Inc.' whole."""
    parts = [p.strip() for p in piece.split(",")]
    company, rest = parts[0], parts[1:]
    while rest and rest[0].rstrip(".").lower() in _LEGAL_SUFFIXES:
        company += ", " + rest.pop(0)
    return company, (", ".join(rest) or None)


def parse_header(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """(title, company, location) from a role's header lines."""
    pieces: list[str] = []
    for line in lines:
        if at := _AT.search(line):
            pieces += [line[: at.start()], line[at.end() :]]
        else:
            pieces += _PIECE_SEPARATORS.split(line)
    pieces = [p.strip(_LEFTOVER_PUNCTUATION) for p in pieces]
    pieces = [p for p in pieces if p]
    if not pieces:
        return None, None, None

    # The title is the piece with a job-title word; without one, resumes put it first.
    title = next((p for p in pieces if has_title_word(p)), pieces[0])
    others = [p for p in pieces if p is not title]
    if not others:
        return title, None, None
    company, location = _split_company(others[0])
    if location is None and len(others) > 1:
        location = others[1]  # "Engineer | Acme | Pune | 2020 – 2022"
    return title, company, location


# --- roles ------------------------------------------------------------------------


@dataclass
class _Anchor:
    line: int  # index of the date line
    dates: DateRange
    header: list[int]  # indices of the header lines (date line included)


def _anchors(lines: list[str], today: date) -> list[_Anchor]:
    anchors: list[_Anchor] = []
    for i, line in enumerate(lines):
        if _is_bullet(line) or not (found := find_date_ranges(line, today=today)):
            continue
        anchors.append(_Anchor(i, found[0], [i]))

    taken = {a.line for a in anchors}
    for anchor in anchors:
        above: list[int] = []
        j = anchor.line - 1
        while j >= 0 and len(above) < MAX_HEADER_LINES and j not in taken:
            if not _is_header_like(lines[j]):
                break
            above.insert(0, j)
            j -= 1
        below: list[int] = []
        if not above and not _remainder(lines[anchor.line], anchor.dates):
            j = anchor.line + 1  # table templates: the date sits above the title
            while j < len(lines) and len(below) < MAX_HEADER_LINES and j not in taken:
                if not _is_header_like(lines[j]) or find_date_ranges(lines[j], today=today):
                    break
                below.append(j)
                j += 1
        anchor.header = [*above, anchor.line, *below]
        taken.update(anchor.header)
    return anchors


def _roles_from_anchors(lines: list[str], anchors: list[_Anchor]) -> list[Role]:
    roles = []
    for k, anchor in enumerate(anchors):
        end = anchors[k + 1].header[0] if k + 1 < len(anchors) else len(lines)
        header_lines = [
            _remainder(lines[i], anchor.dates) if i == anchor.line else lines[i]
            for i in anchor.header
        ]
        title, company, location = parse_header([h for h in header_lines if h])
        description = "\n".join(lines[anchor.header[-1] + 1 : end]).strip()
        roles.append(
            Role(
                title=title,
                company=company,
                location=location,
                dates=anchor.dates,
                description=description,
                is_internship=bool(title and _INTERNSHIP.search(title)),
            )
        )
    return roles


def _undated_roles(lines: list[str]) -> list[Role]:
    """Roles of a resume without dates: each block of header lines followed by bullets."""
    roles: list[Role] = []
    i = 0
    while i < len(lines):  # each pass consumes at least one line
        header: list[str] = []
        while i < len(lines) and _is_header_like(lines[i]) and len(header) <= MAX_HEADER_LINES:
            header.append(lines[i])
            i += 1
        body: list[str] = []
        while i < len(lines) and not (_is_header_like(lines[i]) and body):
            body.append(lines[i])
            i += 1
        if header and any(_is_bullet(b) for b in body):
            title, company, location = parse_header(header)
            internship = bool(title and _INTERNSHIP.search(title))
            roles.append(Role(title, company, location, None, "\n".join(body).strip(), internship))
    return roles


# --- totals -------------------------------------------------------------------


def merged_months(ranges: list[DateRange], today: date) -> int:
    """Months covered by any of the ranges; overlaps count once."""
    spans = sorted((r.start.index, r.end_or(today).index) for r in ranges)
    total, current = 0, None
    for start, end in spans:
        if current is None or start > current[1] + 1:
            if current is not None:
                total += current[1] - current[0] + 1
            current = (start, end)
        else:
            current = (current[0], max(current[1], end))
    if current is not None:
        total += current[1] - current[0] + 1
    return total


def stated_months(text: str) -> int | None:
    """'7 years of experience' -> 84."""
    if found := _STATED.search(text):
        years = found.group(1) or found.group(2)
        return round(float(years) * 12)
    return None


def _current_title(roles: list[Role], today: date) -> str | None:
    dated = [r for r in roles if r.dates]
    if current := [r for r in dated if r.is_current]:
        return max(current, key=lambda r: r.dates.start if r.dates else 0).title
    if dated:
        return max(dated, key=lambda r: r.dates.end_or(today) if r.dates else 0).title
    return roles[0].title if roles else None  # undated: resumes list the newest first


def parse_experience(section: str, *, today: date, summary: str = "") -> WorkHistory:
    """Roles and total experience from an Experience section's text.

    `today` stands in for "Present"; evaluation passes the ground truth's as-of date.
    """
    lines = [line.strip() for line in section.split("\n")]
    anchors = _anchors(lines, today)
    roles = _roles_from_anchors(lines, anchors) if anchors else _undated_roles(lines)

    counted = [r.dates for r in roles if r.dates and not r.is_internship]
    total: int | None
    source: ExperienceSource | None
    if counted:
        total, source = merged_months(counted, today), "dates"
    elif (total := stated_months(summary)) is not None:
        source = "summary_statement"
    else:
        source = None
    return WorkHistory(tuple(roles), total, source, _current_title(roles, today))


def skill_months(history: WorkHistory, extractor: SkillExtractor, *, today: date) -> dict[str, int]:
    """Months each skill was used: the merged dates of the roles that mention it.

    Counts the same roles as total experience (no internships, no undated roles),
    so a skill can never exceed the total.
    """
    ranges: dict[str, list[DateRange]] = {}
    for role in history.roles:
        if role.dates is None or role.is_internship:
            continue
        text = f"{role.title or ''}\n{role.description}"
        for skill in {m.skill for m in extractor.find_mentions(text, SkillSource.EXPERIENCE)}:
            ranges.setdefault(skill, []).append(role.dates)
    return {skill: merged_months(found, today) for skill, found in sorted(ranges.items())}
