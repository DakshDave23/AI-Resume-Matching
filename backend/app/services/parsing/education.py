"""Education entries and the highest degree level (design doc §5.5, step 6).

- Degree: patterns mapped to a level (B.Tech, BSc, Bachelor's -> bachelor; M.Tech,
  MBA, Master's -> master; PhD -> doctorate; Diploma -> diploma; HSC, 12th ->
  high school). Two-letter abbreviations that are also words ("BE", "ME", "MS",
  "BA", "MA") count only in capitals.
- Field: the words after "in" ("B.Tech in Computer Science"), or after "of", a
  dash, comma or bracket when they name a known field ("Master of Computer
  Applications", "B.E. (Electronics and Communication)").
- Institution: the piece of the entry containing University, College, Institute,
  School, ... (rules, not spaCy ORG: see the contact parser for why).
- Year: the latest four-digit year in the entry, so "2016 – 2020" gives 2020.

Entries are grouped line by line: a line with a degree starts a new entry when
the current one already has a degree; likewise for an institution. That handles
both "Degree, Institution, Year" on one line and an institution line above the
degree line. A line counts as one degree: "HSC (12th)" is one entry, and a dual
degree counts at its highest level.

`find_degrees` and `find_field` are shared with the JD parser.
"""

import re
from dataclasses import dataclass

from app.models.enums import DegreeLevel

_APOSTROPHES = "'" + chr(0x2019)  # straight and curly (U+2019)
_POSSESSIVE = f"(?:[{_APOSTROPHES}]?s)?"  # Master's (either apostrophe), Masters

# (pattern, level), matched case-insensitively. Dotted forms need their dots;
# undotted short forms are listed only where they can't be an English word.
_DEGREE_PATTERNS: list[tuple[str, DegreeLevel]] = [
    (r"ph\.?\s?d\.?|d\.?\s?phil\.?|doctorate|doctor\s+of\s+philosophy", DegreeLevel.DOCTORATE),
    (r"post[\s-]?graduate\s+diploma|pg\s?diploma|pgdm", DegreeLevel.MASTER),
    (
        r"m\.\s?tech|mtech|m\.e\.|m\.\s?sc\.?|msc|m\.s\.|m\.\s?eng|meng|m\.?b\.?a\.?|m\.?c\.?a\.?"
        r"|m\.\s?com|mcom|m\.a\.|m\.\s?phil|mphil|m\.\s?arch|m\.\s?pharm"
        rf"|m\.\s?ed|llm|master{_POSSESSIVE}(?:\s+degree)?",
        DegreeLevel.MASTER,
    ),
    (
        r"b\.\s?tech|btech|b\.e\.|b\.\s?sc\.?|bsc|b\.s\.|b\.\s?eng|beng|b\.?c\.?a\.?|b\.?b\.?a\.?"
        r"|b\.\s?com|bcom|b\.a\.|b\.\s?arch|barch|b\.\s?pharm|bpharm|b\.\s?des|llb|mbbs"
        rf"|bachelor{_POSSESSIVE}(?:\s+degree)?|undergraduate\s+degree",
        DegreeLevel.BACHELOR,
    ),
    (
        rf"associate{_POSSESSIVE}\s+degree|associate\s+of\s+(?:arts|science)|diploma",
        DegreeLevel.DIPLOMA,
    ),
    (
        r"high\s+school(?:\s+diploma)?|higher\s+secondary|senior\s+secondary|secondary\s+school"
        r"|hsc|ssc"
        r"|12th|10th|class\s+(?:xii|x|12|10)|intermediate|a[\s-]levels?|ged",
        DegreeLevel.HIGH_SCHOOL,
    ),
]
# Case-sensitive: "be", "me", "ma" are words; "BE", "MS" are degrees, unless "MS Excel".
_MS_PRODUCTS = r"(?!\s+(?:Office|Excel|Word|SQL|Access|PowerPoint|Project|Dynamics|Teams|Azure))"
_UPPER_ONLY: list[tuple[str, DegreeLevel]] = [
    (rf"ME|MS{_MS_PRODUCTS}|MA", DegreeLevel.MASTER),
    (r"BE|BS|BA", DegreeLevel.BACHELOR),
]
_BEFORE = r"(?<![\w.])"
_AFTER = rf"(?![\w{_APOSTROPHES}])"
_DEGREE_REGEXES = [
    (re.compile(rf"{_BEFORE}(?:{p}){_AFTER}", re.IGNORECASE), level)
    for p, level in _DEGREE_PATTERNS
] + [(re.compile(rf"{_BEFORE}(?:{p}){_AFTER}"), level) for p, level in _UPPER_ONLY]
# "Bachelor of Technology", "Master of Computer Applications": the "of ..." is part of the name.
_OF_NAME = re.compile(r"\s+of\s+((?:[A-Z][a-z]+|and)(?:\s+(?:[A-Z][a-z]+|and|&))*)")

