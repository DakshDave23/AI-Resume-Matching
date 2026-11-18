"""One resume's text in, everything the parsers find out (design doc §5.5).

    text = extract_text(data, kind).text
    parsed = parse_resume(text, today=date.today(), region="IN")

The upload pipeline, the CLI and the accuracy evaluation all call this, so they
measure and store exactly the same thing.
"""

from dataclasses import dataclass
from datetime import date

from app.services.parsing.contact import ContactInfo, extract_contact
from app.services.parsing.education import EducationResult, parse_education
from app.services.parsing.experience import WorkHistory, parse_experience, skill_months
from app.services.parsing.sections import CONTACT, Segmentation, segment
from app.services.parsing.skills import SkillExtraction, SkillExtractor, get_skill_extractor

# Below this share of checks passed, the UI flags the resume for manual review (§5.5 step 9).
MIN_CONFIDENCE = 0.5
MIN_SKILLS = 3


@dataclass(frozen=True)
class ParsedResume:
    sections: Segmentation
    contact: ContactInfo
    work: WorkHistory
    education: EducationResult
    skills: SkillExtraction
    skill_months: dict[str, int]  # months of dated, non-intern roles that mention the skill

    @property
    def checks(self) -> dict[str, bool]:
        return {
            "name": self.contact.name is not None,
            "email": self.contact.email is not None,
            "phone": self.contact.phone is not None,
            "skills": len(self.skills.skills) >= MIN_SKILLS,
            "dated_role": any(role.dates is not None for role in self.work.roles),
            "education": bool(self.education.entries),
        }

    @property
    def confidence(self) -> float:
        """The share of the six checks passed, 0-1."""
        checks = self.checks
        return sum(checks.values()) / len(checks)

    @property
    def needs_review(self) -> bool:
        return self.confidence < MIN_CONFIDENCE


def parse_resume(
    text: str, *, today: date, region: str, extractor: SkillExtractor | None = None
) -> ParsedResume:
    """Sections, contact details, work history, education and skills from clean text."""
    extractor = extractor or get_skill_extractor()
    sections = segment(text)
    work = parse_experience(
        sections.text_of("experience"), today=today, summary=sections.text_of("summary")
    )
    return ParsedResume(
        sections=sections,
        contact=extract_contact(sections.text_of(CONTACT), text, region=region),
        work=work,
        education=parse_education(sections.text_of("education")),
        skills=extractor.extract_resume(sections),
        skill_months=skill_months(work, extractor, today=today),
    )
