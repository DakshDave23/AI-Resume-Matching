"""The sample resumes and JDs, with their ground truth (sample_data/, step 7).

Shared by the *_samples tests, which check each parser against the ground truth.
Each sample file is extracted and segmented once per test run, not once per test.

    @pytest.mark.parametrize("resume", TEXT_RESUMES, ids=resume_id)
    def test_something(resume: Sample) -> None:
        sections = resume_sections(resume)
"""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, cast

import yaml

from app.services.extraction import DocumentKind, extract_text
from app.services.parsing.sections import Segmentation, segment

Sample = dict[str, Any]  # one entry of ground_truth.json's "resumes" or "jds"

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"
GROUND_TRUTH: dict[str, Any] = json.loads(
    (SAMPLES / "ground_truth.json").read_text(encoding="utf-8")
)
AS_OF = date.fromisoformat(GROUND_TRUTH["as_of"])  # what "Present" means in the samples
TEXT_RESUMES: list[Sample] = [
    r for r in GROUND_TRUTH["resumes"] if r["expected_parse_status"] == "parsed"
]  # the scanned-image persona (15) is left out: it has no text to parse
JDS: list[Sample] = GROUND_TRUTH["jds"]


def resume_id(resume: Sample) -> str:
    return str(resume["file"])


def jd_id(jd: Sample) -> str:
    return str(jd["id"])


def text_resume(persona_id: int) -> Sample:
    return next(r for r in TEXT_RESUMES if r["id"] == persona_id)


def jd(jd_key: str) -> Sample:
    return next(j for j in JDS if j["id"] == jd_key)


@cache
def _extracted(file: str, kind: str) -> str:
    return extract_text((SAMPLES / file).read_bytes(), cast(DocumentKind, kind)).text


def resume_text(resume: Sample) -> str:
    return _extracted(resume["file"], resume["format"])


@cache
def _segmented(file: str, kind: str) -> Segmentation:
    return segment(_extracted(file, kind))


def resume_sections(resume: Sample) -> Segmentation:
    return _segmented(resume["file"], resume["format"])


def jd_text(jd: Sample) -> str:
    file: str = jd["file"]
    return (SAMPLES / file).read_text(encoding="utf-8")


@cache
def persona(persona_id: int) -> dict[str, Any]:
    """The hand-written YAML a sample was rendered from."""
    (path,) = (SAMPLES / "personas").glob(f"{persona_id:02d}_*.yaml")
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data