# Fields named in "of X" or after a comma only count when they are known fields.
KNOWN_FIELDS = (
    "Computer Science", "Computer Science and Engineering", "Computer Engineering",
    "Computer Applications", "Information Technology", "Information Systems",
    "Software Engineering", "Data Science", "Artificial Intelligence", "Machine Learning",
    "Electronics", "Electronics and Communication", "Electronics and Telecommunication",
    "Electrical Engineering", "Electrical and Electronics Engineering",
    "Mechanical Engineering", "Civil Engineering", "Chemical Engineering",
    "Instrumentation", "Biotechnology", "Mathematics", "Applied Mathematics", "Statistics",
    "Physics", "Chemistry", "Biology", "Economics", "Commerce", "Accounting", "Accountancy",
    "Finance", "Business Administration", "Management", "Marketing", "Human Resources",
    "Operations Research", "Psychology", "English", "Design",
)  # fmt: skip
_KNOWN_FIELDS = {f.lower(): f for f in KNOWN_FIELDS}

_FIELD_AFTER_IN = re.compile(r"^\s*,?\s*in\s+([^,|;(\n]+)", re.IGNORECASE)
_FIELD_AFTER_PUNCT = re.compile(r"^\s*(?:[,:(]|[-–—])\s*([^,|;()\n]+)")
_FIELD_STOP = re.compile(r"\s+(?:from|at)\s+|\s+[-–—]\s+|\s*(?<!\d)(?:19|20)\d{2}(?!\d).*$")
MAX_FIELD_WORDS = 8

_INSTITUTION_WORDS = re.compile(
    r"\b(?:universit\w*|college|institute|institution|school|academy|polytechnic"
    r"|vidyalaya|vidyapeeth|IIT|NIT|IIIT|BITS)\b",
    re.IGNORECASE,
)
_PIECE_SEPARATORS = re.compile(r"\s*[,|;\t]\s*|\s+[-–—]\s+|\s+(?:from|at)\s+")
_YEAR = re.compile(r"(?<!\d)(19[5-9]\d|20\d\d)(?!\d)")
_DATES_AND_BRACKETS = re.compile(
    r"\([^)]*\d[^)]*\)|(?<!\d)(?:19|20)\d{2}(?!\d)(?:\s*[-–—]\s*(?:(?:19|20)\d{2}|present))?",
    re.IGNORECASE,
)
_TRIM = " \t,;:|-–—()."


@dataclass(frozen=True)
class DegreeMatch:
    text: str  # as written: "B.Tech", "Bachelor of Technology"
    level: DegreeLevel
    span: tuple[int, int]


@dataclass(frozen=True)
class EducationEntry:
    degree: str | None
    level: DegreeLevel | None
    field: str | None
    institution: str | None
    year: int | None


@dataclass(frozen=True)
class EducationResult:
    entries: tuple[EducationEntry, ...]  # in resume order

    @property
    def highest_level(self) -> DegreeLevel | None:
        levels = [e.level for e in self.entries if e.level is not None]
        return max(levels) if levels else None


