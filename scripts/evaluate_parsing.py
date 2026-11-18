"""Measure parsing accuracy against sample_data/ground_truth.json (design doc §13).

Runs every sample resume through the same extraction and parsing the upload
pipeline uses, and every sample JD through the JD parser, then prints a markdown
report: one row per field with the doc's metric and target, then every miss.

Usage (from the repo root, with the backend virtualenv):
    backend/.venv/Scripts/python scripts/evaluate_parsing.py                 # Windows
    backend/.venv/bin/python scripts/evaluate_parsing.py                     # macOS/Linux
    ... scripts/evaluate_parsing.py --out docs/parsing-accuracy.md           # also save it

The report has no timestamps, so it only changes when the parsers or samples do.
Exit code 0 even when a target is missed: the report says so.
"""

import argparse
import io
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.services.extraction import ExtractionError, extract_text, validate_file
from app.services.nlp.taxonomy import get_taxonomy
from app.services.parsing.jd_parser import parse_job
from app.services.parsing.resume_parser import ParsedResume, parse_resume

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"
MAX_FILE_BYTES = 5 * 1024 * 1024
REGION = "IN"  # the app's default; every sample phone carries its own country code

Sample = dict[str, Any]
Row = tuple[str, str, str, str, bool]  # field, metric, result, target, met


# --- Comparisons ----------------------------------------------------------------------


def same_name(a: str | None, b: str | None) -> bool:
    """Exact match after normalising case and spaces (§13)."""
    return (
        a is not None
        and b is not None
        and " ".join(a.split()).casefold() == " ".join(b.split()).casefold()
    )


def without_scheme(url: str | None) -> str | None:
    return url.removeprefix("https://") if url else None


def month(value: Any) -> str | None:
    return f"{value.year}-{value.month:02d}" if value else None


def role_key(role: dict[str, Any]) -> tuple[Any, ...]:
    return (role["title"], role["company"], role["start"], role["end"])


def education_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (entry["degree"], entry["field"], entry["institution"], entry["year"], entry["level"])


def prf(true_pos: int, false_pos: int, false_neg: int) -> tuple[float, float, float]:
    precision = true_pos / (true_pos + false_pos) if true_pos + false_pos else 1.0
    recall = true_pos / (true_pos + false_neg) if true_pos + false_neg else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


# --- Tallies ----------------------------------------------------------------------------


@dataclass
class Tally:
    """Right out of total, plus a note for each miss."""

    right: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    def check(self, ok: bool, where: str, expected: Any, found: Any) -> None:
        self.total += 1
        if ok:
            self.right += 1
        else:
            self.misses.append(f"{where}: expected {expected!r}, got {found!r}")

    @property
    def share(self) -> float:
        return self.right / self.total if self.total else 1.0

    def cell(self) -> str:
        return f"{self.share:.1%} ({self.right}/{self.total})"


@dataclass
class Report:
    fields: dict[str, Tally] = field(default_factory=dict)
    skill_counts: Counter[str] = field(default_factory=Counter)
    skill_misses: list[str] = field(default_factory=list)
    experience_errors: list[int] = field(default_factory=list)
    experience_misses: list[str] = field(default_factory=list)
    extra_sections: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    jd_fields: dict[str, Tally] = field(default_factory=dict)
    jd_skill_counts: Counter[str] = field(default_factory=Counter)

    def tally(self, name: str) -> Tally:
        return self.fields.setdefault(name, Tally())

    def jd_tally(self, name: str) -> Tally:
        return self.jd_fields.setdefault(name, Tally())


# --- Resumes ----------------------------------------------------------------------------


def read_text(resume: Sample) -> str:
    """Validate and extract like an upload does; raises ExtractionError."""
    data = (SAMPLES / resume["file"]).read_bytes()
    validated = validate_file(data, Path(resume["file"]).name, max_bytes=MAX_FILE_BYTES)
    return extract_text(data, validated.kind).text


