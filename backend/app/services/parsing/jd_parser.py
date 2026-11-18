"""Read a job description into requirements (design doc §5.4).

1. Title, company and location come from "Job Title:", "Company:" and "Location:"
   labels; without a title label the first short line is the title. Seniority is
   read from the title's words (Senior, Lead, ...); a title without one is mid level.
2. Sections: Responsibilities, Requirements (Qualifications, Must have) and Preferred
   (Nice to have, Bonus), found by the resume section engine with a JD header
   dictionary. "About us" and benefits text is not scanned for skills. A JD with
   none of those headers is read whole.
3. Required or preferred, decided per skill mention:
   - the section decides first (Requirements: required, Nice to have: preferred);
   - cues in the same clause override it. "Must", "required", "a plus", "bonus"
     and "preferred" (predicates) outrank "strong", "proficient", "familiarity
     with" and "exposure to" (modifiers), so "Strong communication skills are a
     plus" is preferred. When a clause has both kinds, the nearest cue wins:
     "Java is required and Kotlin is a plus";
   - a modifier like "strong" doesn't promote a skill out of a Nice-to-have list;
   - with no signal at all (Responsibilities), a skill is required.
   A skill mentioned several times takes its strongest signal; ties go to required.
4. Years: "5+ years", "3–5 years", "minimum of 4 years", "at least 2 yrs". When the
   years lead straight into skills ("4+ years of Java and Spring Boot") they are
   those skills' `min_years`. The overall minimum is the largest figure in a
   required general experience sentence.
5. Education: the degree patterns from the resume parser. The required level is the
   lowest one a required clause accepts ("Bachelor's or Master's" -> bachelor's).
   Fields come from "in Computer Science, IT or a related field". "Or equivalent
   experience" marks education as soft.
6. Requirement rows: every bullet (or prose sentence) under Responsibilities,
   Requirements and Preferred, with a category and a type.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum

from app.models.enums import (
    DegreeLevel,
    RequirementCategory,
    RequirementType,
    Seniority,
    SkillSource,
)
from app.services.parsing.education import KNOWN_FIELDS, DegreeMatch, find_degrees, find_field
from app.services.parsing.sections import CONTACT, HeaderDictionary, Segmentation, segment
from app.services.parsing.skills import SkillExtractor, SkillMention, get_skill_extractor

REQUIRED, PREFERRED = RequirementType.REQUIRED, RequirementType.PREFERRED

# --- Sections -------------------------------------------------------------------------

ABOUT = "about"
RESPONSIBILITIES = "responsibilities"
REQUIREMENTS = "requirements"
PREFERRED_SECTION = "preferred"
BENEFITS = "benefits"

JD_HEADERS: dict[str, list[str]] = {
    ABOUT: [
        "about the role", "about the job", "about the position", "about the team",
        "about us", "about the company", "who we are", "the role", "role overview",
        "overview", "job summary", "position summary", "summary", "job description",
        "introduction",
    ],
    RESPONSIBILITIES: [
        "responsibilities", "key responsibilities", "job responsibilities",
        "roles and responsibilities", "role and responsibilities", "duties", "key duties",
        "what you will do", "what you'll do", "what you will be doing",
        "what you'll be doing", "your responsibilities", "your role", "day to day",
    ],
    REQUIREMENTS: [
        "requirements", "job requirements", "key requirements", "minimum requirements",
        "qualifications", "minimum qualifications", "basic qualifications",
        "required qualifications", "must have", "must haves", "must have skills",
        "required skills", "key skills", "skills", "technical skills",
        "skills and experience", "skills and qualifications", "what you will need",
        "what you'll need", "what you bring", "what we are looking for",
        "what we're looking for", "who you are", "about you", "essential skills",
        "eligibility",
    ],
    PREFERRED_SECTION: [
        "preferred", "preferred qualifications", "preferred skills", "nice to have",
        "nice to haves", "good to have", "bonus", "bonus points", "bonus skills",
        "desirable", "desirable skills", "desired skills", "desired qualifications",
        "pluses", "additional qualifications",
    ],
    BENEFITS: [
        "what we offer", "benefits", "perks", "perks and benefits", "why join us",
        "why work with us", "compensation", "compensation and benefits",
        "what's in it for you", "how to apply", "equal opportunity",
    ],
}  # fmt: skip
JD_HEADER_DICTIONARY = HeaderDictionary(JD_HEADERS)
SCANNED_SECTIONS = (RESPONSIBILITIES, REQUIREMENTS, PREFERRED_SECTION)

# --- Title, company, location -----------------------------------------------------------

_LABELS = {
    "title": r"job\s+title|position|title",
    "company": r"company|organi[sz]ation|employer",
    "location": r"(?:job\s+|work\s+)?location",
}
_LABEL_LINE = re.compile(
    rf"^[ \t]*(?:(?P<title>{_LABELS['title']})|(?P<company>{_LABELS['company']})"
    rf"|(?P<location>{_LABELS['location']}))[ \t]*:[ \t]*(?P<value>\S.*?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
MAX_TITLE_WORDS = 10
_SENIORITY = [  # checked in this order: "Senior Lead" is lead
    (Seniority.PRINCIPAL, r"principal|distinguished"),
    (Seniority.LEAD, r"lead|staff|head"),
    (Seniority.SENIOR, r"senior|sr\.?"),
    (Seniority.JUNIOR, r"junior|jr\.?|entry[\s-]level|graduate|trainee|intern|fresher"),
    (Seniority.MID, r"mid|mid[\s-]level|intermediate"),
]
_SENIORITY_REGEXES = [
    (level, re.compile(rf"\b(?:{words})(?!\w)", re.IGNORECASE)) for level, words in _SENIORITY
]

# --- Required / preferred cues -----------------------------------------------------------


class _Signal(IntEnum):
    """How strongly a mention says required or preferred; the strongest wins."""

    DEFAULT = 0  # no section, no cue: required
    SECTION = 1  # under Requirements or Nice to have
    MODIFIER = 2  # "strong", "proficient", "familiarity with", "exposure to"
    PREDICATE = 3  # "must", "required", "is a plus", "preferred"


# Checked in this order; a later cue can't overlap an earlier one ("not required").
_CUES = [
    (
        PREFERRED,
        _Signal.PREDICATE,
        r"not\s+(?:strictly\s+)?(?:required|mandatory|necessary|a\s+must)|nice[\s-]to[\s-]have"
        r"|good[\s-]to[\s-]have|an?\s+(?:\w+\s+)?(?:plus|bonus|advantage)|bonus|preferred"
        r"|preferably|preferable|desirable|desired|advantageous|ideally|optional",
    ),
    (REQUIRED, _Signal.PREDICATE, r"must|required|mandatory|essential|minimum|necessary"),
    (
        REQUIRED,
        _Signal.MODIFIER,
        r"strong|proficient|proficiency|solid|expert|expertise|excellent|in-depth",
    ),
    (
        PREFERRED,
        _Signal.MODIFIER,
        r"familiarity|familiar|exposure|awareness|basic\s+(?:knowledge|understanding)",
    ),
]
_CUE_REGEXES = [
    (kind, signal, re.compile(rf"\b(?:{words})\b", re.IGNORECASE)) for kind, signal, words in _CUES
]

# --- Years ------------------------------------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}  # fmt: skip
_N = rf"(?:\d{{1,2}}(?:\.\d)?|{'|'.join(_NUMBER_WORDS)})"
_Y = r"(?:years?|yrs?)\b(?!\s+(?:old|ago))"
_YEARS = re.compile(
    rf"\b(?:(?P<low>{_N})\s*(?:-|–|—|to)\s*(?P<high>{_N})\s*\+?\s*{_Y}"
    rf"|(?:minimum(?:\s+of)?|min\.?|at\s+least|over|more\s+than|no\s+less\s+than)"
    rf"\s+(?P<least>{_N})\s*\+?\s*{_Y}"
    rf"|(?P<n>{_N})\s*(?:\+\s*)?(?:or\s+more\s+)?{_Y}(?:\s*\+|\s+(?:or\s+more|and\s+above))?)",
    re.IGNORECASE,
)
MAX_YEARS = 40.0
# Words allowed between the years and the skills they apply to: "5+ years of hands-on
# experience with Java". Anything else ("as a data scientist") means general experience.
_YEARS_TO_SKILL = re.compile(
    r"(?:\s*\b(?:of|in|with|using|on|working|hands-on|professional|relevant|industry"
    r"|commercial|practical|production|proven|programming|development|developing|building"
    r"|experience|exp)\b\.?)*\s*",
    re.IGNORECASE,
)
_SKILL_TO_YEARS = re.compile(r"\s*(?:[:(\-–—]\s*|for\s+)?", re.IGNORECASE)  # "Java (5+ years)"
_SKILL_JOINER = re.compile(r"\s*(?:,|/|&|,?\s*\band\b|,?\s*\bor\b)?\s*", re.IGNORECASE)

# --- Education --------------------------------------------------------------------------

# Degree words that are also everyday JD words: "work with the BA", "intermediate SQL",
# "the Scrum Master", "a level of ownership". They count only beside an education word.
_AMBIGUOUS_DEGREES = frozenset(
    {"me", "ms", "ma", "be", "bs", "ba", "intermediate", "master", "masters", "a level"}
)
_EDUCATION_WORDS = re.compile(
    r"\b(?:degree|graduate|graduation|qualification|education|university|college|field"
    r"|equivalent)\b",
    re.IGNORECASE,
)
_IN_A_FIELD = re.compile(r"\bin\s+[A-Z]")  # "BS in Computer Science"
_BARE_DEGREE = re.compile(r"\b(?:university\s+|college\s+)?degree\b", re.IGNORECASE)
_FIELDS_START = re.compile(r"\bin\s+(?:the\s+field\s+of\s+)?", re.IGNORECASE)
_FIELDS_END = re.compile(
    r"[.;:()\n]|\s+(?:from|at|with|preferably|preferred|required|is|are)\b"
    r"|,?\s+(?:or|and)\s+(?:an?\s+)?equivalent\b|\s+and\s+(?:\d|at\s+least|a\s+minimum)",
    re.IGNORECASE,
)
_FIELD_SEPARATORS = re.compile(r"\s*,\s*(?:and\s+|or\s+)?|\s*/\s*|\s+or\s+", re.IGNORECASE)
_FIELD_ABBREVIATIONS = {
    "cs": "Computer Science",
    "cse": "Computer Science and Engineering",
    "it": "Information Technology",
    "ece": "Electronics and Communication",
    "ee": "Electrical Engineering",
}
_FIELD_NAMES = {f.lower(): f for f in KNOWN_FIELDS} | _FIELD_ABBREVIATIONS
_SMALL_WORDS = frozenset({"and", "of", "&"})
MAX_FIELD_WORDS = 4
_EQUIVALENT_EXPERIENCE = re.compile(
    r"\bequivalent\s+(?:(?:practical|professional|work|relevant|industry|hands-on)\s+)?"
    r"experience\b|\bexperience\s+in\s+lieu\s+of\b|\bin\s+lieu\s+of\s+(?:a\s+)?degree\b",
    re.IGNORECASE,
)

# --- Splitting text into bullets, sentences and clauses -----------------------------------

_BULLET = re.compile(r"^(?:[-*•]\s+|\d{1,2}[.)]\s+)")
_CONTINUES = re.compile(r"(?:[,&/(-]|\b(?:and|or|of|in|with|the|a|an|to|for|on|by))$")
_SENTENCE_END = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?])\s+(?=[A-Z(])")
_CLAUSE_END = re.compile(rf"\s*;\s*|{_SENTENCE_END.pattern}")
_LIST_LABEL = re.compile(r"^[^:,]{1,40}:")
MAX_LIST_ITEM_WORDS = 3


# --- Results ----------------------------------------------------------------------------


@dataclass(frozen=True)
class JobSkill:
    name: str  # canonical taxonomy name
    requirement_type: RequirementType
    min_years: float | None  # from "5+ years of Java"
    source_text: str  # the JD bullet or sentence it came from

    @property
    def default_weight(self) -> float:
        """job_skills.weight before any recruiter edit (design doc §4)."""
        return 1.0 if self.requirement_type == REQUIRED else 0.5


@dataclass(frozen=True)
class JobRequirement:
    text: str
    category: RequirementCategory
    requirement_type: RequirementType


@dataclass(frozen=True)
class JobParse:
    title: str | None
    company: str | None
    location: str | None
    seniority: Seniority
    skills: tuple[JobSkill, ...]  # in order of first mention
    unmapped: tuple[str, ...]  # skill-list items in no taxonomy
    min_experience_years: float | None
    max_experience_years: float | None
    degree_level: DegreeLevel | None  # the lowest degree a required clause accepts
    preferred_degree_level: DegreeLevel | None  # "Master's preferred"; informational
    fields_of_study: tuple[str, ...]
    accepts_equivalent_experience: bool
    requirements: tuple[JobRequirement, ...]  # in JD order; the index is the position
    segmentation: Segmentation

    def skill_names(self, kind: RequirementType) -> list[str]:
        return [s.name for s in self.skills if s.requirement_type == kind]

    @property
    def required_skills(self) -> list[str]:
        return self.skill_names(REQUIRED)

    @property
    def preferred_skills(self) -> list[str]:
        return self.skill_names(PREFERRED)


@dataclass(frozen=True)
class YearsPhrase:
    min_years: float | None
    max_years: float | None
    span: tuple[int, int]


@dataclass(frozen=True)
class _Decision:
    kind: RequirementType
    signal: _Signal


@dataclass(frozen=True)
class _Cue:
    kind: RequirementType
    signal: _Signal
    span: tuple[int, int]


# --- Title ------------------------------------------------------------------------------


def _labels(text: str) -> dict[str, str]:
    """The first "Job Title:", "Company:" and "Location:" values."""
    found: dict[str, str] = {}
    for match in _LABEL_LINE.finditer(text):
        name = next(n for n in _LABELS if match.group(n))
        found.setdefault(name, match.group("value"))
    return found


def _first_short_line(text: str) -> str | None:
    """A JD without a title label usually opens with the title."""
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or _LABEL_LINE.match(line):
            continue
        if len(line.split()) <= MAX_TITLE_WORDS and not line.endswith((".", "!", "?", ",", ":")):
            return line
        return None
    return None


def seniority_of(title: str | None) -> Seniority:
    for level, regex in _SENIORITY_REGEXES:
        if title and regex.search(title):
            return level
    return Seniority.MID


# --- Required / preferred ----------------------------------------------------------------


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _cues(clause: str, mentions: list[SkillMention]) -> list[_Cue]:
    """Cue words in a clause, minus any inside a skill name ("SOLID principles")."""
    taken = [m.span for m in mentions if m.span is not None]
    cues: list[_Cue] = []
    for kind, signal, regex in _CUE_REGEXES:
        for match in regex.finditer(clause):
            if not any(_overlaps(match.span(), other) for other in taken):
                taken.append(match.span())
                cues.append(_Cue(kind, signal, match.span()))
    return cues


def _section_decision(section: str | None) -> _Decision:
    if section == REQUIREMENTS:
        return _Decision(REQUIRED, _Signal.SECTION)
    if section == PREFERRED_SECTION:
        return _Decision(PREFERRED, _Signal.SECTION)
    return _Decision(REQUIRED, _Signal.DEFAULT)  # Responsibilities, or no section


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(a[0] - b[1], b[0] - a[1], 0)


def _decide(section: str | None, cues: list[_Cue], at: tuple[int, int] | None) -> _Decision:
    """Required or preferred for a mention at `at` (or the whole clause when None)."""
    for signal in (_Signal.PREDICATE, _Signal.MODIFIER):
        tier = [c for c in cues if c.signal == signal]
        if signal == _Signal.MODIFIER and section == PREFERRED_SECTION:
            # "Strong knowledge of Kubernetes" in a Nice-to-have list is still nice to have.
            tier = [c for c in tier if c.kind == PREFERRED]
        if not tier:
            continue
        if at is None:
            kind = REQUIRED if any(c.kind == REQUIRED for c in tier) else PREFERRED
            return _Decision(kind, signal)
        nearest = min(tier, key=lambda c: (_distance(c.span, at), c.kind != REQUIRED))
        return _Decision(nearest.kind, signal)
    return _section_decision(section)


# --- Years ------------------------------------------------------------------------------


def _number(text: str) -> float:
    return float(_NUMBER_WORDS.get(text.lower()) or text)


def find_years(text: str) -> list[YearsPhrase]:
    """'3–5 years' -> (3, 5); '5+ years', 'minimum of 4 years', 'at least 2 yrs' -> (n, None)."""
    phrases = []
    for match in _YEARS.finditer(text):
        if match.group("low"):
            low, high = _number(match.group("low")), _number(match.group("high"))
            if not low <= high <= MAX_YEARS:
                continue
            phrases.append(YearsPhrase(low, high, match.span()))
        else:
            least = _number(match.group("least") or match.group("n"))
            if least <= MAX_YEARS:
                phrases.append(YearsPhrase(least, None, match.span()))
    return phrases


def _skills_for_years(clause: str, phrase: YearsPhrase, mentions: list[SkillMention]) -> list[str]:
    """Skills the years apply to: '4+ years of Java and Spring Boot', 'Java (5+ years)'."""
    spans = [(m.span, m.skill) for m in mentions if m.span is not None]
    after = [(span, skill) for span, skill in spans if span[0] >= phrase.span[1]]
    if after and _YEARS_TO_SKILL.fullmatch(clause[phrase.span[1] : after[0][0][0]]):
        skills, end = [after[0][1]], after[0][0][1]
        for span, skill in after[1:]:
            if not _SKILL_JOINER.fullmatch(clause[end : span[0]]):
                break
            skills.append(skill)
            end = span[1]
        return skills
    before = [(span, skill) for span, skill in spans if span[1] <= phrase.span[0]]
    if before and _SKILL_TO_YEARS.fullmatch(clause[before[-1][0][1] : phrase.span[0]]):
        return [before[-1][1]]
    return []


# --- Education --------------------------------------------------------------------------


def _plain(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def find_education(clause: str) -> list[DegreeMatch]:
    """Degrees a JD clause asks for. A bare 'degree in X' counts as a bachelor's."""
    degrees = find_degrees(clause)
    if not (_EDUCATION_WORDS.search(clause) or _IN_A_FIELD.search(clause)):
        degrees = [d for d in degrees if _plain(d.text) not in _AMBIGUOUS_DEGREES]
    if not degrees and (bare := _BARE_DEGREE.search(clause)):
        degrees = [DegreeMatch(bare.group(0), DegreeLevel.BACHELOR, bare.span())]
    return degrees


