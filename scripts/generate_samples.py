"""Render the synthetic sample resumes and write ground_truth.json (design doc §10).

Inputs (hand-written, reviewed like code):
    sample_data/personas/NN_*.yaml   one resume persona each
    sample_data/jds/*.txt            three job descriptions
    sample_data/jds/expected.yaml    what a perfect JD parser would extract

Outputs (generated, committed):
    sample_data/resumes/NN_<slug>.pdf|docx
    sample_data/ground_truth.json

Usage (from the repo root, with the backend virtualenv):
    backend/.venv/Scripts/python scripts/generate_samples.py          # Windows
    backend/.venv/bin/python scripts/generate_samples.py              # macOS/Linux
    ... scripts/generate_samples.py --check                           # validate only

Output is deterministic: running it twice produces byte-identical files.
All people, companies, emails and phone numbers are fictional (example.com
emails, phone numbers from ranges reserved for fiction).
"""

import argparse
import html
import io
import json
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import pymupdf
import yaml
from docx import Document
from docx.document import Document as DocxDocument
from docx.shared import Cm, Pt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.services.nlp.taxonomy import TaxonomySkill, get_taxonomy, normalize_term

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data"
PERSONA_DIR = SAMPLES / "personas"
RESUME_DIR = SAMPLES / "resumes"
JD_DIR = SAMPLES / "jds"
GROUND_TRUTH = SAMPLES / "ground_truth.json"

# "Present" means this month in the ground truth. Fixed so regenerating never changes the files.
AS_OF = date(2026, 11, 1)
FIXED_PDF_DATE = "D:20261101000000Z"
FIXED_DATETIME = datetime(2026, 11, 1)
FIXED_ZIP_TIME = (2026, 11, 1, 0, 0, 0)

A4 = pymupdf.paper_rect("a4")
MARGIN = 42

Tier = Literal["strong", "good", "partial", "weak", "failed"]
YM = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")


# --- Persona schema ----------------------------------------------------------


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Contact(Strict):
    name: str
    email: str
    phone: str
    location: str
    linkedin: str | None = None
    github: str | None = None


class Role(Strict):
    title: str
    company: str
    location: str | None = None
    start: str | None = None  # "YYYY-MM" or "YYYY"
    end: str | None = None  # "YYYY-MM", "YYYY" or "present"
    internship: bool = False
    bullets: list[str] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def _valid_date(cls, value: str | None) -> str | None:
        if value is not None and value != "present" and not YM.match(value):
            raise ValueError(f"expected YYYY-MM, YYYY or 'present', got {value!r}")
        return value


class Education(Strict):
    degree: str
    field: str
    institution: str
    year: int
    level: int = Field(ge=0, le=5)


class Persona(Strict):
    id: int
    slug: str
    persona: str
    tests: str
    format: Literal["pdf", "docx"]
    layout: Literal["one_column", "two_column", "tables", "scanned"]
    date_format: Literal["mon_yyyy", "month_yyyy", "mm_yyyy", "yyyy", "none"]
    role_style: Literal["pipe", "at", "stacked"]
    bullet: str = "•"
    present_word: str = "Present"
    date_separator: str = " \u2013 "  # en dash, as most resumes use
    uppercase_headers: bool = False
    header_colon: bool = False
    section_titles: dict[str, str] = Field(default_factory=dict)
    contact_in_header: bool = False
    docx_list_bullets: bool = False
    skills_style: Literal["grouped", "paragraph"] = "grouped"
    expected_tier: dict[str, Tier]
    relevant_experience_months: dict[str, int] = Field(default_factory=dict)
    stated_experience_months: int | None = None

    contact: Contact
    headline: str
    summary: str
    experience: list[Role]
    skills: dict[str, list[str]]
    unmapped: list[str] = Field(default_factory=list)
    also_mentions: list[str] = Field(default_factory=list)
    not_skills: list[str] = Field(default_factory=list)
    education: list[Education]
    certifications: list[str] = Field(default_factory=list)

    @property
    def filename(self) -> str:
        return f"{self.id:02d}_{self.slug}.{self.format}"


class ExpectedJD(Strict):
    id: str
    file: str
    title: str
    seniority: str
    required_skills: list[str]
    preferred_skills: list[str]
    min_experience_years: float | None
    max_experience_years: float | None
    degree_level: int | None
    fields_of_study: list[str]
    accepts_equivalent_experience: bool


# --- Dates and experience ----------------------------------------------------

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_LONG = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip


