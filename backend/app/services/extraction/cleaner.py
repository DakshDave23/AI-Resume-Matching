"""Normalise extracted text (design doc §5.1, step 5).

Line breaks are kept: section detection works line by line.
"""

import re
import unicodedata

# Characters resumes use as bullets. "-", "–" and "*" only count at the start of a
# line followed by a space, so "3-5 years" and "Jan 2020 – Present" are untouched.
_BULLET_LINE = re.compile(r"^[ \t]*[•●○◦▪▫■□►▸▶➢➤✓✔∙·*–—-][ \t]+", re.MULTILINE)
# A line ending in "letter-" followed by a lowercase letter is one word wrapped at its
# hyphen ("top-\nups"). Resumes rarely use typographic hyphenation, so the hyphen is kept.
_HYPHENATED_LINE_END = re.compile(r"([A-Za-z])-\n([a-z])")
_INVISIBLE = re.compile(r"[­​‌‍⁠﻿]")  # soft hyphen, zero-width
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INVISIBLE.sub("", text)
    # NFKC folds ligatures ("ﬁ" -> "fi"), full-width letters and non-breaking spaces.
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL.sub("", text)
    text = _BULLET_LINE.sub("- ", text)
    text = _HYPHENATED_LINE_END.sub(r"\1-\2", text)  # "top-\nups" -> "top-ups"
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