def _field_names(piece: str) -> list[str]:
    piece = re.sub(r"^(?:an?|the)\s+", "", piece.strip(" ,"), flags=re.IGNORECASE)
    key = " ".join(piece.split()).lower()
    if not key:
        return []
    if key in _FIELD_NAMES:
        return [_FIELD_NAMES[key]]
    parts = re.split(r"\s+(?:and|&)\s+", key)  # "Mathematics and Statistics"
    if len(parts) > 1 and all(p in _FIELD_NAMES for p in parts):
        return [_FIELD_NAMES[p] for p in parts]
    words = piece.split()
    if len(words) <= MAX_FIELD_WORDS and all(w[0].isupper() or w in _SMALL_WORDS for w in words):
        return [piece]  # a field we don't list, written as a name: "Quantitative Finance"
    return []  # "a related field", "equivalent experience", "any engineering discipline"


def find_fields(clause: str, degrees: list[DegreeMatch]) -> list[str]:
    """'... in Statistics, Computer Science, Mathematics or a related field' -> three fields."""
    last = degrees[-1]
    start = _FIELDS_START.search(clause, last.span[1])
    if start is None:
        field = find_field(last, clause)  # "Master of Computer Applications"
        return [field] if field else []
    rest = clause[start.end() :]
    if end := _FIELDS_END.search(rest):
        rest = rest[: end.start()]
    return [name for piece in _FIELD_SEPARATORS.split(rest) for name in _field_names(piece)]


