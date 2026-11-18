"""Split resume text into sections (design doc §5.5, step 1).

A line is a section header when it

- has 5 words or fewer, no sentence punctuation and no digits,
- starts with a capital letter (a wrapped sentence that happens to end in
  "experience" continues in lower case),
- does not follow a line that obviously continues ("..., Spring and"), and
- fuzzy-matches a known header: score >= 85 when the line *looks* like a header
  (ALL CAPS or a trailing colon), >= 90 otherwise.

Text before the first header is the contact block. Headers we recognise but don't
parse (Hobbies, Languages, ...) open an "other" section, so their text doesn't
leak into the section above them.

The engine takes the header dictionary as an argument; the JD parser (step 14)
reuses it with Requirements / Nice to have / Responsibilities headers.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from rapidfuzz import fuzz, process

CONTACT = "contact"
OTHER = "other"

MAX_HEADER_WORDS = 5
MIN_SCORE_WITH_CUE = 85.0  # ALL CAPS or trailing colon
MIN_SCORE_PLAIN = 90.0

RESUME_HEADERS: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "profile",
        "objective",
        "about me",
        "about",
        "professional summary",
        "career summary",
        "profile summary",
        "professional profile",
        "career objective",
        "executive summary",
        "summary of qualifications",
        "overview",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "employment",
        "career history",
        "work history",
        "relevant experience",
        "professional background",
        "internships",
        "internship experience",
    ),
    "education": (
        "education",
        "academics",
        "academic qualifications",
        "educational qualifications",
        "academic background",
        "education and training",
        "academic details",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core competencies",
        "tech stack",
        "key skills",
        "skill set",
        "skills summary",
        "competencies",
        "technologies",
        "technical expertise",
        "areas of expertise",
        "tools and technologies",
        "technical proficiencies",
    ),
    "projects": (
        "projects",
        "key projects",
        "academic projects",
        "personal projects",
        "selected projects",
        "notable projects",
        "side projects",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses",
        "courses",
        "licenses and certifications",
        "certifications and courses",
        "courses and certifications",
        "training",
        "professional development",
    ),
    OTHER: (
        "achievements",
        "awards",
        "honors and awards",
        "accomplishments",
        "publications",
        "languages",
        "interests",
        "hobbies",
        "hobbies and interests",
        "volunteer experience",
        "volunteering",
        "extracurricular activities",
        "positions of responsibility",
        "references",
        "personal details",
        "personal information",
        "declaration",
    ),
}

# Sentence punctuation, separators used in role lines ("Engineer | Acme"), and digits.
_NOT_A_HEADER = re.compile(r"[.,;!?|@\d]")
_NON_WORD = re.compile(r"[^\w\s]")
# A line ending like this continues on the next line, so the next line is not a header.
# Case-sensitive on purpose: "Team A" or "Grade A" ends a line; "with a" does not.
_CONTINUES = re.compile(r"(?:[,&/-]|\b(?:and|or|of|in|with|the|a|an|to|for|at|on|by))\s*$")


def normalize_header(text: str) -> str:
    """'Licenses & Certifications:' -> 'licenses and certifications'."""
    text = text.strip().removesuffix(":").replace("&", " and ")
    return " ".join(_NON_WORD.sub(" ", text).lower().split())


@dataclass(frozen=True)
class HeaderMatch:
    section: str
    variant: str  # the dictionary entry it matched
    score: float  # rapidfuzz ratio, 0-100


class HeaderDictionary:
    """Known header variants and the section each one opens."""

    def __init__(self, headers: Mapping[str, Iterable[str]]) -> None:
        section_of: dict[str, str] = {}
        for section, variants in headers.items():
            for variant in variants:
                key = normalize_header(variant)
                if key in section_of and section_of[key] != section:
                    sections = f"{section_of[key]!r} and {section!r}"
                    raise ValueError(f"header {variant!r} is listed for both {sections}")
                section_of[key] = section
        self.section_of = section_of
        self.variants = list(section_of)

    def match(self, line: str) -> HeaderMatch | None:
        """The section `line` opens, or None if it isn't a header."""
        stripped = line.strip()
        if not stripped or not stripped[0].isupper():
            return None
        has_colon = stripped.endswith(":")
        body = stripped.removesuffix(":")
        if ":" in body or _NOT_A_HEADER.search(body):
            return None
        key = normalize_header(body)
        if not key or len(key.split()) > MAX_HEADER_WORDS:
            return None

        best = process.extractOne(key, self.variants, scorer=fuzz.ratio, processor=None)
        if best is None:
            return None
        variant, score, _ = best
        looks_like_header = has_colon or body.isupper()
        if score < (MIN_SCORE_WITH_CUE if looks_like_header else MIN_SCORE_PLAIN):
            return None
        return HeaderMatch(self.section_of[variant], variant, score)


RESUME_HEADER_DICTIONARY = HeaderDictionary(RESUME_HEADERS)


@dataclass(frozen=True)
class Section:
    name: str  # "contact", a key of the header dictionary, or "other"
    header: str | None  # the header line as written; None for the contact block
    text: str


@dataclass(frozen=True)
class Segmentation:
    sections: tuple[Section, ...]  # in document order; a name can repeat

    def names(self) -> list[str]:
        """Section names in first-seen order, without repeats."""
        return list(dict.fromkeys(s.name for s in self.sections))

    def text_of(self, name: str) -> str:
        """All text under `name`; repeated sections are joined by a blank line."""
        return "\n\n".join(s.text for s in self.sections if s.name == name and s.text)

    def as_dict(self) -> dict[str, str]:
        """Section name -> text, as stored in resumes.sections."""
        return {name: self.text_of(name) for name in self.names()}


def segment(text: str, headers: HeaderDictionary = RESUME_HEADER_DICTIONARY) -> Segmentation:
    """Split cleaned text (one item per line) into sections."""
    sections: list[Section] = []
    name, header = CONTACT, None
    body: list[str] = []
    previous = ""  # last non-blank line

    def close() -> None:
        content = "\n".join(body).strip("\n")
        if header is not None or content:  # an empty contact block is dropped
            sections.append(Section(name, header, content))

    for line in text.split("\n"):
        found = None if _CONTINUES.search(previous) else headers.match(line)
        if found is not None:
            close()
            name, header, body = found.section, line.strip(), []
        else:
            body.append(line)
        if line.strip():
            previous = line
    close()
    return Segmentation(tuple(sections))
