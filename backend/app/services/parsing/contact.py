"""Contact details from a resume (design doc §5.5, step 2).

Email, phone and profile links are found by pattern: in the contact block first
(the text above the first section header), then anywhere, since some templates
put them in a footer. Phone numbers go through `phonenumbers`, so only valid
numbers are kept, normalised to E.164.

Name and location are found from the shape of the contact lines rather than
spaCy NER: on short, list-like contact blocks the small English model missed 2
of 14 sample names and 3 of 14 locations, and merged entities across lines
("Rahul Verma\\nJava"). The rules below get all 14 right and are predictable.

- Name: the first piece of a contact line (lines are split on "|", "—", "•" ...)
  made of 2-4 capitalised words, with no digits, "@" or job-title words.
  "Name: ..." labels win.
- Location: a piece of a contact line shaped like a place ("Pune, India",
  "Austin, TX 78701"), or a "Location: ..." label.
"""

import re
from dataclasses import dataclass

import phonenumbers

CONTACT_LINES_SCANNED = 8  # the name sits at the top; don't wander into a headline paragraph

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
LINKEDIN = re.compile(
    r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9_%-]+)", re.IGNORECASE
)
GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![\w-])",
    re.IGNORECASE,
)
URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)+/\S*", re.IGNORECASE)
# "Name: Asha Rao", "Location - Pune, India"
NAME_LABEL = re.compile(r"^\s*(?:full\s+)?name\s*[:\-–]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
LOCATION_LABEL = re.compile(
    r"^\s*(?:location|address|city|based in)\s*[:\-–]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
)
# Pieces of a contact line: "a | b", "a — b", "a • b", "a · b", tabs.
LINE_SEPARATORS = re.compile(r"\s*[|•·\t]\s*|\s+[—–-]\s+")
POSTAL_CODE = re.compile(r"\s+\d{5,6}(?:-\d{4})?$")

# Words that make a capitalised phrase a headline or title, not a person's name.
NOT_NAME_WORDS = frozenset(
    {
        # job titles
        "developer", "engineer", "manager", "analyst", "scientist", "consultant",
        "accountant", "designer", "architect", "intern", "trainee", "lead", "specialist",
        "officer", "administrator", "tester", "programmer", "director", "executive",
        "associate", "assistant", "coordinator", "representative", "technician", "student",
        "graduate", "fresher", "professional", "expert", "head", "president", "founder",
        "freelancer", "owner",
        # headline words
        "software", "data", "web", "cloud", "backend", "frontend", "fullstack", "stack",
        "devops", "technical", "senior", "junior",
        # document labels
        "resume", "curriculum", "vitae", "cv", "profile", "contact", "summary", "objective",
    }
)  # fmt: skip
NAME_PARTICLES = frozenset({"van", "von", "de", "da", "del", "der", "di", "la", "le", "bin", "al"})
APOSTROPHES = ("'", chr(0x2019))  # straight and curly (U+2019), as in O'Neil


@dataclass(frozen=True)
class ContactInfo:
    name: str | None
    email: str | None
    phone: str | None  # E.164, e.g. +919876543210
    location: str | None
    linkedin_url: str | None
    github_url: str | None


def _first(pattern: re.Pattern[str], *texts: str) -> re.Match[str] | None:
    for text in texts:
        if found := pattern.search(text):
            return found
    return None


def find_email(*texts: str) -> str | None:
    found = _first(EMAIL, *texts)
    return found.group(0).rstrip(".") if found else None


def find_phone(*texts: str, region: str) -> str | None:
    """The first valid phone number, in E.164. Numbers without a country code use `region`."""
    for text in texts:
        for match in phonenumbers.PhoneNumberMatcher(text, region):
            return phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
    return None


def find_linkedin(*texts: str) -> str | None:
    found = _first(LINKEDIN, *texts)
    return f"https://linkedin.com/in/{found.group(1)}" if found else None


def find_github(*texts: str) -> str | None:
    found = _first(GITHUB, *texts)
    return f"https://github.com/{found.group(1)}" if found else None


def _pieces(line: str) -> list[str]:
    return [p.strip() for p in LINE_SEPARATORS.split(line) if p.strip()]


def _is_name_word(word: str) -> bool:
    if len(word) == 2 and word[0].isupper() and word[1] == ".":  # an initial: "K."
        return True
    core = word.replace("-", "")
    for apostrophe in APOSTROPHES:
        core = core.replace(apostrophe, "")
    if not core.isalpha() or not word[0].isupper():
        return False
    # "Rao", "RAO", or a compound such as "Anne-Marie" / "O'Neil" (capitals inside are fine)
    return core[1:].islower() or core.isupper() or core != word


def looks_like_name(text: str) -> bool:
    words = text.split()
    if not 2 <= len(words) <= 4:
        return False
    if any(w.lower().strip(".") in NOT_NAME_WORDS for w in words):
        return False
    inner = words[1:-1]
    return (
        _is_name_word(words[0])
        and _is_name_word(words[-1])
        and all(_is_name_word(w) or w in NAME_PARTICLES for w in inner)
    )


def _tidy_name(text: str) -> str:
    """ALL-CAPS names are shown in title case; everything else as written."""
    words = text.split()
    if all(w.isupper() for w in words if len(w) > 2):
        words = [w if len(w) == 2 and w.endswith(".") else w.capitalize() for w in words]
    return " ".join(words)


def find_name(contact_block: str, full_text: str) -> str | None:
    if (label := NAME_LABEL.search(full_text)) and looks_like_name(label.group(1)):
        return _tidy_name(label.group(1))
    for line in contact_block.splitlines()[:CONTACT_LINES_SCANNED]:
        for piece in _pieces(line):
            if looks_like_name(piece):
                return _tidy_name(piece)
    return None


def _looks_like_place(piece: str, *, on_contact_line: bool) -> bool:
    parts = [p.strip() for p in POSTAL_CODE.sub("", piece).split(",")]
    if not 1 <= len(parts) <= 3 or (len(parts) == 1 and not on_contact_line):
        return False
    for part in parts:
        words = part.split()
        if not 1 <= len(words) <= 3 or not all(w[0].isupper() and w.isalpha() for w in words):
            return False
        if any(w.lower() in NOT_NAME_WORDS for w in words):
            return False
    return True


def find_location(contact_block: str, name: str | None) -> str | None:
    if label := LOCATION_LABEL.search(contact_block):
        return POSTAL_CODE.sub("", label.group(1)).strip()
    for line in contact_block.splitlines()[:CONTACT_LINES_SCANNED]:
        # On a line that also holds an email or phone, a lone "Pune" is a location too.
        on_contact_line = bool(EMAIL.search(line) or re.search(r"\d{3}", line))
        for piece in _pieces(line):
            if piece == name or EMAIL.search(piece) or URL.search(piece):
                continue
            if _looks_like_place(piece, on_contact_line=on_contact_line):
                return POSTAL_CODE.sub("", piece)
    return None


def extract_contact(contact_block: str, full_text: str, *, region: str) -> ContactInfo:
    """Contact details from a resume's contact block, falling back to its full text.

    `region` (ISO 3166 alpha-2, e.g. "IN") is used for phone numbers written
    without a country code.
    """
    name = find_name(contact_block, full_text)
    return ContactInfo(
        name=name,
        email=find_email(contact_block, full_text),
        phone=find_phone(contact_block, full_text, region=region),
        location=find_location(contact_block, name),
        linkedin_url=find_linkedin(contact_block, full_text),
        github_url=find_github(contact_block, full_text),
    )
