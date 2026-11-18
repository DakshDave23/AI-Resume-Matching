"""Step 25's "done when": persona 11 (diploma only) scores 0.5 on education.

Every sample against the Java JD (a Bachelor's in Computer Science or IT), with the
real model for the field-name cosine.
"""

import pytest

from app.services.matching.education import FieldResult, education_score
from app.services.matching.inputs import degrees_from_parse
from app.services.nlp.embedder import Embedder
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import parse_resume
from tests.samples import AS_OF, TEXT_RESUMES, jd, jd_text, resume_text

pytestmark = pytest.mark.model

JAVA = parse_job(jd_text(jd("backend_java")))
# Everyone else holds a computing degree at bachelor's level or above: 1.0.
EXPECTED = {
    8: (0.8, FieldResult.DIFFERENT),  # B.E. Electronics and Communication
    11: (0.5, FieldResult.MATCH),  # Diploma in Computer Engineering: one level below
    12: (0.8, FieldResult.DIFFERENT),  # M.Sc Statistics: level met, another field
    13: (0.8, FieldResult.DIFFERENT),  # B.Com Accounting
}


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=lambda r: r["file"])
def test_education_against_the_java_jd(resume: dict[str, object], real_embedder: Embedder) -> None:
    parsed = parse_resume(resume_text(resume), today=AS_OF, region="IN")
    result = education_score(
        degrees_from_parse(parsed),
        required_level=JAVA.degree_level,
        required_fields=JAVA.fields_of_study,
        accepts_equivalent_experience=JAVA.accepts_equivalent_experience,
        encoder=real_embedder,
    )
    persona = resume["id"]
    assert isinstance(persona, int)
    expected = EXPECTED.get(persona, (1.0, FieldResult.MATCH))
    assert result.score == pytest.approx(expected[0])
    assert result.field_result == expected[1]
    assert result.weight_factor == 1.0  # the Java JD doesn't accept equivalent experience
