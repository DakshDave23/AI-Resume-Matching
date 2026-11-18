# AI Resume Matcher

Rank a batch of PDF/DOCX resumes against a job description and explain every point of every score.

Each resume gets a 0–100 match score built from four explainable components: **skills**, **semantic similarity**, **relevant experience**, and **education**. Scoring is deterministic: the same inputs always produce the same score, and every point traces back to a rule and a piece of evidence from the resume.

> **Status:** under active development. Sections marked _TODO_ are filled in as the build progresses.

> **Data notice:** all resumes and job descriptions in this repository are synthetic. No real person's data is used.

---

## Contents

1. [Demo](#demo)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Tech stack](#tech-stack)
5. [Quick start](#quick-start)
6. [Local development](#local-development)
7. [How matching works](#how-matching-works)
8. [Database](#database)
9. [API](#api)
10. [Results](#results)
11. [Project structure](#project-structure)
12. [Running tests](#running-tests)
13. [Limitations and future work](#limitations-and-future-work)
14. [Data and ethics](#data-and-ethics)
15. [License](#license)

## Demo

_TODO: demo GIF and video link._

## Features

- **Job description intake:** paste or upload a JD; required skills, preferred skills, minimum experience and education are extracted and can be corrected by the recruiter before matching.
- **Batch resume parsing:** upload 10–50 PDF/DOCX resumes; name, contact details, skills, work history, total and relevant years, and education are extracted.
- **Semantic matching:** tiered skill matching (exact → alias → related → contextual) plus requirement-level sentence-embedding similarity, so candidates match on meaning, not just keywords.
- **Ranking dashboard:** sortable, filterable table with live re-ranking when scoring weights change.
- **Explanations:** per-candidate breakdown of points earned and lost, with resume evidence for each JD requirement.

## Architecture

_TODO: architecture diagram._

React SPA → FastAPI REST API → extraction, parsing, embedding and matching services → PostgreSQL with pgvector. Parsing and scoring run as background tasks; the dashboard only reads stored results.

## Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query/Table |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| NLP | spaCy, sentence-transformers (`all-MiniLM-L6-v2`), rapidfuzz, dateparser |
| Database | PostgreSQL 16 + pgvector |
| DevOps | Docker Compose, GitHub Actions |

_TODO: "why" column._

## Quick start

_TODO._ Target flow:

```bash
cp .env.example .env
docker compose up --build
# open http://localhost:5173 and click "Load sample data"
```

## Local development

**Database** (Postgres 16 + pgvector 0.8.7, in Docker):

```bash
cp .env.example .env                   # once; Windows: copy .env.example .env
docker compose up -d --wait db         # start and wait until healthy
docker compose exec db psql -U resume -d resume_matcher   # SQL shell
docker compose down                    # stop (keeps data)
docker compose down -v                 # stop and DELETE all data
```

Postgres listens on `127.0.0.1:5432` only. The `vector` extension is enabled automatically on first start.

**Make targets** (macOS/Linux, or Windows with `winget install ezwinports.make`). Run `make` to list them all:

| Target | Plain command |
| --- | --- |
| `make db-up` | `docker compose up -d --wait db` |
| `make db-down` | `docker compose down` |
| `make db-reset` | `docker compose down -v` then `make db-up` |
| `make db-shell` | `docker compose exec db psql -U resume -d resume_matcher` |
| `make migrate` | `cd backend && alembic upgrade head` |
| `make seed` | `backend/.venv/Scripts/python scripts/seed_skills.py` |
| `make samples` | `backend/.venv/Scripts/python scripts/generate_samples.py` |
| `make install` | see the backend steps below |
| `make dev` | `cd backend && uvicorn app.main:app --reload` |
| `make check` | lint + type-check + tests (see below) |

**Backend** (Python 3.12):

```bash
cd backend
py -3.12 -m venv .venv                 # macOS/Linux: python3.12 -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head                   # create/upgrade the database schema
python ../scripts/seed_skills.py       # load the skills taxonomy (safe to re-run)
uvicorn app.main:app --reload          # http://localhost:8000/docs
```

**Skills taxonomy:** [`backend/app/data/skills_taxonomy.json`](backend/app/data/skills_taxonomy.json) lists ~430 skills in 15 categories, each with aliases (`k8s` → Kubernetes, `postgres` → PostgreSQL). To add a skill, add a line to the file and re-run the seed script. `seed_skills.py --check` validates the file without touching the database. It rejects any alias claimed by two skills.

Migrations live in `backend/alembic/versions/` and are numbered (`0001_...`). To add one after changing a model:

```bash
alembic revision --autogenerate --rev-id 0002 -m "what changed"
# review the generated file by hand, then:
alembic upgrade head
alembic check                          # "No new upgrade operations detected." = models and DB agree
```

Health check: `GET http://localhost:8000/api/v1/health` returns 200 with `"database": "ok"` when Postgres is up, or 503 when it isn't.

Lint, type-check and test:

```bash
ruff check . && ruff format --check . && mypy app tests && pytest
```

## Sample data

Everything in [`sample_data/`](sample_data/) is synthetic: invented people and companies, `example.com` emails, and phone numbers from ranges reserved for fiction.

| Path | What it is |
| --- | --- |
| `jds/*.txt` | Three job descriptions: Backend Java Developer (the main demo), Data Scientist, Frontend React Developer |
| `jds/expected.yaml` | What a perfect JD parser would extract from each |
| `personas/NN_*.yaml` | 15 hand-written resume personas, each built to test one thing (aliases, two-column layout, overlapping jobs, keyword stuffing, a scanned PDF, ...) |
| `resumes/` | The personas rendered to PDF and DOCX in one-column, two-column, table and scanned layouts |
| `ground_truth.json` | Expected name, contact, skills, roles, total months, degree level and ranking tier per resume |

The personas are the source; the resumes and ground truth are generated from them:

```bash
backend/.venv/Scripts/python scripts/generate_samples.py --check   # validate personas only
backend/.venv/Scripts/python scripts/generate_samples.py           # re-render (deterministic)
```

The generator refuses to write anything if the ground truth would be incomplete. For example, if a resume mentions a taxonomy skill that its persona doesn't list, it stops with an error.

## Text extraction

Every upload is checked before parsing. The file's content decides its type, not its extension: a PDF must start with `%PDF-`, and a DOCX must be a ZIP containing `word/document.xml`. Files over 5 MB, and DOCX files that unpack to an unreasonable size, are rejected with a reason.

- **PDF:** PyMuPDF text blocks, read in column order. When a page has a real gutter, the left column is read fully before the right, so two-column resumes don't interleave. A PDF with almost no text is reported as *"Looks like a scanned image; OCR is not enabled."*
- **DOCX:** page header first (templates often put the name there), then paragraphs and tables in document order (each merged cell once), then the footer. Word list items get a `- ` prefix.
- **Cleaning:** NFKC normalisation (ligatures, full-width letters), every bullet symbol becomes `- `, words wrapped at a hyphen are rejoined, and whitespace is tidied. Line breaks are kept.

To see exactly what the parser will receive from a file:

```bash
cd backend
python -m app.services.extraction ../sample_data/resumes/03_candidate_a_two_column.pdf
```

## Section detection

Resume text is split into contact, summary, experience, skills, projects, education and certifications. A line is a section header when it has 5 words or fewer, no sentence punctuation or digits, starts with a capital letter, and fuzzy-matches (rapidfuzz) one of ~90 known headers: `Tech Stack`, `Career History`, `About Me`, `ACADEMIC QUALIFICATIONS:` and so on. Typos still match ("Work Experiance"). A line in ALL CAPS or ending in a colon needs a fuzzy score of 85; any other line needs 90. Text before the first header is the contact block. Recognised but unused sections (Hobbies, Languages, References) are kept as `other`, so their text doesn't leak into the section above them.

## Contact details

| Field | How it is found |
| --- | --- |
| Email | Pattern match in the contact block, then anywhere (some templates use the footer) |
| Phone | `phonenumbers` finds valid numbers only and normalises them to E.164. Numbers without a country code use `PHONE_DEFAULT_REGION` (default `IN`). |
| LinkedIn / GitHub | URL patterns, normalised to `https://linkedin.com/in/<id>` and `https://github.com/<user>` |
| Name | The first piece of a contact line with 2–4 capitalised words and no digits, `@` or job-title words (`Meera Pillai — Full Stack Developer` → `Meera Pillai`). A `Name:` label wins. |
| Location | A piece of a contact line shaped like a place (`Pune, India`, `Austin, TX 78701`), or a `Location:` label |

Name and location use the layout of the contact lines rather than named-entity recognition. On these short, list-like blocks spaCy's small English model missed 2 of the 14 sample names and 3 of the 14 locations; these rules get all 14 right.

## Skill extraction

Skills are mapped to the taxonomy's canonical names, with the section and line each one came from.

1. **Exact and alias pass.** A spaCy PhraseMatcher holds every name and alias, plus a simple plural ("tax audits" → Auditing). It matches whole tokens, so "Java" never fires inside "JavaScript". When matches overlap, the longest wins: "Spring Boot" is not also "Spring", and "T-SQL" is not also "SQL".
2. **Everyday words.** Terms that are also English words ("go", "rest", "spring", "express", "C", "R") only match in free text when spelled like the skill ("Go", "Express") or in capitals ("REST"). "ML" counts but "50 ml" doesn't. A one-letter skill (C, R) is never part of something else: "C-level", "R&D", "grade C", "Type C cable", "Section R" and "25 C" are not skills. Inside a skills list, any spelling counts.
3. **Fuzzy pass.** In the skills section, each comma-separated item is judged as a whole. An item that no single exact match covers is compared with rapidfuzz (`token_sort_ratio` ≥ 90, and again with spaces removed): "Kubernetis" → Kubernetes, "Type Script" → TypeScript, "Postgress SQL" → PostgreSQL (not SQL).
4. **Unmapped.** List items that match nothing (e.g. "Hystrix") are kept so the recruiter can add them to the taxonomy.

Group labels ("Frontend:"), contact links (`github.com/...` is not GitHub) and degree names ("Electronics and Communication" is not the soft skill) are not skill claims. On the 14 text samples the extractor finds all 200 expected skills with no false positives.

## Work history

Each date range in the Experience section anchors one role. Supported formats include `Jan 2020 – Present`, `January 2020 - Mar 2022`, `2019 – 2021`, `03/2018 – 06/2020`, `2018-03 – 2020-06`, `Jan '20 – Mar '22`, `Since 2021`, and the end words Present, Current, Now, Till date, To date and Ongoing. A start year alone means January, an end year alone means December, and months count inclusively.

Title and company come from the role's header: the date line itself (`Engineer | Acme, Pune | Jan 2020 – Present`), up to two lines above it, or the lines below it when a table template puts the date first. The piece containing a job-title word is the title, so `Acme | Senior Engineer` works too. A city after the company (`Acme Fintech, Bengaluru`) becomes the role's location.

- **Total experience** merges overlapping date ranges, so two jobs held at once count once (persona 9: 137 months of roles, 113 months of experience). Gaps are not penalised.
- **Internships** (intern, trainee, apprentice) are listed but left out of the total.
- **No dates at all:** roles are still read from their title and company lines, and the total comes from a statement such as "7 years of experience" in the summary.
- **Years per skill:** the merged dates of the roles whose title or bullets mention the skill, so a skill never exceeds the total.

Dates use a small built-in grammar rather than dateparser, which fills missing parts from today ("2019" would become 2019-*this month*).

## Education

Each entry gets a degree, a level, a field, an institution and a year. The resume's highest level is used for scoring.

| Level | Examples |
| --- | --- |
| 5 doctorate | PhD, Ph.D., Doctor of Philosophy |
| 4 master's | M.Tech, M.Sc, MS, MBA, MCA, Master's, Master of Computer Applications, PGDM / Post Graduate Diploma |
| 3 bachelor's | B.Tech, B.E., BE, B.Sc, BCA, B.Com, Bachelor's, Bachelor of Technology |
| 2 diploma | Diploma, Associate Degree |
| 1 high school | HSC, SSC, 12th, Class XII, High School Diploma |

- Two-letter forms that are also words (BE, ME, MS, BA, MA) count only in capitals, and "MS Excel" is not a master's.
- **Field** is the text after "in" ("B.Tech in Computer Science"). After "of", a dash, comma or bracket it counts only if it is a known field ("Master of Computer Applications", "B.E. (Electronics and Communication)").
- **Institution** is the piece containing University, College, Institute, School, Academy, IIT/NIT, ...
- **Year** is the latest year in the entry, so "2016 – 2020" gives 2020.

Entries may sit on one line or several, with the institution above or below the degree. A dual degree counts at its highest level.

## Job description parsing

A JD (pasted text, TXT, PDF or DOCX) is read with the same section engine, skill matcher and degree patterns as resumes.

- **Title, company, location** come from "Job Title:", "Company:" and "Location:" labels, or the first short line for the title. **Seniority** (junior, mid, senior, lead, principal) comes from the title's words; a title without one is mid level.
- **Sections:** Responsibilities, Requirements (Qualifications, Must have) and Preferred (Nice to have, Bonus). "About us" and benefits text is not scanned for skills. A JD with no headers is read whole.
- **Required or preferred** is decided for each skill mention. The section decides first; cues in the same clause override it:

  | | Required | Preferred |
  | --- | --- | --- |
  | Strong cues | must, required, mandatory, minimum | a plus, bonus, preferred, nice to have, not required |
  | Weak cues | strong, proficient, solid, expert | familiarity with, exposure to, basic knowledge |

  Strong cues outrank weak ones ("Strong communication skills are a plus" is preferred), and in a mixed sentence the nearest cue wins ("Java is required and Kotlin is a plus"). "Strong" doesn't move a skill out of a Nice-to-have list. With no signal (Responsibilities), a skill is required.
- **Years:** "5+ years", "3–5 years", "minimum of 4 years", "at least 2 yrs", "five years". Years that lead straight into skills ("4+ years of Java and Spring Boot", "Java (5+ years)") become those skills' minimum years. The JD's minimum is the largest figure in a required general sentence ("4+ years of professional experience", "3+ years as a data scientist").
- **Education:** the required level is the lowest one a required clause accepts ("BS/MS in CS" → bachelor's; "Master's preferred" is not required). Fields come from "in Statistics, Computer Science, Mathematics or a related field". "Or equivalent experience" marks education as soft.
- **Requirement rows:** every bullet (or prose sentence) under Responsibilities, Requirements and Preferred, tagged responsibility, experience, education, skill or other.

## Trying the parsers

To see what the parser gets from a resume (contact details, work history, education, skills, then sections) or a JD (title, skills, years, degree, requirement rows):

```bash
cd backend
python -m app.services.parsing ../sample_data/resumes/02_java_aliases.docx
python -m app.services.parsing --jd ../sample_data/jds/backend_java_developer.txt
```

## How matching works

```
Score = 100 × Σ(wᵢ · Sᵢ) / Σ(wᵢ)   over active components
```

Default weights: skills 0.40, semantic 0.30, experience 0.20, education 0.10. A component the JD doesn't specify drops out and the rest are rescaled.

_TODO: link to `docs/matching-algorithm.md`._

## Database

_TODO: Mermaid ER diagram._

## API

_TODO._ Swagger UI is served at `/docs` once the backend is running.

## Results

_TODO: parsing accuracy, ranking quality, keyword-only ablation, batch timing._

## Project structure

```text
.
├── backend/        FastAPI app, services, migrations, tests
├── frontend/       React + Vite SPA
├── sample_data/    synthetic JDs, personas, resumes, ground truth
├── scripts/        sample generation, taxonomy seeding, evaluation
└── docs/           architecture, matching algorithm, database
```

## Running tests

```bash
make test          # unit + integration (integration needs: make db-up)
make check         # lint, type check and tests, as CI runs them
cd backend && pytest tests/unit/parsing -v   # just the parsers
```

The parser tests come in two kinds:

- **Unit tests** (`test_dates.py`, `test_sections.py`, `test_skills.py`, `test_jd_parser.py`, ...) pin each rule with small inputs, including formats the samples don't have: 21 date formats, overlapping, nested, back-to-back and gapped roles, upper-case, colon and two-column headers, aliases (k8s), fuzzy variants (Node JS), the Java/JavaScript guard, short aliases (C, R, JS, ML), required vs preferred cues, "3–5 years" and "5+ years of Java".
- **Sample tests** (`test_*_samples.py`) run every parser on the 14 text samples and 3 JDs and compare with `sample_data/ground_truth.json`. They share `tests/samples.py`, which extracts each sample file once per run.

## Limitations and future work

_TODO._

## Data and ethics

- All data in this repository is synthetic.
- Name, gender, age, photo and location are never used in scoring.
- Career gaps and over-qualification are not penalised.
- The system ranks and explains; a human makes the hiring decision.

## License

[MIT](LICENSE)