def to_month(value: str, *, is_end: bool) -> tuple[int, int]:
    """'present' -> AS_OF; 'YYYY' -> January (start) or December (end) of that year."""
    if value == "present":
        return AS_OF.year, AS_OF.month
    if len(value) == 4:
        return int(value), 12 if is_end else 1
    year, month = value.split("-")
    return int(year), int(month)


def month_index(ym: tuple[int, int]) -> int:
    return ym[0] * 12 + ym[1] - 1


def format_date(value: str, persona: Persona) -> str:
    if value == "present":
        return persona.present_word
    year, month = to_month(value, is_end=False)
    match persona.date_format:
        case "mon_yyyy":
            return f"{MONTHS[month - 1]} {year}"
        case "month_yyyy":
            return f"{MONTHS_LONG[month - 1]} {year}"
        case "mm_yyyy":
            return f"{month:02d}/{year}"
        case "yyyy":
            return str(year)
    return ""


def date_range(role: Role, persona: Persona) -> str:
    if persona.date_format == "none" or role.start is None or role.end is None:
        return ""
    start, end = format_date(role.start, persona), format_date(role.end, persona)
    return f"{start}{persona.date_separator}{end}"


def total_experience_months(roles: list[Role]) -> int:
    """Union of inclusive month ranges, overlaps merged, internships excluded."""
    spans = sorted(
        (month_index(to_month(r.start, is_end=False)), month_index(to_month(r.end, is_end=True)))
        for r in roles
        if r.start and r.end and not r.internship
    )
    total, current_start, current_end = 0, None, None
    for start, end in spans:
        if current_end is None or start > current_end + 1:
            if current_end is not None and current_start is not None:
                total += current_end - current_start + 1
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None and current_start is not None:
        total += current_end - current_start + 1
    return total


# --- Ground truth: skills ----------------------------------------------------


