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

_TODO._

## Limitations and future work

_TODO._

## Data and ethics

- All data in this repository is synthetic.
- Name, gender, age, photo and location are never used in scoring.
- Career gaps and over-qualification are not penalised.
- The system ranks and explains; a human makes the hiring decision.

## License

[MIT](LICENSE)