def evaluate_resume(resume: Sample, parsed: ParsedResume, report: Report) -> None:
    where = Path(resume["file"]).name
    contact = parsed.contact
    report.tally("Name").check(
        same_name(contact.name, resume["name"]), where, resume["name"], contact.name
    )
    report.tally("Email").check(
        contact.email == resume["email"], where, resume["email"], contact.email
    )
    report.tally("Phone").check(
        contact.phone == resume["phone_e164"], where, resume["phone_e164"], contact.phone
    )
    report.tally("Location").check(
        contact.location == resume["location"], where, resume["location"], contact.location
    )
    for label, found, expected in [
        ("LinkedIn", without_scheme(contact.linkedin_url), resume["linkedin"]),
        ("GitHub", without_scheme(contact.github_url), resume["github"]),
    ]:
        report.tally("LinkedIn and GitHub URLs").check(
            found == expected, f"{where} {label}", expected, found
        )

    # Skills: micro-averaged over every resume.
    found_skills, expected_skills = parsed.skills.names(), set(resume["skills"])
    report.skill_counts["tp"] += len(found_skills & expected_skills)
    report.skill_counts["fp"] += len(found_skills - expected_skills)
    report.skill_counts["fn"] += len(expected_skills - found_skills)
    if missed := sorted(expected_skills - found_skills):
        report.skill_misses.append(f"{where}: missed {', '.join(missed)}")
    if extra := sorted(found_skills - expected_skills):
        report.skill_misses.append(f"{where}: not in the resume: {', '.join(extra)}")
    report.tally("Unmapped skill terms").check(
        list(parsed.skills.unmapped) == resume["unmapped_skill_terms"],
        where,
        resume["unmapped_skill_terms"],
        list(parsed.skills.unmapped),
    )

    # Experience.
    expected_total, found_total = resume["total_experience_months"], parsed.work.total_months
    if expected_total is not None:
        error = abs((found_total or 0) - expected_total)
        report.experience_errors.append(error)
        if error:
            report.experience_misses.append(
                f"{where}: expected {expected_total} months, got {found_total}"
            )
    found_roles = Counter(
        (r.title, r.company, month(r.dates.start) if r.dates else None,
         month(r.dates.end) if r.dates else None)
        for r in parsed.work.roles
    )  # fmt: skip
    for role in resume["roles"]:
        key = role_key(role)
        ok = found_roles[key] > 0
        found_roles[key] -= 1
        report.tally("Roles (title, company, dates)").check(ok, where, key, "not found")
    report.tally("Current title").check(
        parsed.work.current_title == resume["current_title"],
        where,
        resume["current_title"],
        parsed.work.current_title,
    )

    # Education.
    level = parsed.education.highest_level
    report.tally("Degree level").check(
        level == resume["degree_level"], where, resume["degree_level"], level
    )
    found_entries = Counter(
        (e.degree, e.field, e.institution, e.year, e.level) for e in parsed.education.entries
    )
    for entry in resume["education"]:
        key = education_key(entry)
        ok = found_entries[key] > 0
        found_entries[key] -= 1
        report.tally("Education entries").check(ok, where, key, "not found")

    # Sections: the share of expected sections found; extras are listed.
    found_sections = set(parsed.sections.names()) - {"contact"}
    for section in resume["sections"]:
        report.tally("Sections").check(section in found_sections, where, section, "not found")
    if extra_sections := sorted(found_sections - set(resume["sections"]) - {"other"}):
        report.extra_sections.append(f"{where}: {', '.join(extra_sections)}")

    if parsed.needs_review:
        report.needs_review.append(f"{where} ({parsed.confidence:.2f})")


def evaluate_resumes(truth: dict[str, Any], report: Report) -> None:
    as_of = date.fromisoformat(truth["as_of"])
    for resume in truth["resumes"]:
        where = Path(resume["file"]).name
        try:
            text = read_text(resume)
        except ExtractionError as exc:
            report.tally("Unreadable files rejected").check(
                resume["expected_parse_status"] == "failed"
                and exc.code == resume["expected_failure"],
                where,
                resume["expected_failure"] or "parsed",
                exc.code,
            )
            continue
        if resume["expected_parse_status"] == "failed":
            report.tally("Unreadable files rejected").check(
                False, where, resume["expected_failure"], "parsed"
            )
            continue
        evaluate_resume(resume, parse_resume(text, today=as_of, region=REGION), report)


# --- JDs --------------------------------------------------------------------------------


def evaluate_jds(truth: dict[str, Any], report: Report) -> None:
    for jd in truth["jds"]:
        job = parse_job((SAMPLES / jd["file"]).read_text(encoding="utf-8"))
        where = jd["id"]
        for kind, found_list in [
            ("required", job.required_skills),
            ("preferred", job.preferred_skills),
        ]:
            found, expected = set(found_list), set(jd[f"{kind}_skills"])
            report.jd_skill_counts["tp"] += len(found & expected)
            report.jd_skill_counts["fp"] += len(found - expected)
            report.jd_skill_counts["fn"] += len(expected - found)
            report.jd_tally(f"{kind.capitalize()} skills, exact set").check(
                found == expected, where, sorted(expected), sorted(found)
            )
        checks = [
            ("Title", job.title, jd["title"]),
            ("Seniority", job.seniority.value, jd["seniority"]),
            (
                "Years (min, max)",
                (job.min_experience_years, job.max_experience_years),
                (jd["min_experience_years"], jd["max_experience_years"]),
            ),
            ("Degree level", job.degree_level, jd["degree_level"]),
            ("Fields of study", list(job.fields_of_study), jd["fields_of_study"]),
            (
                "Or equivalent experience",
                job.accepts_equivalent_experience,
                jd["accepts_equivalent_experience"],
            ),
        ]
        for name, found_value, expected_value in checks:
            report.jd_tally(name).check(
                found_value == expected_value, where, expected_value, found_value
            )