def _term_pattern(term: str, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![\w+#.]){re.escape(term)}(?![\w+#])", flags)


AMBIGUOUS_WORDS = {"rest", "chef", "spring", "express", "node", "vault", "ruby", "swift"}


def taxonomy_mentions(text: str) -> set[str]:
    """Naive scan for taxonomy terms in free text. Only used to keep ground truth complete.

    Longest terms are matched first and their text is blanked out, so "Spring Boot" never
    also counts as "Spring". Short or ambiguous terms (Go, R, C, ML, rest) must appear in
    their canonical spelling or upper case.
    """
    found: set[str] = set()
    remaining = text
    for term, skill in sorted(get_taxonomy().term_index().items(), key=lambda kv: -len(kv[0])):
        if len(term) <= 3 or term in AMBIGUOUS_WORDS:
            spellings = {skill.name, term.upper()} if len(term) <= 3 else {skill.name}
            patterns = [_term_pattern(s, case_sensitive=True) for s in spellings]
        else:
            patterns = [_term_pattern(term, case_sensitive=False)]
        for pattern in patterns:
            if pattern.search(remaining):
                found.add(skill.name)
                remaining = pattern.sub(lambda m: " " * len(m.group()), remaining)
    return found


def resolve_skill(term: str) -> TaxonomySkill | None:
    return get_taxonomy().term_index().get(normalize_term(term))


def expected_skills(p: Persona, errors: list[str]) -> list[str]:
    names: set[str] = set()
    for items in p.skills.values():
        for item in items:
            skill = resolve_skill(item)
            if skill:
                names.add(skill.name)
            elif item not in p.unmapped:
                errors.append(f"persona {p.id}: skill {item!r} is not in the taxonomy "
                              f"(add it there, or list it under `unmapped`)")  # fmt: skip
    canonical = {s.name for s in get_taxonomy().skills}
    for name in p.also_mentions:
        if name not in canonical:
            errors.append(f"persona {p.id}: also_mentions {name!r} is not a canonical skill name")
        names.add(name)

    free_text = " ".join(
        [p.headline, p.summary, *p.certifications]
        + [line for r in p.experience for line in (r.title, *r.bullets)]
        + [f"{e.degree} {e.field}" for e in p.education]
    )
    unaccounted = taxonomy_mentions(free_text) - names - set(p.not_skills)
    for name in sorted(unaccounted):
        errors.append(
            f"persona {p.id}: text mentions {name!r}; add it to also_mentions or not_skills"
        )
    return sorted(names, key=str.lower)


# --- Ground truth: records ---------------------------------------------------


def e164(phone: str) -> str:
    return "+" + re.sub(r"\D", "", phone)


def current_title(p: Persona) -> str | None:
    dated = [r for r in p.experience if r.end and not r.internship]
    if not dated:
        return p.experience[0].title if p.experience else None
    return max(dated, key=lambda r: month_index(to_month(r.end or "", is_end=True))).title


def resume_truth(p: Persona, errors: list[str]) -> dict[str, object]:
    scanned = p.layout == "scanned"
    has_dates = p.date_format != "none"
    if has_dates and any(r.start is None or r.end is None for r in p.experience):
        errors.append(f"persona {p.id}: every role needs start and end unless date_format is none")
    if not has_dates and p.stated_experience_months is None:
        errors.append(f"persona {p.id}: undated roles need stated_experience_months")

    sections = ["summary", "experience", "skills", "education"]
    if p.certifications:
        sections.append("certifications")

    def norm(value: str | None, *, is_end: bool) -> str | None:
        if value is None or value == "present":
            return None
        y, m = to_month(value, is_end=is_end)
        return f"{y:04d}-{m:02d}"

    return {
        "id": p.id,
        "file": f"resumes/{p.filename}",
        "persona": p.persona,
        "tests": p.tests,
        "format": p.format,
        "layout": p.layout,
        "expected_parse_status": "failed" if scanned else "parsed",
        "expected_failure": "scanned_pdf" if scanned else None,
        "name": p.contact.name,
        "email": p.contact.email,
        "phone_e164": e164(p.contact.phone),
        "location": p.contact.location,
        "linkedin": p.contact.linkedin,
        "github": p.contact.github,
        "current_title": current_title(p),
        "skills": expected_skills(p, errors),
        "unmapped_skill_terms": p.unmapped,
        "roles": [
            {
                "title": r.title,
                "company": r.company,
                "start": norm(r.start, is_end=False),
                "end": norm(r.end, is_end=True),
                "is_current": r.end == "present",
                "is_internship": r.internship,
                "date_precision": None
                if not r.start
                else ("year" if len(r.start) == 4 else "month"),
            }
            for r in p.experience
        ],
        "total_experience_months": (
            total_experience_months(p.experience) if has_dates else p.stated_experience_months
        ),
        "experience_source": "dates" if has_dates else "summary_statement",
        "relevant_experience_months": p.relevant_experience_months or None,
        "degree_level": max(e.level for e in p.education),
        "education": [e.model_dump() for e in p.education],
        "sections": sections,
        "expected_tier": p.expected_tier,
    }


def jd_truth(jd: ExpectedJD, errors: list[str]) -> dict[str, object]:
    canonical = {s.name for s in get_taxonomy().skills}
    listed = set(jd.required_skills) | set(jd.preferred_skills)
    for name in sorted(listed - canonical):
        errors.append(f"JD {jd.id}: {name!r} is not a canonical skill name")
    text = (JD_DIR / jd.file).read_text(encoding="utf-8")
    for name in sorted(taxonomy_mentions(text) - listed):
        errors.append(f"JD {jd.id}: text mentions {name!r}, which expected.yaml does not list")
    for name in sorted(listed - taxonomy_mentions(text)):
        errors.append(f"JD {jd.id}: expected skill {name!r} does not appear in the text")
    return {"file": f"jds/{jd.file}", **jd.model_dump(exclude={"file"})}


# --- Rendering: shared -------------------------------------------------------

DEFAULT_TITLES = {
    "summary": "Summary",
    "experience": "Work Experience",
    "skills": "Technical Skills",
    "education": "Education",
    "certifications": "Certifications",
}


def section_title(p: Persona, key: str) -> str:
    title = p.section_titles.get(key, DEFAULT_TITLES[key])
    title = title.upper() if p.uppercase_headers else title
    return f"{title}:" if p.header_colon else title


def role_lines(role: Role, p: Persona) -> list[str]:
    """The heading lines of one role; the date range is the anchor a parser looks for."""
    dates = date_range(role, p)
    where = f"{role.company}, {role.location}" if role.location else role.company
    match p.role_style:
        case "pipe":
            return [" | ".join(x for x in (role.title, where, dates) if x)]
        case "at":
            return [x for x in (f"{role.title} at {role.company}", dates) if x]
        case _:  # stacked
            return [x for x in (role.title, where, dates) if x]


def skill_lines(p: Persona) -> list[str]:
    if p.skills_style == "paragraph" or len(p.skills) == 1:
        return [", ".join(item for items in p.skills.values() for item in items)]
    return [f"{group}: {', '.join(items)}" for group, items in p.skills.items()]


def education_line(e: Education) -> str:
    return f"{e.degree} in {e.field}, {e.institution}, {e.year}"


def contact_lines(p: Persona) -> list[str]:
    c = p.contact
    links = " | ".join(x for x in (c.linkedin, c.github) if x)
    return [x for x in (f"{c.email} | {c.phone} | {c.location}", links) if x]


# --- Rendering: PDF (HTML + CSS laid out by PyMuPDF's Story) -----------------

CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; line-height: 1.3; color: #222; }
h1 { font-size: 20pt; margin: 0 0 2pt 0; }
h2 { font-size: 11.5pt; margin: 12pt 0 4pt 0; color: #1f3a5f;
     border-bottom: 0.6pt solid #1f3a5f; }
p { margin: 0 0 3pt 0; }
.headline { font-size: 12pt; color: #555; margin-bottom: 4pt; }
.contact { font-size: 9pt; color: #444; }
.role { font-weight: bold; margin-top: 6pt; }
.meta { color: #555; }
.bullet { margin-left: 10pt; }
"""


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def html_header(p: Persona) -> str:
    lines = "".join(f'<p class="contact">{esc(x)}</p>' for x in contact_lines(p))
    return f'<h1>{esc(p.contact.name)}</h1><p class="headline">{esc(p.headline)}</p>{lines}'


def html_section(p: Persona, key: str) -> str:
    out = [f"<h2>{esc(section_title(p, key))}</h2>"]
    if key == "summary":
        out.append(f"<p>{esc(p.summary)}</p>")
    elif key == "experience":
        for role in p.experience:
            first, *rest = role_lines(role, p)
            out.append(f'<p class="role">{esc(first)}</p>')
            out.extend(f'<p class="meta">{esc(x)}</p>' for x in rest)
            out.extend(f'<p class="bullet">{esc(p.bullet)} {esc(b)}</p>' for b in role.bullets)
    elif key == "skills":
        out.extend(f"<p>{esc(x)}</p>" for x in skill_lines(p))
    elif key == "education":
        out.extend(f"<p>{esc(education_line(e))}</p>" for e in p.education)
    elif key == "certifications":
        out.extend(f'<p class="bullet">{esc(p.bullet)} {esc(c)}</p>' for c in p.certifications)
    return "".join(out)


def sections_of(p: Persona) -> list[str]:
    keys = ["summary", "experience", "skills", "education"]
    return [*keys, "certifications"] if p.certifications else keys


class Flow:
    """One HTML story and where it goes: `first` rect on page 1, `later` on later pages."""

    def __init__(self, body: str, first: pymupdf.Rect, later: pymupdf.Rect | None) -> None:
        self.story = pymupdf.Story(html=body, user_css=CSS)
        self.first, self.later, self.more = first, later, True


def flows_to_pdf(flows: list[Flow]) -> bytes:
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page_number = 0
    while any(f.more for f in flows):
        device = writer.begin_page(A4)
        for flow in flows:
            rect = flow.first if page_number == 0 else flow.later
            if not flow.more or rect is None:
                continue
            more, _ = flow.story.place(rect)
            flow.story.draw(device)
            flow.more = bool(more)
        writer.end_page()
        page_number += 1
        if page_number > 5:
            raise RuntimeError("layout did not converge; content overflows a non-continuing area")
    writer.close()
    return buffer.getvalue()


def render_pdf_bytes(p: Persona, layout: str) -> bytes:
    full = pymupdf.Rect(A4.x0 + MARGIN, A4.y0 + MARGIN, A4.x1 - MARGIN, A4.y1 - MARGIN)
    if layout != "two_column":
        body = html_header(p) + "".join(html_section(p, k) for k in sections_of(p))
        return flows_to_pdf([Flow(body, full, full)])

    # Two columns: a narrow sidebar (skills, education) and a wide main column (summary,
    # experience). Text blocks interleave vertically, which naive top-to-bottom reading breaks.
    header_h, gutter, sidebar_w = 92, 18, 165
    top = full.y0 + header_h
    sidebar = pymupdf.Rect(full.x0, top, full.x0 + sidebar_w, full.y1)
    main = pymupdf.Rect(sidebar.x1 + gutter, top, full.x1, full.y1)
    side_keys = [k for k in sections_of(p) if k in ("skills", "education", "certifications")]
    main_keys = [k for k in sections_of(p) if k not in side_keys]
    return flows_to_pdf(
        [
            Flow(html_header(p), pymupdf.Rect(full.x0, full.y0, full.x1, top), None),
            Flow("".join(html_section(p, k) for k in side_keys), sidebar, sidebar),
            Flow("".join(html_section(p, k) for k in main_keys), main, main),
        ]
    )


def finalize_pdf(pdf: pymupdf.Document, path: Path, title: str) -> None:
    pdf.set_metadata(
        {
            "title": title,
            "author": "Synthetic sample (generate_samples.py)",
            "creator": "generate_samples.py",
            "producer": "PyMuPDF",
            "creationDate": FIXED_PDF_DATE,
            "modDate": FIXED_PDF_DATE,
        }
    )
    pdf.save(path, garbage=4, deflate=True, no_new_id=True)


def write_pdf(p: Persona, path: Path) -> None:
    if p.layout == "scanned":
        # Render the page to a greyscale image and wrap it in a PDF with no text layer.
        source = pymupdf.open("pdf", render_pdf_bytes(p, "one_column"))
        pixmap = source[0].get_pixmap(dpi=110, colorspace=pymupdf.csGRAY)
        pdf = pymupdf.open()
        page = pdf.new_page(width=A4.width, height=A4.height)
        page.insert_image(page.rect, pixmap=pixmap)
    else:
        pdf = pymupdf.open("pdf", render_pdf_bytes(p, p.layout))
    finalize_pdf(pdf, path, f"Resume — {p.contact.name}")


# --- Rendering: DOCX ---------------------------------------------------------


def add_text(
    doc: DocxDocument, text: str, *, bold: bool = False, size: float | None = None
) -> None:
    run = doc.add_paragraph().add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)


def add_bullet(doc: DocxDocument, p: Persona, text: str) -> None:
    if p.docx_list_bullets:
        doc.add_paragraph(text, style="List Bullet")  # bullet glyph comes from Word numbering
    else:
        doc.add_paragraph(f"{p.bullet} {text}")


def docx_section(doc: DocxDocument, p: Persona, key: str) -> None:
    add_text(doc, section_title(p, key), bold=True, size=12)
    if key == "summary":
        add_text(doc, p.summary)
    elif key == "experience":
        for role in p.experience:
            first, *rest = role_lines(role, p)
            add_text(doc, first, bold=True)
            for line in rest:
                add_text(doc, line)
            for b in role.bullets:
                add_bullet(doc, p, b)
    elif key == "skills":
        for line in skill_lines(p):
            add_text(doc, line)
    elif key == "education":
        for e in p.education:
            add_text(doc, education_line(e))
    elif key == "certifications":
        for c in p.certifications:
            add_bullet(doc, p, c)


def docx_tables(doc: DocxDocument, p: Persona) -> None:
    """Every block in a table, as many Word resume templates do."""
    head = doc.add_table(rows=1, cols=2)
    left, right = head.rows[0].cells
    left.text = f"{p.contact.name}\n{p.headline}"
    right.text = "\n".join(contact_lines(p))

    for key in sections_of(p):
        doc.add_paragraph()
        table = doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        if key == "experience":
            title_row = table.add_row().cells
            title_row[0].merge(title_row[1]).text = section_title(p, key)
            for role in p.experience:
                cells = table.add_row().cells
                cells[0].text = date_range(role, p)
                lines = [f"{role.title} | {role.company}, {role.location}"]
                lines += [f"{p.bullet} {b}" for b in role.bullets]
                cells[1].text = "\n".join(lines)
        else:
            cells = table.add_row().cells
            cells[0].text = section_title(p, key)
            if key == "summary":
                cells[1].text = p.summary
            elif key == "skills":
                cells[1].text = "\n".join(skill_lines(p))
            elif key == "education":
                cells[1].text = "\n".join(education_line(e) for e in p.education)
            else:
                cells[1].text = "\n".join(p.certifications)


def write_docx(p: Persona, path: Path) -> None:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Cm(1.8)
        section.left_margin = section.right_margin = Cm(2)

    if p.layout == "tables":
        docx_tables(doc, p)
    else:
        if p.contact_in_header:
            # Name and contact live in the page header, which plain body-text readers miss.
            header = doc.sections[0].header
            header.paragraphs[0].text = f"{p.contact.name} — {p.headline}"
            for line in contact_lines(p):
                header.add_paragraph(line)
        else:
            add_text(doc, p.contact.name, bold=True, size=18)
            add_text(doc, p.headline, size=12)
            for line in contact_lines(p):
                add_text(doc, line)
        for key in sections_of(p):
            docx_section(doc, p, key)

    props = doc.core_properties
    props.title = f"Resume — {p.contact.name}"
    props.author = props.last_modified_by = "Synthetic sample (generate_samples.py)"
    props.created = props.modified = FIXED_DATETIME
    props.revision = 1

    buffer = io.BytesIO()
    doc.save(buffer)
    path.write_bytes(deterministic_zip(buffer.getvalue()))


def deterministic_zip(data: bytes) -> bytes:
    """Rewrite a DOCX (a ZIP) with fixed timestamps so regenerating gives identical bytes."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            dst.writestr(info, src.read(item.filename))
    return out.getvalue()


# --- Self-check of rendered files ---------------------------------------------


def extracted_text(path: Path) -> str:
    if path.suffix == ".pdf":
        with pymupdf.open(path) as pdf:
            return "".join(page.get_text() for page in pdf)
    doc = Document(str(path))
    parts = [para.text for para in doc.paragraphs]
    parts += [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    parts += [para.text for s in doc.sections for para in s.header.paragraphs]
    return "\n".join(parts)


def check_rendered(p: Persona, path: Path, errors: list[str]) -> int:
    text = extracted_text(path)
    if p.layout == "scanned":
        if len(text.strip()) >= 100:
            errors.append(f"{path.name}: scanned PDF unexpectedly has a text layer")
    else:
        for needle in (p.contact.name, p.contact.email, p.experience[0].company):
            if needle not in text:
                errors.append(f"{path.name}: {needle!r} not found in extracted text")
    return len(text)


# --- Main ----------------------------------------------------------------------


def load_personas(errors: list[str]) -> list[Persona]:
    personas = []
    for path in sorted(PERSONA_DIR.glob("*.yaml")):
        try:
            persona = Persona.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except ValidationError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if not path.name.startswith(f"{persona.id:02d}_{persona.slug}"):
            errors.append(f"{path.name}: file name must match id and slug")
        personas.append(persona)
    ids = [p.id for p in personas]
    if len(ids) != len(set(ids)):
        errors.append("duplicate persona ids")
    return personas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate inputs, write nothing")
    args = parser.parse_args()

    errors: list[str] = []
    personas = load_personas(errors)
    jds = [
        ExpectedJD.model_validate(item)
        for item in yaml.safe_load((JD_DIR / "expected.yaml").read_text(encoding="utf-8"))
    ]
    resumes = [resume_truth(p, errors) for p in personas]
    jd_records = [jd_truth(jd, errors) for jd in jds]
    if errors:
        print("Input problems:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    if args.check:
        print(f"OK: {len(personas)} personas and {len(jds)} JDs are valid (nothing written)")
        return 0

    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    for stale in RESUME_DIR.glob("*.*"):
        stale.unlink()
    print(f"{'file':<36} {'layout':<11} {'chars':>6}  skills  months")
    for persona, truth in zip(personas, resumes, strict=True):
        path = RESUME_DIR / persona.filename
        (write_pdf if persona.format == "pdf" else write_docx)(persona, path)
        chars = check_rendered(persona, path, errors)
        skills = truth["skills"]
        assert isinstance(skills, list)
        print(f"{path.name:<36} {persona.layout:<11} {chars:>6}  {len(skills):>6}  "
              f"{truth['total_experience_months']!s:>6}")  # fmt: skip

    if errors:
        print("Rendering problems:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1

    ground_truth = {
        "description": "Expected parser output for the synthetic samples. All data is fictional.",
        "generated_by": "scripts/generate_samples.py",
        "as_of": AS_OF.isoformat(),
        "conventions": {
            "months": "Inclusive whole months: Jan 2020 - Mar 2020 is 3. "
            "'Present' is the as_of month.",
            "year_only_dates": "A start year means January; an end year means December.",
            "total_experience_months": "Union of role date ranges with overlaps merged; "
            "internships excluded. Undated resumes use the figure stated in the summary.",
            "skills": "Canonical taxonomy names the resume genuinely contains, from the skills "
            "section or the text. unmapped_skill_terms are skill-list items not in the taxonomy.",
            "expected_tier": "strong > good > partial > weak; failed means parsing should fail.",
        },
        "jds": jd_records,
        "resumes": resumes,
    }
    GROUND_TRUTH.write_text(
        json.dumps(ground_truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {len(personas)} resumes to {RESUME_DIR.relative_to(ROOT)} "
          f"and {GROUND_TRUTH.relative_to(ROOT)}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
