"""Find taxonomy skills in resume and JD text (design doc §5.3).

1. Exact and alias pass: a spaCy PhraseMatcher over tokens holds every skill
   name and alias, plus a simple plural ("audits", "unit tests"). Overlapping
   hits keep the longest, so "Spring Boot" never also counts as "Spring" and
   "T-SQL" never also as "SQL".
2. Ambiguous terms, which are also everyday words ("go", "rest", "spring", "express"),
   only match in free text when spelled like the skill ("Go", "Ruby", "Express"
   for Express.js) or in capitals ("REST"). Inside a skill list any spelling counts.
3. Fuzzy pass: a skill-list item that no single exact hit covers is compared
   whole with rapidfuzz `token_sort_ratio` >= 90 against every term. "Node JS"
   is Node.js, not "node" + "JS"; "Postgre SQL" is PostgreSQL, not SQL.
4. Items that still match nothing are kept as `unmapped` for the recruiter.

Every hit records its section and the line it came from; both feed the
explanation later.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz, process, utils
from spacy.language import Language
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc, Span
from spacy.util import filter_spans

from app.models.enums import SkillCategory, SkillSource
from app.services.nlp.spacy_pipeline import get_nlp
from app.services.nlp.taxonomy import Taxonomy, get_taxonomy, normalize_term
from app.services.parsing.contact import EMAIL, URL
from app.services.parsing.sections import Segmentation

# Taxonomy terms that are also everyday English words.
AMBIGUOUS_TERMS = frozenset(
    {
        "c", "r", "go", "rest", "spring", "express", "node", "vault", "ruby", "swift", "chef",
        "safe", "spa", "spas", "soap", "helm", "hive", "gin", "dart", "rust", "jest", "yarn",
        "ann", "sap", "elk", "kube",
    }
)  # fmt: skip

FUZZY_MIN_SCORE = 90
FUZZY_MIN_CHARS = 4  # "c#" and "f#" both become "c"/"f" once punctuation goes: too short
MAX_ITEM_WORDS = 5  # a longer "item" is a sentence, not a skill name
MAX_EVIDENCE_CHARS = 300

SOURCE_BY_SECTION = {
    "skills": SkillSource.SKILLS_SECTION,
    "experience": SkillSource.EXPERIENCE,
    "projects": SkillSource.PROJECTS,
    "summary": SkillSource.SUMMARY,
}
# Degree names aren't skill claims: "Electronics and Communication" is not the soft skill.
SECTIONS_NOT_SCANNED = frozenset({"education"})
# Which mention makes the best evidence: a bullet shows the skill being used.
EVIDENCE_PREFERENCE = (
    SkillSource.EXPERIENCE,
    SkillSource.PROJECTS,
    SkillSource.SUMMARY,
    SkillSource.OTHER,
    SkillSource.SKILLS_SECTION,
)

# "Frontend: React, Redux" -> the label is a group name, not a skill claim.
_LIST_LABEL = re.compile(r"^(\s*(?:- )?)([^:,\n]{1,40}):", re.MULTILINE)
_ITEM_SEPARATORS = re.compile(r"[,;|•]|\s+/\s+")
_WRAPPED_LIST = re.compile(r",[ \t]*\n[ \t]*")


@dataclass(frozen=True)
class SkillMention:
    skill: str  # canonical name
    source: SkillSource
    text: str  # as written in the resume
    evidence: str  # the line (or wrapped bullet) it appeared in
    fuzzy: bool = False
    # Character offsets in the text given to find_mentions (None for skill-list items).
    span: tuple[int, int] | None = field(default=None, compare=False)


@dataclass(frozen=True)
class FoundSkill:
    name: str
    category: SkillCategory
    sources: tuple[SkillSource, ...]
    mention_count: int
    evidence: str


@dataclass(frozen=True)
class SkillExtraction:
    skills: tuple[FoundSkill, ...]  # sorted by name
    unmapped: tuple[str, ...]  # skill-list items not in the taxonomy, as written
    mentions: tuple[SkillMention, ...]

    def names(self) -> set[str]:
        return {s.name for s in self.skills}


def _mask(text: str, pattern: re.Pattern[str], group: int = 0) -> str:
    """Blank out matches, keeping every other character at its offset."""
    return pattern.sub(
        lambda m: m.group(0).replace(m.group(group), " " * len(m.group(group))), text
    )


def _evidence(text: str, start: int, end: int) -> str:
    """The line holding text[start:end], with wrapped lower-case continuations joined."""
    lines_before = text[:start].split("\n")
    lines_after = text[end:].split("\n")
    line = lines_before[-1] + text[start:end] + lines_after[0]
    # PDF lines wrap mid-sentence; the continuation starts in lower case.
    for previous in reversed(lines_before[:-1]):
        if not line[:1].islower() or not previous.strip():
            break
        line = f"{previous} {line}"
    for following in lines_after[1:]:
        if not following[:1].islower():
            break
        line = f"{line} {following}"
    line = line.strip().removeprefix("- ")
    return line if len(line) <= MAX_EVIDENCE_CHARS else line[: MAX_EVIDENCE_CHARS - 1] + "…"


def _plural(term: str) -> str | None:
    """'audit' -> 'audits', 'unit test' -> 'unit tests'. None when there is no simple plural."""
    last = term.rsplit(" ", 1)[-1]
    if len(last) < 4 or not last.isalpha() or last.endswith(("s", "x", "y")):
        return None
    return term + "s"


def _covers(spans: list[Span], doc: Doc) -> bool:
    """One hit spans every word of the item ("Java 11": the version number doesn't count)."""
    if len(spans) != 1:
        return False
    span = spans[0]
    return all(span.start <= t.i < span.end for t in doc if any(c.isalpha() for c in t.text))


def _is_plausible(span: Span) -> bool:
    """Reject a one-letter skill that is part of something else: "C-level", "Grade-C"."""
    if len(span.text) > 1:
        return True
    doc = span.doc
    neighbours = [doc[i].text for i in (span.start - 1, span.end) if 0 <= i < len(doc)]
    return not any(n in {"-", "&", "'", "."} for n in neighbours)


class SkillExtractor:
    def __init__(self, taxonomy: Taxonomy, nlp: Language) -> None:
        self._nlp = nlp
        self._skills = {s.name: s for s in taxonomy.skills}
        self._anywhere = PhraseMatcher(nlp.vocab, attr="LOWER")
        self._as_written = PhraseMatcher(nlp.vocab, attr="ORTH")
        self._in_lists = PhraseMatcher(nlp.vocab, attr="LOWER")

        index = taxonomy.term_index()
        fuzzy: dict[str, str] = {}
        for term, skill in index.items():
            if term in AMBIGUOUS_TERMS:
                spellings = {term.upper()}
                name = normalize_term(skill.name)
                if term == name:
                    spellings.add(skill.name)  # "Go", "Ruby", "C"
                elif name.startswith(term) and not name[len(term)].isalpha():
                    spellings.add(term.capitalize())  # "Express" for Express.js
                self._as_written.add(skill.name, [nlp.make_doc(s) for s in sorted(spellings)])
                self._in_lists.add(skill.name, [nlp.make_doc(term)])
            else:
                forms = [term]
                if (plural := _plural(term)) and plural not in index:
                    forms.append(plural)  # "tax audits" -> Auditing
                self._anywhere.add(skill.name, [nlp.make_doc(f) for f in forms])
            key = utils.default_process(term)
            if len(key) >= FUZZY_MIN_CHARS:
                fuzzy.setdefault(key, skill.name)
        self._fuzzy_terms = fuzzy
        self._compact_terms = {k.replace(" ", ""): v for k, v in fuzzy.items()}

    # --- matching ------------------------------------------------------------

    def _spans(self, doc: Doc, *, skill_list: bool) -> list[Span]:
        matches = self._anywhere(doc) + self._as_written(doc)
        if skill_list:
            matches += self._in_lists(doc)
        spans = [Span(doc, start, end, label=key) for key, start, end in matches]
        return filter_spans([s for s in spans if _is_plausible(s)])

    def find_mentions(
        self, text: str, source: SkillSource, *, skill_list: bool = False
    ) -> list[SkillMention]:
        """Exact and alias hits in `text`, in order. `skill_list` relaxes the case rules."""
        doc = self._nlp.make_doc(text)
        return [
            SkillMention(
                skill=span.label_,
                source=source,
                text=span.text,
                evidence=_evidence(text, span.start_char, span.end_char),
                span=(span.start_char, span.end_char),
            )
            for span in sorted(self._spans(doc, skill_list=skill_list), key=lambda s: s.start)
        ]

    def fuzzy_match(self, item: str) -> str | None:
        """The skill a near-miss list item means ("Kubernetis" -> Kubernetes), if any.

        token_sort_ratio forgives word order, but sorting breaks a word split by a
        space ("Type Script" -> "script type"), so items are also compared with
        spaces removed.
        """
        key = utils.default_process(item)
        if len(key) < FUZZY_MIN_CHARS:
            return None
        candidates = [
            (self._fuzzy_terms, key, fuzz.token_sort_ratio),
            (self._compact_terms, key.replace(" ", ""), fuzz.ratio),
        ]
        best: tuple[float, str] | None = None
        for terms, query, scorer in candidates:
            found = process.extractOne(
                query, terms.keys(), scorer=scorer, processor=None, score_cutoff=FUZZY_MIN_SCORE
            )
            if found and (best is None or found[1] > best[0]):
                best = (found[1], terms[found[0]])
        return best[1] if best else None

    # --- skill lists ---------------------------------------------------------

    def scan_skill_list(
        self, text: str, source: SkillSource = SkillSource.SKILLS_SECTION
    ) -> tuple[list[SkillMention], list[str]]:
        """Mentions in a skills section, plus the items that are in no taxonomy.

        Each comma-separated item is judged as a whole. "Node JS" holds two valid
        aliases ("node", "JS"), but as an item it means one skill, so an item that a
        single exact hit doesn't fully cover is tried fuzzily first.
        """
        mentions: list[SkillMention] = []
        unmapped: list[str] = []
        for line in _WRAPPED_LIST.sub(", ", text).split("\n"):
            evidence = " ".join(line.split()).removeprefix("- ")  # label kept: "Tools: Docker"
            items = _mask(line, _LIST_LABEL, group=2).strip().removeprefix("- ")
            for raw in _ITEM_SEPARATORS.split(items):
                item = raw.strip().removesuffix(".")  # keep the dot in ".NET"
                if not item:
                    continue
                doc = self._nlp.make_doc(item)
                spans = sorted(self._spans(doc, skill_list=True), key=lambda s: s.start)
                exact = [SkillMention(s.label_, source, s.text, evidence) for s in spans]
                if len(item.split()) > MAX_ITEM_WORDS or _covers(spans, doc):
                    mentions += exact  # a sentence, or one skill that is the whole item
                elif skill := self.fuzzy_match(item):
                    mentions.append(SkillMention(skill, source, item, evidence, fuzzy=True))
                elif exact:
                    mentions += exact  # "Spring Boot (Actuator)": keep what we know
                elif not item.replace(" ", "").isdigit():
                    unmapped.append(item)
        return mentions, unmapped

    # --- a whole resume ------------------------------------------------------

    def extract_resume(self, segmentation: Segmentation) -> SkillExtraction:
        mentions: list[SkillMention] = []
        unmapped: list[str] = []
        for section in segmentation.sections:
            if section.name in SECTIONS_NOT_SCANNED:
                continue
            source = SOURCE_BY_SECTION.get(section.name, SkillSource.OTHER)
            if section.name == "skills":
                found, missed = self.scan_skill_list(section.text, source)
                mentions += found
                unmapped += missed
            else:
                # The contact block holds the headline, but also github.com/... links.
                text = _mask(_mask(section.text, EMAIL), URL)
                mentions += self.find_mentions(text, source)
        return SkillExtraction(
            skills=tuple(self.summarize(mentions)),
            unmapped=tuple(_unique(unmapped)),
            mentions=tuple(mentions),
        )

    def summarize(self, mentions: Iterable[SkillMention]) -> list[FoundSkill]:
        """One entry per skill: where it appeared, how often, and the best evidence."""
        by_skill: dict[str, list[SkillMention]] = {}
        for mention in mentions:
            by_skill.setdefault(mention.skill, []).append(mention)
        found = []
        for name, group in by_skill.items():
            best = min(group, key=lambda m: EVIDENCE_PREFERENCE.index(m.source))
            found.append(
                FoundSkill(
                    name=name,
                    category=self._skills[name].category,
                    sources=tuple(s for s in SkillSource if any(m.source == s for m in group)),
                    mention_count=len(group),
                    evidence=best.evidence,
                )
            )
        return sorted(found, key=lambda s: s.name.lower())


def _unique(items: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for item in items:
        seen.setdefault(item.lower(), item)
    return list(seen.values())


@lru_cache
def get_skill_extractor() -> SkillExtractor:
    return SkillExtractor(get_taxonomy(), get_nlp())
