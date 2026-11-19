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
| NLP | spaCy (tokenizer and PhraseMatcher), sentence-transformers (`all-MiniLM-L6-v2`) on CPU PyTorch, rapidfuzz, phonenumbers |
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
| `make eval-parsing` | `backend/.venv/Scripts/python scripts/evaluate_parsing.py --out docs/parsing-accuracy.md` |
| `make eval-ranking` | `backend/.venv/Scripts/python scripts/evaluate_ranking.py --out docs/ranking-results.md` |
| `make install` | see the backend steps below |
| `make dev` | `cd backend && uvicorn app.main:app --reload` |
| `make check` | lint + type-check + tests (see below) |

**Backend** (Python 3.12):

```bash
cd backend
py -3.12 -m venv .venv                 # macOS/Linux: python3.12 -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
# Linux only, first: pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"                # includes PyTorch (CPU) for the embedding model
alembic upgrade head                   # create/upgrade the database schema
python ../scripts/seed_skills.py       # load the skills taxonomy and embed each skill
uvicorn app.main:app --reload          # http://localhost:8000/docs
```

**Embedding model:** `EMBEDDING_MODEL` (default `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions) is downloaded from Hugging Face on first use (about 90 MB) and read from the local cache after that, so later starts work offline. The API loads it once, in the background, about 8 seconds after start-up. Until it is ready, `/health` answers 503 and routes that need it answer 503 with `model_loading`. Any other 384-dimensional model works (e.g. `BAAI/bge-small-en-v1.5`). After switching, run `seed_skills.py --reembed` and recalibrate the scoring thresholds.

**Skills taxonomy:** [`backend/app/data/skills_taxonomy.json`](backend/app/data/skills_taxonomy.json) lists ~430 skills in 15 categories, each with aliases (`k8s` → Kubernetes, `postgres` → PostgreSQL). To add a skill, add a line to the file and re-run the seed script. `seed_skills.py --check` validates the file without touching the database. It rejects any alias claimed by two skills. The seed script then embeds every skill that has no vector yet (new, renamed or recruiter-added). Each skill is embedded as "name (category)", e.g. "Kafka (messaging)".

Migrations live in `backend/alembic/versions/` and are numbered (`0001_...`). To add one after changing a model:

```bash
alembic revision --autogenerate --rev-id 0002 -m "what changed"
# review the generated file by hand, then:
alembic upgrade head
alembic check                          # "No new upgrade operations detected." = models and DB agree
```

Health check: `GET http://localhost:8000/api/v1/health` returns 200 when Postgres, pgvector and the embedding model are all ready, and 503 otherwise. `checks` says which one: `{"database": "ok", "pgvector": "0.8.7", "embedding_model": "ok" | "loading" | "failed"}`.

Lint, type-check and test:

```bash
ruff check . && ruff format --check . && mypy app tests && pytest
pytest -m "not model"                  # skip the tests that load the real embedding model
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

## Chunks and vectors

After parsing, each document is embedded in one batched call and stored in pgvector:

| What | Vector of | Used for |
| --- | --- | --- |
| `resume_chunks` | Each role (title, company and its bullets), each project, the summary; at most 120 words, cut between bullets | Requirement coverage and evidence |
| `work_experiences.embedding` | Role title + description | Role relevance (§6.4) |
| `resumes.embedding` | Normalised mean of the resume's chunk vectors | Whole-document similarity |
| `job_requirements.embedding` | Each JD bullet or sentence | Requirement coverage |
| `jobs.embedding` | Normalised mean of the requirement vectors | Whole-document similarity |
| `skills.embedding` | "Name (category)", e.g. "Kafka (messaging)" | Related-skill credit |

The skills section is not chunked: a bare list of names would let keyword stuffing pass for described experience. A whole role matches requirements as well as its best single bullet (0.46 vs 0.43 for "Microservices" on sample 3), so roles are kept whole.

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

Default weights: skills 0.40, semantic 0.30, experience 0.20, education 0.10. A component the JD doesn't ask for drops out and the rest are rescaled: experience without a minimum, education without a degree, skills without skills. With no years and no degree, skills and semantic count 0.57 and 0.43. "Or equivalent experience" halves education's weight first. Ties are broken by required-skill coverage, then relevant years.

Each resume is scored right after it is parsed, in the same transaction that counts it, so when a batch shows `completed` every resume in it is scored and ranked. Results are upserted on (job, resume), so scoring again never duplicates. Every result stores its weights and `scoring_version`. A scoring bug can't undo a good parse: scoring runs in its own savepoint.

### Skill score

Each JD skill (weight 1.0 if required, 0.5 if preferred) earns credit from the first tier that fires:

| Tier | Rule | Credit | Example (sample 3 vs the Java JD) |
| --- | --- | --- | --- |
| Exact | The resume has the skill, written as its name | 1.0 | Java |
| Alias | The same skill through an alias or a fuzzy match | 1.0 | REST → REST APIs |
| Related | A resume skill of the same category with cosine ≥ 0.58 | 0.5 | MySQL → PostgreSQL (0.62), RabbitMQ → Kafka (0.59) |
| Contextual | Not listed, but an experience or project passage matches the skill's name with cosine ≥ 0.43 | 0.5 | "Split a monolith into 8 independently deployed services" → Microservices (0.46) |
| Missing | None of the above | 0 | AWS |

Skill score = Σ weight × credit ÷ Σ weight. For sample 3 that is 4.75 ÷ 6.5 = 0.731, the design doc's worked example, and a test checks it with the real model.

- **Years check:** when the JD asks for "5+ years of Java" and the resume shows fewer, the credit is multiplied by max(0.5, used ÷ required).
- **Never equivalent:** Java/JavaScript, C/C#, C/C++ and React/React Native are never related, and a passage naming the other one never counts as context.
- **Custom skills:** a skill the recruiter adds is in no extractor dictionary, so its name is looked up in the resume text.

**Thresholds were measured, not taken from the doc.** The doc starts at 0.80 (related) and 0.55 (contextual). `all-MiniLM-L6-v2` never reaches those for real matches: MySQL/PostgreSQL scores 0.62. Over all 3 JDs × 14 samples, 0.58 separates the intended related pairs (Kafka/RabbitMQ 0.59 and up) from the wrong ones (Next.js/Node.js 0.55, Java/Python 0.54). 0.43 separates the one described-but-unnamed skill (0.46) from the closest wrong one (0.40). The margins are thin, so a test pins every indirect match across the samples. Both values live in [`scoring_config.py`](backend/app/services/matching/scoring_config.py) and get recalibrated in step 30.

### Semantic similarity

```
best_i   = max over resume passages of cos(requirement_i, passage)
coverage = weighted mean of best_i            (required 1.0, preferred 0.5)
raw      = 0.7 × coverage + 0.3 × cos(whole JD, whole resume)
S_sem    = clip((raw − 0.30) ÷ (0.47 − 0.30), 0, 1)
```

- **Calibration (L = 0.30, H = 0.47).** Raw cosines sit in a narrow band. Following the design doc's rule, L is the average raw score of the "weak" sample/JD pairs (0.295) and H that of the "strong" ones (0.473). The doc's starting values (0.20 / 0.70) assume a wider-spread model.
- **Result on the samples:** the accountant, the data scientist and the keyword stuffer score 0.00–0.03 against the Java JD. Strong pairs average 0.95 and weak ones 0.10, and in every JD each strong sample scores above every weak one. Good candidates bunch at the top, so this component mainly separates relevant from irrelevant; skills and experience do the fine ranking.
- **Years and degree sentences are left out.** "4+ years of professional experience" matches any summary that states years: it scores 0.40 against a chartered accountant's. These sentences already count in the experience and education components.
- **Requirement table:** each requirement keeps its best passage and a status: covered (≥ 0.40), partial (0.30–0.40) or not covered.

### Relevant experience

Total years can mislead: a QA engineer with 5 years who moved to backend 18 months ago has 1.5 years of backend experience.

1. **Role profile:** the JD's title and responsibility sentences, embedded as one text.
2. **Each role** (title + bullets) is compared with it: cosine ≥ 0.55 counts fully, 0.42–0.55 counts half, below that not at all.
3. **Month by month,** each month counts once, at the best factor of any role active then, so overlapping jobs are never double counted. Internships don't count.
4. **Relevant years ÷ the JD's minimum,** capped at 1. A JD without a minimum leaves this component out. Being above the JD's maximum is shown but never penalised: such a penalty works as a proxy for age.

Against the Java JD, every figure in the ground truth comes out exactly: sample 8 has 1.5 relevant years (its QA role scores 0.39), Candidate A 4.5 (support role 0.34), sample 4 2.0 (internship excluded). The design doc's partial cut-off of 0.40 would have sat 0.01 above the QA role, so it is 0.42.

### Education

| Highest degree vs the JD's | Score |
| --- | --- |
| Equal or higher | 1.0 |
| One level below | 0.5 |
| Two or more below, or none found | 0.2: not 0, since the parser may have missed it |

- **Field of study:** when the JD names fields and none of the candidate's degrees is in one of them, the score is multiplied by 0.8. "Same field" means an equivalence group (Computer Science ≈ IT ≈ Computer Engineering ≈ Computer Applications …; Electronics ≈ Electrical; Mathematics ≈ Statistics; Commerce ≈ Accounting ≈ Finance), or names with cosine ≥ 0.6. A degree with no field written is not penalised.
- **"Or equivalent experience"** in the JD halves education's weight, and relevant years ≥ the JD's minimum + 2 stand in for the degree.
- A JD that names no degree leaves this component out.

Against the Java JD (a Bachelor's in CS or IT), sample 11's Diploma in Computer Engineering scores 0.5. Samples 8 (Electronics), 12 (Statistics) and 13 (Accounting) meet the level but not the field: 0.8.

### Explanations

Every score comes with reasons built from the same numbers by fixed templates, with no LLM, so they always agree with the score:

- **Verdict:** 80+ strong, 65–79 good, 50–64 partial, below 50 weak.
- **Breakdown:** points earned against points available per component. They add up to the match % exactly as displayed: rounding is distributed so the parts sum to the total.
- **Strengths and gaps,** each with its points. Sample 3 (Candidate A) against the Java JD:
  - Microservices not listed, but inferred from the "Java Developer | Contoso Payments" role (−3.1 points).
  - PostgreSQL credited at half: related skill MySQL found (−3.1 points).
  - Missing preferred skill AWS (−3.1 points).
  - Kafka credited at half: related skill RabbitMQ found (−1.5 points).

  That is the design doc's worked example exactly: 10.8 points lost on skills.
- **Data-quality notes:** for example "Education not found; check the original file", and experience above the JD's maximum (shown, never penalised).

_TODO: link to `docs/matching-algorithm.md`._

## Database

_TODO: Mermaid ER diagram._

## API

REST under `/api/v1`. Swagger UI at http://localhost:8000/docs lists every route with its request and response shapes, so it doubles as a demo.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | Database, pgvector and embedding-model readiness; 503 until all are ready |
| POST | `/jobs` | Create a job from pasted JD text (`{"text": ..., "title": optional}`) |
| POST | `/jobs/upload` | Create a job from a PDF, DOCX or TXT file |
| GET | `/jobs` | List jobs, newest first, with resume count and top score (`limit`, `offset`) |
| GET | `/jobs/{job_id}` | One job: extracted skills (required/preferred, weight, min years, source phrase), requirement sentences, years, degree, fields |
| PATCH | `/jobs/{job_id}/requirements` | Recruiter edits; marks existing scores stale |
| POST | `/jobs/{job_id}/resumes` | Upload 1–50 PDF/DOCX resumes; 202 with the batch id, accepted files and rejected files with reasons |
| GET | `/batches/{batch_id}` | Batch progress for polling: status, parsed / failed / pending counts, and each file's parse status, error, confidence (`needs_review` below 0.5) and candidate name |
| POST | `/jobs/{job_id}/match` | Re-score every parsed resume (optionally saving new `weights` first); 409 if a run is already going |
| GET | `/jobs/{job_id}/rankings` | Ranked candidates: match %, verdict, component scores, years, top skills, missing required count. Filters: `min_score`, `skill` (an alias works), `search`; `sort` = score, name, relevant_experience, total_experience |
| GET | `/jobs/{job_id}/rankings/export` | The same rows as CSV (cells that would run as spreadsheet formulas are escaped) |
| GET | `/jobs/{job_id}/candidates/{resume_id}` | The full stored analysis: contact, component scores, matched and missing skills, requirement matches, explanation |
| PATCH | `/jobs/{job_id}/weights` | Save the four weights (each ≥ 0, not all 0) and recompute every total |

**Resume uploads.** Each file is checked on arrival: size, real type (magic bytes, not the extension) and duplicates within the upload. A bad file is listed under `rejected` with a reason, and the rest go ahead. Accepted files are stored as `<uuid>.<ext>` under `UPLOAD_DIR`; the recruiter's file name is kept for display only. A background task then parses each one (extract → parse → chunk → embed → save) in its own transaction, so a failure marks only that file `failed`, with a reason such as "Looks like a scanned image; OCR is not enabled." The 15 samples finish in about 2 seconds on a laptop CPU. If the server stops mid-batch (a crash, or `--reload`), it finishes the remaining files when it starts again.

`PATCH /requirements` changes only the fields sent. `skills` replaces the whole chip list. Each chip names a skill by `skill_id`, or by `name` (canonical or alias: `k8s` finds Kubernetes). An unknown name adds a custom skill. Chips the recruiter changed are saved with `added_by: "recruiter"`.

Every error has the same shape: `{"error": {"code": "...", "message": "...", "details": ...}}`.

| Status | When |
| --- | --- |
| 202 | Upload accepted; parsing continues in the background |
| 409 | A scoring run for the job is already in progress |
| 400 | Empty file |
| 404 | No such job |
| 413 | File over the upload limit |
| 415 | Not a PDF, DOCX or TXT |
| 422 | Invalid body, scanned or corrupt file, unknown skill id, duplicate skill, max years below min |
| 503 | `model_loading` |

## Results

### Parsing accuracy

Measured by `make eval-parsing` on the 14 text samples and 3 JDs against `sample_data/ground_truth.json`. The full report, including every miss, is in [docs/parsing-accuracy.md](docs/parsing-accuracy.md).

| Field | Metric | Result | Target |
| --- | --- | --- | --- |
| Name | Exact match after normalising case and spaces | 100% (14/14) | ≥ 90% |
| Email | Exact match | 100% (14/14) | ≥ 98% |
| Phone | Match after E.164 normalisation | 100% (14/14) | ≥ 95% |
| Skills | Precision, recall and F1 | P 1.00, R 1.00, F1 1.00 (200 skills) | F1 ≥ 0.85 |
| Total experience | Mean absolute error | 0.0 months | ≤ 6 months |
| Degree level | Accuracy | 100% (14/14) | ≥ 90% |
| Sections | Share of sections found | 100% (57/57) | ≥ 90% |
| JD extraction | Required/preferred skills, years, degree, fields | 100% (3/3 JDs) | — |

The scanned PDF (persona 15) is rejected with `scanned_pdf`, as expected. **Read these as an upper bound:** the parsers were developed against these same samples. The parser unit tests cover formats the samples don't have, and real resumes will be messier.

### Ranking quality

Measured by `make eval-ranking`: every text sample scored against every sample JD with the real model. The full report, with each ranking, is in [docs/ranking-results.md](docs/ranking-results.md).

| JD | Spearman (match % vs expected tier) | Precision at k | Last place |
| --- | --- | --- | --- |
| Backend Java | **0.93** (goal ≥ 0.8) | 0.75 (k = 4) | sample 13, the accountant |
| Data Scientist | 0.57 | 1.00 (k = 1) | sample 11 |
| Frontend React | 0.45 | 1.00 (k = 1) | sample 13 |

- **The miss:** for the Java JD, sample 11 ("good": every skill an exact match, but only a diploma) ranks 4th, 2.7 points above sample 3 ("strong": two skills only related, one inferred). Under the default weights the diploma costs 5 points and the indirect skills 10.8. Only raising education's weight to 0.2 would change that. The design doc's 40/30/20/10 were kept rather than tuned to one pair of samples.
- **The other two JDs** each have one strong sample and 12–13 equally "weak" ones, so Spearman there mostly measures the order among the weak. The strong sample ranks first, by 57 points or more.
- **Keyword-only ablation** (semantic weight 0, related and inferred skills off): the keyword stuffer (sample 7) climbs from 11th to 6th. Sample 3, whose skills are partly described rather than listed, loses 15.6 points. Sample 2's synonyms are all in the alias dictionary, so it stays put.
- **Stability:** partial credit at 0.4 or 0.6 instead of 0.5 gives identical rankings. Moving any weight by ±0.1 keeps the same top 3, apart from the order of two candidates 0.5 points apart, and except lowering education, which lets sample 11 into the top 3.
- **Speed:** the 14 readable samples are extracted, parsed, embedded and scored in about 1–4 seconds on a laptop CPU, once the model is loaded.

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
- **End-to-end ranking test** (`tests/integration/test_end_to_end_ranking.py`, real model and database): create the Java job, upload all 15 samples, poll until done, fetch the rankings. It checks that sample 15 failed with a reason, sample 13 ranks last, and every strong or good sample ranks above every partial or weak one. The design doc's last check, that the four strong samples fill the top 4, is marked as an expected failure until the calibration step. Sample 11 (rated "good": every skill matched exactly, but only a diploma) ranks 4th, 2.7 points above sample 3 (rated "strong", with three skills only related or inferred).

Tests that load the real embedding model are marked `model` (`pytest -m "not model"` skips them); tests that need Postgres are marked `integration`.

## Limitations and future work

_TODO._

## Data and ethics

- All data in this repository is synthetic.
- Name, gender, age, photo and location are never used in scoring.
- Career gaps and over-qualification are not penalised.
- The system ranks and explains; a human makes the hiring decision.

## License

[MIT](LICENSE)