def find_degrees(text: str) -> list[DegreeMatch]:
    """Degree mentions in `text`, in order, without overlaps (the longest wins)."""
    found: list[DegreeMatch] = []
    for regex, level in _DEGREE_REGEXES:
        for match in regex.finditer(text):
            start, end = match.span()
            long_form = match.group(0).lower().startswith(("bachelor", "master", "associate"))
            if long_form and (of := _OF_NAME.match(text, end)):  # "Bachelor of Technology"
                end = of.end()
            found.append(DegreeMatch(text[start:end], level, (start, end)))
    found.sort(key=lambda d: (d.span[0], -(d.span[1] - d.span[0])))
    kept: list[DegreeMatch] = []
    for degree in found:
        if not kept or degree.span[0] >= kept[-1].span[1]:
            kept.append(degree)
    return kept


def _known_field(text: str) -> str | None:
    return _KNOWN_FIELDS.get(" ".join(text.split()).lower())


def _clean_field(text: str) -> str | None:
    text = _FIELD_STOP.split(text, maxsplit=1)[0].strip(_TRIM)
    return text if text and len(text.split()) <= MAX_FIELD_WORDS else None


def find_field(degree: DegreeMatch, text: str) -> str | None:
    """The field of study written after a degree in `text`."""
    after = text[degree.span[1] :]
    if found := _FIELD_AFTER_IN.match(after):
        return _clean_field(found.group(1))
    if (of := _OF_NAME.search(degree.text)) and (field := _known_field(of.group(1))):
        return field  # "Master of Computer Applications"
    if found := _FIELD_AFTER_PUNCT.match(after):  # "B.E. (Electronics)", "B.Tech - IT"
        candidate = _clean_field(found.group(1))
        if candidate and _known_field(candidate):
            return candidate
    return None


def _institution(text: str, skip: list[DegreeMatch]) -> str | None:
    """The first piece of `text` that names a school, ignoring the degree's own words."""
    for degree in skip:  # "High School Diploma" names a degree, not a school
        text = text.replace(degree.text, " " * len(degree.text), 1)
    for piece in _PIECE_SEPARATORS.split(text):
        if _INSTITUTION_WORDS.search(piece):
            name = " ".join(_DATES_AND_BRACKETS.sub(" ", piece).split()).strip(_TRIM)
            if name:
                return name
    return None


@dataclass
class _Draft:
    lines: list[str]
    degree: DegreeMatch | None = None
    degree_line: str = ""
    has_institution: bool = False


def parse_education(section: str) -> EducationResult:
    """Entries from an Education section's text."""
    drafts: list[_Draft] = []
    for raw in section.split("\n"):
        line = raw.strip().removeprefix("- ")
        if not line:
            continue
        degrees = find_degrees(line)
        # One degree per line: "HSC (12th)" is one entry, and so is "B.Tech + M.Tech
        # (Dual Degree)", which counts at its highest level.
        degree = max(degrees, key=lambda d: d.level) if degrees else None
        has_institution = _institution(line, [degree] if degree else []) is not None
        current = drafts[-1] if drafts else None
        if (
            current is None
            or (degree is not None and current.degree is not None)
            or (degree is None and has_institution and current.has_institution)
        ):
            current = _Draft([])
            drafts.append(current)
        current.lines.append(line)
        if degree is not None and current.degree is None:
            current.degree, current.degree_line = degree, line
        current.has_institution = current.has_institution or has_institution

    entries = []
    for draft in drafts:
        text = "\n".join(draft.lines)
        degree = draft.degree
        # Blank only the entry's own degree: "Lincoln High School" also contains "High School".
        institution = _institution(text, [degree] if degree else [])
        if degree is None and institution is None:
            continue  # a stray line: "CGPA 8.5", "Relevant coursework: ..."
        years = [int(y) for y in _YEAR.findall(text)]
        entries.append(
            EducationEntry(
                degree=degree.text if degree else None,
                level=degree.level if degree else None,
                field=find_field(degree, draft.degree_line) if degree else None,
                institution=institution,
                year=max(years) if years else None,
            )
        )
    return EducationResult(tuple(entries))
