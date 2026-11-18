from datetime import date

from app.services.parsing.resume_parser import parse_resume
from tests.samples import AS_OF, TEXT_RESUMES, resume_text

TODAY = date(2026, 11, 1)

FULL = """\
Asha Rao
asha.rao@example.com | +91 98450 12345 | Pune, India

Experience
Backend Engineer | Acme, Pune
Jan 2020 – Present
- Built Spring Boot services in Java on PostgreSQL.

Education
B.E. in Computer Engineering, Pune College of Engineering, 2019
"""


def test_a_complete_resume_passes_every_check() -> None:
    parsed = parse_resume(FULL, today=TODAY, region="IN")
    assert parsed.checks == dict.fromkeys(
        ("name", "email", "phone", "skills", "dated_role", "education"), True
    )
    assert (parsed.confidence, parsed.needs_review) == (1.0, False)
    assert parsed.contact.phone == "+919845012345"
    assert parsed.work.total_months == 83
    assert parsed.skill_months["Java"] == 83


def test_a_resume_missing_most_things_needs_review() -> None:
    parsed = parse_resume("Asha Rao\nI like computers.", today=TODAY, region="IN")
    assert [check for check, ok in parsed.checks.items() if ok] == ["name"]
    assert parsed.confidence == 1 / 6
    assert parsed.needs_review


def test_half_the_checks_is_not_flagged() -> None:
    text = "Asha Rao\nasha@example.com | +91 98450 12345\nSkills\nJava"  # name, email, phone
    parsed = parse_resume(text, today=TODAY, region="IN")
    assert (parsed.confidence, parsed.needs_review) == (0.5, False)


def test_no_text_sample_needs_review() -> None:
    for resume in TEXT_RESUMES:
        assert not parse_resume(resume_text(resume), today=AS_OF, region="IN").needs_review