# --- Splitting --------------------------------------------------------------------------


def _units(text: str) -> Iterator[str]:
    """Bullets (wrapped lines joined) and the sentences of prose paragraphs."""
    bullet: list[str] = []
    paragraph: list[str] = []

    def flush() -> Iterator[str]:
        if bullet:
            yield " ".join(bullet)
            bullet.clear()
        if paragraph:
            yield from (s for s in _SENTENCE_END.split(" ".join(paragraph)) if s.strip())
            paragraph.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            yield from flush()
        elif marker := _BULLET.match(line):
            yield from flush()
            bullet.append(line[marker.end() :])
        elif bullet and (line[0].islower() or _CONTINUES.search(bullet[-1])):
            bullet.append(line)  # a bullet wrapped onto the next line
        else:
            if bullet:
                yield from flush()
            paragraph.append(line)
    yield from flush()


def _clauses(unit: str) -> list[str]:
    return [c for c in _CLAUSE_END.split(unit) if c.strip()]


def _is_skill_list(clause: str) -> bool:
    """'Tech stack: Java, Kotlin', 'Python, SQL, Spark' -> read like a resume skills list."""
    label = _LIST_LABEL.match(clause)
    body = clause[label.end() :] if label else clause
    items = [i for i in re.split(r"[,;|]", body.rstrip(".")) if i.strip()]
    enough = 2 if label else 3
    return len(items) >= enough and all(len(i.split()) <= MAX_LIST_ITEM_WORDS for i in items)


