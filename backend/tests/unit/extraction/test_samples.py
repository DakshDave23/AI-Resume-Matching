"""Step 8's "done when": text comes out of all 14 text-based samples, and the scanned
one fails with a clear reason. Expectations come from sample_data/ground_truth.json."""

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from app.services.extraction import ExtractionError, extract_text, validate_file

SAMPLES = Path(__file__).resolve().parents[4] / "sample_data"
GROUND_TRUTH: dict[str, Any] = json.loads(
    (SAMPLES / "ground_truth.json").read_text(encoding="utf-8")
)
RESUMES = GROUND_TRUTH["resumes"]
TEXT_RESUMES = [r for r in RESUMES if r["expected_parse_status"] == "parsed"]
MAX_BYTES = 5 * 1024 * 1024


def extract(resume: dict[str, Any]) -> str:
    data = (SAMPLES / resume["file"]).read_bytes()
    kind = validate_file(data, resume["file"], max_bytes=MAX_BYTES).kind
    return extract_text(data, kind).text


def test_there_are_14_text_samples_and_one_scanned() -> None:
    assert len(TEXT_RESUMES) == 14
    assert len(RESUMES) == 15


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=lambda r: r["file"])
def test_text_comes_out_of_every_text_sample(resume: dict[str, Any]) -> None:
    text = extract(resume)

    assert resume["name"] in text
    assert resume["email"] in text
    for role in resume["roles"]:
        assert role["title"] in text
        assert role["company"] in text


def test_the_scanned_sample_fails_with_a_clear_reason() -> None:
    scanned = next(r for r in RESUMES if r["expected_failure"] == "scanned_pdf")

    with pytest.raises(ExtractionError) as exc:
        extract(scanned)
    assert exc.value.code == "scanned_pdf"


def test_two_column_sample_reads_each_column_without_interleaving() -> None:
    resume = next(r for r in RESUMES if r["layout"] == "two_column")
    path = SAMPLES / resume["file"]

    text = extract(resume)
    with pymupdf.open(path) as pdf:
        naive = pdf[0].get_text(sort=True)  # plain top-to-bottom order

    # Plain top-to-bottom reading puts "Summary" (right column) before "Education" (left)...
    assert naive.index("Summary") < naive.index("Education")
    # ...the column-aware reader finishes the sidebar first, then reads the main column.
    assert text.index("Technical Skills") < text.index("Education") < text.index("Summary")
    assert text.index("Summary") < text.index("Work Experience")


def test_table_sample_keeps_every_cell_once() -> None:
    resume = next(r for r in RESUMES if r["layout"] == "tables")

    text = extract(resume)

    assert text.count("Work Experience") == 1  # merged title cell, not duplicated
    assert "Sep 2023 – Present" in text and "Jul 2022 – Aug 2023" in text


def test_docx_header_contact_comes_first() -> None:
    resume = next(r for r in RESUMES if r["id"] == 6)

    first_line = extract(resume).split("\n")[0]

    assert first_line.startswith(resume["name"])


@pytest.mark.parametrize("jd", GROUND_TRUTH["jds"], ids=lambda j: j["id"])
def test_jd_text_files_extract(jd: dict[str, Any]) -> None:
    data = (SAMPLES / jd["file"]).read_bytes()

    text = extract_text(data, "txt").text

    assert jd["title"] in text