# --- Output -----------------------------------------------------------------------------


def met(ok: bool) -> str:
    return "yes" if ok else "**no**"


def render(report: Report, truth: dict[str, Any]) -> str:
    resumes = truth["resumes"]
    text_resumes = sum(r["expected_parse_status"] == "parsed" for r in resumes)
    precision, recall, f1 = prf(*(report.skill_counts[k] for k in ("tp", "fp", "fn")))
    mae = sum(report.experience_errors) / len(report.experience_errors)
    exact_totals = sum(e == 0 for e in report.experience_errors)
    t = report.fields

    def share_row(name: str, metric: str, target: float) -> Row:
        return (name, metric, t[name].cell(), f"≥ {target:.0%}", t[name].share >= target)

    rows: list[Row] = [
        share_row("Name", "Exact match after normalising case and spaces", 0.90),
        share_row("Email", "Exact match", 0.98),
        share_row("Phone", "Match after E.164 normalisation", 0.95),
        (
            "Skills",
            "Precision, recall and F1 (micro, over all resumes)",
            f"P {precision:.3f}, R {recall:.3f}, F1 {f1:.3f}",
            "F1 ≥ 0.85",
            f1 >= 0.85,
        ),
        (
            "Total experience",
            "Mean absolute error",
            f"{mae:.1f} months ({exact_totals}/{len(report.experience_errors)} exact)",
            "≤ 6 months",
            mae <= 6,
        ),
        share_row("Degree level", "Accuracy", 0.90),
        share_row("Sections", "Share of sections found", 0.90),
    ]
    extra_rows = [
        "Location", "LinkedIn and GitHub URLs", "Unmapped skill terms",
        "Roles (title, company, dates)", "Current title", "Education entries",
        "Unreadable files rejected",
    ]  # fmt: skip

    lines = [
        "# Parsing accuracy",
        "",
        f"Generated by `scripts/evaluate_parsing.py` from `sample_data/ground_truth.json` "
        f"({len(resumes)} resumes, {text_resumes} with text; {len(truth['jds'])} JDs). "
        f'Taxonomy v{get_taxonomy().version}; "Present" is {truth["as_of"]}.',
        "",
        "## Resumes: the design doc's targets",
        "",
        "| Field | Metric | Result | Target | Met |",
        "| --- | --- | --- | --- | --- |",
        *(f"| {f} | {m} | {r} | {g} | {met(ok)} |" for f, m, r, g, ok in rows),
        "",
        "## Resumes: other fields",
        "",
        "| Field | Exact match |",
        "| --- | --- |",
        *(f"| {name} | {t[name].cell()} |" for name in extra_rows if name in t),
        "",
        "## Job descriptions",
        "",
        "| Field | Exact match |",
        "| --- | --- |",
        *(f"| {name} | {tally.cell()} |" for name, tally in report.jd_fields.items()),
    ]
    jd_p, jd_r, jd_f1 = prf(*(report.jd_skill_counts[k] for k in ("tp", "fp", "fn")))
    lines += [f"| Skills, micro F1 | P {jd_p:.3f}, R {jd_r:.3f}, F1 {jd_f1:.3f} |", ""]

    misses = [m for tally in t.values() for m in tally.misses]
    misses += report.skill_misses + report.experience_misses
    misses += [m for tally in report.jd_fields.values() for m in tally.misses]
    lines += ["## Misses", ""]
    lines += [f"- {m}" for m in misses] or ["None."]
    if report.extra_sections:
        lines += ["", "Sections found that the ground truth doesn't list:", ""]
        lines += [f"- {m}" for m in report.extra_sections]
    lines += ["", "Resumes the UI would flag for manual review (parse confidence < 0.5): "]
    lines[-1] += ", ".join(report.needs_review) or "none."
    lines += [
        "",
        "## Caveat",
        "",
        "The parsers were developed against these same samples, so these numbers are an",
        "upper bound, not an estimate for real resumes. The unit tests in",
        "`backend/tests/unit/parsing` cover formats the samples don't have.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    args = parser.parse_args(argv)

    truth = json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))
    report = Report()
    evaluate_resumes(truth, report)
    evaluate_jds(truth, report)
    markdown = render(report, truth)

    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # "≥" on a Windows console
    print(markdown)
    if args.out:
        args.out.write_text(markdown, encoding="utf-8", newline="\n")
        print(f"Saved to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