# --- The parser -------------------------------------------------------------------------


@dataclass
class _Vote:
    decision: _Decision
    source_text: str


@dataclass
class _Collected:
    votes: dict[str, list[_Vote]]
    skill_years: dict[str, float]
    general_years: list[YearsPhrase]
    required_levels: list[DegreeLevel]
    preferred_levels: list[DegreeLevel]
    fields: list[str]
    unmapped: list[str]
    requirements: list[JobRequirement]


class JobParser:
    def __init__(self, extractor: SkillExtractor) -> None:
        self._extractor = extractor

    def parse(self, text: str) -> JobParse:
        segmentation = segment(text, JD_HEADER_DICTIONARY)
        labels = _labels(text)
        title = labels.get("title") or _first_short_line(segmentation.text_of(CONTACT))

        parts: list[tuple[str | None, str]]
        if any(name in SCANNED_SECTIONS for name in segmentation.names()):
            parts = [(s.name, s.text) for s in segmentation.sections if s.name in SCANNED_SECTIONS]
        else:  # no headers we know: read everything but the title lines
            body = [
                line
                for line in text.split("\n")
                if not _LABEL_LINE.match(line) and line.strip() != title
            ]
            parts = [(None, "\n".join(body))]

        found = _Collected({}, {}, [], [], [], [], [], [])
        for section, body_text in parts:
            for unit in _units(body_text):
                self._read_unit(section, unit, found)

        skills = []
        for name, votes in found.votes.items():
            best = max(votes, key=lambda v: (v.decision.signal, v.decision.kind == REQUIRED))
            skills.append(
                JobSkill(name, best.decision.kind, found.skill_years.get(name), best.source_text)
            )

        min_years, max_years = None, None
        if found.general_years:
            top = max(found.general_years, key=lambda p: p.min_years or 0.0)
            min_years, max_years = top.min_years, top.max_years
        else:  # only "5+ years of Java": the job still needs that much experience
            required_years = [
                found.skill_years[s.name]
                for s in skills
                if s.requirement_type == REQUIRED and s.name in found.skill_years
            ]
            min_years = max(required_years, default=None)

        scanned = "\n".join(body_text for _, body_text in parts)
        return JobParse(
            title=title,
            company=labels.get("company"),
            location=labels.get("location"),
            seniority=seniority_of(title),
            skills=tuple(skills),
            unmapped=tuple(dict.fromkeys(found.unmapped)),
            min_experience_years=min_years,
            max_experience_years=max_years,
            degree_level=min(found.required_levels, default=None),
            preferred_degree_level=min(found.preferred_levels, default=None),
            fields_of_study=tuple(dict.fromkeys(found.fields)),
            accepts_equivalent_experience=bool(_EQUIVALENT_EXPERIENCE.search(scanned)),
            requirements=tuple(found.requirements),
            segmentation=segmentation,
        )

    def _read_unit(self, section: str | None, unit: str, found: _Collected) -> None:
        kinds: list[RequirementType] = []
        has_degree = has_years = has_skill = False
        for clause in _clauses(unit):
            degrees = find_education(clause)
            mentions: list[SkillMention] = []
            if degrees:
                pass  # field names ("Statistics") are not skill claims
            elif _is_skill_list(clause):
                mentions, missed = self._extractor.scan_skill_list(clause, SkillSource.OTHER)
                found.unmapped += missed
            else:
                mentions = self._extractor.find_mentions(clause, SkillSource.OTHER)

            cues = _cues(clause, mentions)
            clause_decision = _decide(section, cues, None)
            kinds.append(clause_decision.kind)
            for mention in mentions:
                decision = _decide(section, cues, mention.span)
                found.votes.setdefault(mention.skill, []).append(_Vote(decision, unit))

            for phrase in find_years(clause):
                has_years = True
                bound = _skills_for_years(clause, phrase, mentions)
                for skill in bound:
                    years = phrase.min_years or 0.0
                    found.skill_years[skill] = max(found.skill_years.get(skill, 0.0), years)
                if not bound and clause_decision.kind == REQUIRED:
                    found.general_years.append(phrase)

            if degrees:
                has_degree = True
                level = min(d.level for d in degrees)
                if clause_decision.kind == REQUIRED:
                    found.required_levels.append(level)
                else:
                    found.preferred_levels.append(level)
                found.fields += find_fields(clause, degrees)
            has_skill = has_skill or bool(mentions)

        if section == RESPONSIBILITIES:
            category = RequirementCategory.RESPONSIBILITY
        elif has_degree:
            category = RequirementCategory.EDUCATION
        elif has_years:
            category = RequirementCategory.EXPERIENCE
        elif has_skill:
            category = RequirementCategory.SKILL
        else:
            category = RequirementCategory.OTHER
        kind = REQUIRED if REQUIRED in kinds or not kinds else PREFERRED
        found.requirements.append(JobRequirement(unit, category, kind))


def parse_job(text: str, extractor: SkillExtractor | None = None) -> JobParse:
    """Requirements, years, degree and skills from a JD's text."""
    return JobParser(extractor or get_skill_extractor()).parse(text)
