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

**Backend** (Python 3.12):

```bash
cd backend
py -3.12 -m venv .venv                 # macOS/Linux: python3.12 -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload          # http://localhost:8000/docs
```

Health check: `GET http://localhost:8000/api/v1/health`

Lint, type-check and test:

```bash
ruff check . && ruff format --check . && mypy app tests && pytest
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
