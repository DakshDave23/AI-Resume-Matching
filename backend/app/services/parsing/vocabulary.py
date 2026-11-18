"""Word lists shared by the resume parsers."""

import re

# A word from this list marks a phrase as a job title ("Senior Software Engineer"),
# which tells a title from a company name and a headline from a person's name.
JOB_TITLE_WORDS = frozenset(
    {
        "developer", "engineer", "manager", "analyst", "scientist", "consultant",
        "accountant", "designer", "architect", "intern", "trainee", "lead", "specialist",
        "officer", "administrator", "tester", "programmer", "director", "executive",
        "associate", "assistant", "coordinator", "representative", "technician", "student",
        "graduate", "fresher", "expert", "head", "president", "founder", "freelancer",
        "owner", "apprentice", "internship", "cto", "ceo", "vp", "sde", "dba", "qa",
    }
)  # fmt: skip

_WORD = re.compile(r"[A-Za-z]+")


def has_title_word(text: str) -> bool:
    return any(w.lower() in JOB_TITLE_WORDS for w in _WORD.findall(text))
