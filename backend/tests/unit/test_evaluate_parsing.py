"""scripts/evaluate_parsing.py must report misses, not just print 100%.

The samples parse perfectly, so the report is checked against a ground truth
with deliberate mistakes in it: each one must show up as a miss.
"""

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.samples import GROUND_TRUTH, SAMPLES


def load_script() -> ModuleType:
    path = SAMPLES.parent / "scripts" / "evaluate_parsing.py"
    spec = importlib.util.spec_from_file_location("evaluate_parsing", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return load_script()


def small_truth() -> dict[str, Any]:
    """Two resumes (one text, one scanned) and the Java JD, to keep the test fast."""
    truth = copy.deepcopy(GROUND_TRUTH)
    truth["resumes"] = [r for r in truth["resumes"] if r["id"] in (1, 15)]
    truth["jds"] = [j for j in truth["jds"] if j["id"] == "backend_java"]
    return truth


def report_for(script: ModuleType, truth: dict[str, Any]) -> str:
    report = script.Report()
    script.evaluate_resumes(truth, report)
    script.evaluate_jds(truth, report)
    markdown: str = script.render(report, truth)
    return markdown


def test_correct_ground_truth_has_no_misses(script: ModuleType) -> None:
    markdown = report_for(script, small_truth())
    assert "## Misses\n\nNone." in markdown
    assert "**no**" not in markdown
    assert "| Unreadable files rejected | 100.0% (1/1) |" in markdown


def test_every_kind_of_mistake_is_reported(script: ModuleType) -> None:
    truth = small_truth()
    resume = truth["resumes"][0]
    resume["name"] = "Someone Else"
    resume["skills"] = [s for s in resume["skills"] if s != "Docker"] + ["Zz Imaginary"]
    resume["total_experience_months"] += 12
    resume["degree_level"] = 5
    resume["sections"].append("projects")
    truth["jds"][0]["min_experience_years"] = 7.0

    markdown = report_for(script, truth)

    assert "| Name | Exact match after normalising case and spaces | 0.0% (0/1) |" in markdown
    assert "01_senior_java_engineer.pdf: expected 'Someone Else', got 'Arjun Mehta'" in markdown
    assert "missed Zz Imaginary" in markdown
    assert "not in the resume: Docker" in markdown
    assert "| Total experience | Mean absolute error | 12.0 months (0/1 exact) |" in markdown
    assert "expected 5, got <DegreeLevel.BACHELOR: 3>" in markdown
    assert "01_senior_java_engineer.pdf: expected 'projects', got 'not found'" in markdown
    assert "backend_java: expected (7.0, None), got (4.0, None)" in markdown
    assert markdown.count("**no**") == 4  # name, total experience, degree level, sections


def test_the_script_runs_from_the_command_line(script: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    assert script.main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Parsing accuracy")
