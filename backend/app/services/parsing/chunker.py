"""Split a resume into passages for embedding (design doc §5.5, step 8).

Experience, projects and the summary are cut into chunks of up to about 120
words, along role and bullet boundaries:

- each role is one chunk, headed by its title and company, when it fits; a long
  role becomes several chunks, each repeating the header so it still says whose
  work it describes;
- a bullet is never split unless it alone is too long; then it splits by sentence;
- projects are grouped the same way (a project name line, then its bullets);
- the summary is one paragraph, split by sentence if it is long.

all-MiniLM-L6-v2 reads at most 256 word pieces (roughly 200 words), so a
120-word chunk is never cut off. The skills section is not chunked: a bare list
of names would let a keyword list pass for described experience.

Measured on sample 3, a whole-role chunk matches JD requirements as well as its
best single bullet (0.46 vs 0.43 for "Microservices"), so roles stay whole.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from app.services.parsing.experience import Role, WorkHistory
from app.services.parsing.sections import Segmentation

MAX_CHUNK_WORDS = 120
MAX_HEADER_WORDS = 12  # a longer line with nothing under it is prose, not a project name
CHUNKED_SECTIONS = ("summary", "experience", "projects")  # in this order

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
# A line that stops mid-phrase continues on the next one (PDF lines keep their wraps).
_MID_PHRASE = re.compile(r"(?:[,;:&/(-]|\b(?:and|or|of|in|with|the|a|an|to|for|on|by))$")


@dataclass(frozen=True)
class Chunk:
    section: str  # "summary", "experience" or "projects"
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class _Entry:
    """A header line (a project name) and the bullets under it."""

    header: str | None
    items: list[str]

    def lines(self) -> list[str]:
        return ([self.header] if self.header else []) + self.items


def _continues(previous: str, line: str) -> bool:
    return line[0].islower() or line[0].isdigit() or bool(_MID_PHRASE.search(previous))


def _entries(text: str) -> list[_Entry]:
    """Bullets grouped under the header line above them; wrapped lines rejoined."""
    entries: list[_Entry] = []
    previous = ""  # the line above, or "" after a blank line
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            previous = ""
            continue
        if line.startswith("- "):
            if not entries:
                entries.append(_Entry(None, []))
            entries[-1].items.append(line[2:].strip())
        elif entries and previous and _continues(previous, line):
            last = entries[-1]
            if last.items:
                last.items[-1] += " " + line
            else:
                last.header = f"{last.header} {line}" if last.header else line
        else:
            entries.append(_Entry(line, []))
        previous = line
    for entry in entries:
        if entry.header and not entry.items and len(entry.header.split()) > MAX_HEADER_WORDS:
            entry.items, entry.header = [entry.header], None
    return entries


def _pieces(item: str, budget: int) -> Iterator[str]:
    """The item if it fits; else its sentences, and a sentence too long is cut by words."""
    if len(item.split()) <= budget:
        yield item
        return
    for sentence in _SENTENCE_END.split(item):
        words = sentence.split()
        for start in range(0, len(words), budget):
            yield " ".join(words[start : start + budget])


def _pack(section: str, header: str | None, items: list[str]) -> list[Chunk]:
    """Fill chunks with whole items, in order, up to MAX_CHUNK_WORDS each (header included)."""
    budget = MAX_CHUNK_WORDS - (len(header.split()) if header else 0)
    budget = max(budget, MAX_CHUNK_WORDS // 2)  # a silly-long header can't starve the body
    groups: list[list[str]] = []
    used = 0
    for item in items:
        for piece in _pieces(item, budget):
            size = len(piece.split())
            if not groups or used + size > budget:
                groups.append([])
                used = 0
            groups[-1].append(piece)
            used += size

    chunks = []
    for group in groups:
        body = " ".join(group) if section == "summary" else "\n".join(f"- {p}" for p in group)
        chunks.append(Chunk(section, f"{header}\n{body}" if header else body))
    if not chunks and header:  # a role with a title but no bullets still says something
        chunks.append(Chunk(section, header))
    return chunks


def _role_header(role: Role) -> str | None:
    return " | ".join(part for part in (role.title, role.company) if part) or None


def chunk_section(section: str, text: str) -> list[Chunk]:
    """Chunks of one section's text, without the parsed roles (projects, or a fallback)."""
    if section == "summary":
        return _pack(section, None, [" ".join(text.split())]) if text.strip() else []
    return [c for entry in _entries(text) for c in _pack(section, entry.header, entry.items)]


def chunk_resume(sections: Segmentation, work: WorkHistory) -> list[Chunk]:
    """Summary, then experience, then projects. The list index is the chunk_index."""
    chunks: list[Chunk] = []
    for section in CHUNKED_SECTIONS:
        if section == "experience" and work.roles:
            for role in work.roles:
                # Inside a role every line is content: a stray non-bullet line is not a header.
                items = [line for entry in _entries(role.description) for line in entry.lines()]
                chunks += _pack(section, _role_header(role), items)
        else:
            chunks += chunk_section(section, sections.text_of(section))
    return chunks
