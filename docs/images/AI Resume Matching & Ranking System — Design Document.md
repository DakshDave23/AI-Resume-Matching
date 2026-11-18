# AI Resume Matching & Ranking System — Design Document

Nov 16, 2026 · @Daksh Dave

## 1. Overview

The system ranks a batch of 10+ PDF/DOCX resumes against one job description (JD). Each resume gets a 0–100 score built from four explainable parts: skills, semantic similarity, relevant experience and education.

**Goals**

- Paste or upload a JD, then extract required skills, preferred skills, minimum experience and education. The recruiter can correct the extraction before matching.
- Upload 10–50 resumes in one batch and parse name, contact details, skills, work history, total and relevant years, and education.
- Score every resume 0–100, list matched and missing skills, and match on meaning, not only exact keywords.
- Rank candidates in a sortable dashboard and open any candidate to see why they got their score.
- Keep every point traceable to a rule and a piece of evidence from the resume.

**Non-goals for the prototype:** login and multi-tenancy, OCR for scanned PDFs (stretch goal), letting an LLM decide the score, and production-scale throughput.

**How the design answers the evaluation rubric**

| Parameter | Weight | How this design earns it |
| --- | --- | --- |
| Functional application | 25% | Full flow (JD → upload → rankings → detail) runs with one `docker compose up` |
| JD-to-resume matching logic | 25% | Tiered skill matching (exact → alias → semantic → contextual), requirement-level semantic coverage, relevance-weighted experience |
| Resume parsing accuracy | 15% | Section-aware parser plus a curated skills taxonomy; accuracy measured against ground truth and published in the README |
| Matching score and explanation | 15% | Deterministic formula, points-lost breakdown, evidence snippet for every JD requirement |
| UI/UX and usability | 10% | 3-step wizard, editable requirement chips, live parse status, weight sliders, candidate detail page |
| Code quality and documentation | 10% | Layered FastAPI services, typed schemas, tests, CI, about 40 conventional commits, README plus algorithm write-up |

**Four decisions shape everything below**

1. **Deterministic hybrid scoring, not LLM scoring.** The same inputs always give the same score, and you can explain each point in an interview.
2. **PostgreSQL with pgvector.** Relational data, flexible JSON and embeddings live in one database.
3. **Recruiter in the loop.** Extracted JD requirements are shown as editable chips before scoring, which fixes most extraction errors cheaply.
4. **Synthetic data with ground truth.** Parsing accuracy and ranking quality are measured, not claimed.

## 2. System architecture

A React single-page app calls a FastAPI REST API. The API stores uploaded files, runs parsing and scoring as background tasks, and keeps everything in PostgreSQL with pgvector.

&#91;embedded content: system architecture · 3 tiers, 5 services\]

Parsing and scoring run in the background pipeline. The routers only read stored results, so the dashboard never waits on NLP work.

| Component | Responsibility | Main libraries |
| --- | --- | --- |
| React SPA | JD input, batch upload, ranking dashboard, candidate detail | React, TanStack Query, TanStack Table |
| API routers | Request validation, HTTP status codes, response schemas | FastAPI, Pydantic v2 |
| Extraction service | PDF/DOCX to clean plain text | PyMuPDF, python-docx |
| Parsing service | Sections, contact, skills, experience, education; JD requirements | spaCy, regex, dateparser, rapidfuzz |
| Embedding service | Turns text into vectors; model loaded once at startup | sentence-transformers |
| Matching engine | Four component scores and the weighted total | NumPy |
| Explanation generator | Reasons, points lost, evidence snippets | Plain Python templates |
| Pipeline runner | Processes a batch in the background and updates status | FastAPI BackgroundTasks |
| PostgreSQL + pgvector | Relational tables, JSONB, embedding vectors | SQLAlchemy 2, Alembic |
| File storage | Original files on a Docker volume, stored under UUID names | Local disk |

**Request lifecycle**

1. The recruiter submits a JD. The API extracts text, parses requirements, embeds each requirement sentence, saves the job and returns the extraction for review.
2. The recruiter edits the requirement chips. A `PATCH` call saves the final requirements.
3. The recruiter uploads resumes. The API validates and hashes each file, saves it, creates `resumes` rows with status `queued`, and returns `202 Accepted` with a batch id at once.
4. The background pipeline handles each resume: extract → clean → segment → parse → chunk → embed → save. Status becomes `parsed`, or `failed` with a readable reason.
5. After the last resume, the pipeline scores every resume against the job and writes `match_results`.
6. The frontend polls batch status every 2 seconds and loads the rankings when the batch is done.
7. Clicking a row reads the stored match result and parsed resume. Nothing is recomputed.

**Why BackgroundTasks instead of Celery and Redis:** a batch of 10–50 resumes finishes in seconds, so a queue adds containers without adding value. The pipeline is one plain function, so moving to RQ or Celery later changes one file. Encoding is CPU-bound, so it runs in FastAPI's thread pool and never blocks the event loop.

## 3. Tech stack and rationale

The NLP lives in Python, so the backend is FastAPI; data lives in PostgreSQL with pgvector; the UI is React with TypeScript. Every piece runs locally on a laptop CPU, with no paid API.

| Layer | Choice | Why | Considered instead |
| --- | --- | --- | --- |
| Frontend | React 18 + TypeScript + Vite | Listed in the brief; TypeScript catches API-shape bugs; Vite starts in seconds | Next.js (server rendering not needed) |
| UI components | Tailwind CSS + shadcn/ui | Accessible table, dialog, slider, badge and tabs; polished look fast | MUI (heavier, generic look) |
| Server state | TanStack Query | Caching, plus `refetchInterval` polling for parse status | Redux (too much ceremony) |
| Ranking table | TanStack Table | Headless sorting, filtering, column control | AG Grid |
| Upload | react-dropzone | Multi-file drag and drop with type filtering | Plain file input |
| Charts | Recharts | Score breakdown bars and score gauge | Chart.js |
| Backend | Python 3.11 + FastAPI | Same language as the NLP; Pydantic validation; free Swagger UI at `/docs` for the demo | Flask (no typing or async), Django (heavy) |
| ORM and migrations | SQLAlchemy 2.0 + Alembic | Typed models; each schema change is a versioned migration you can show in commits | Raw SQL |
| PDF text | PyMuPDF, pdfplumber as fallback | Fast; text blocks with coordinates let you fix reading order in two-column resumes | PyPDF2 (weak layout handling) |
| DOCX text | python-docx | Reads paragraphs and tables; many resume templates use tables | docx2txt (loses structure) |
| NER and skill matching | spaCy `en_core_web_sm` + PhraseMatcher | PERSON, ORG, DATE entities; PhraseMatcher finds thousands of skill terms in one pass | NLTK |
| Fuzzy matching | rapidfuzz | Catches variants such as "Node JS" or "Postgre SQL" | fuzzywuzzy (slower) |
| Dates and phones | dateparser, python-dateutil, phonenumbers | Parses "Jan 2020", "03/2019", "Present"; validates phone numbers | Hand-written regex only |
| Embeddings | sentence-transformers with `all-MiniLM-L6-v2` (384-dim); `BAAI/bge-small-en-v1.5` as a switchable alternative | Small and fast on CPU, strong on short texts, 384 dims keep storage light; model name set by env var | OpenAI embeddings (cost, resume text leaves the machine), `all-mpnet-base-v2` (768-dim, larger and slower) |
| Database | PostgreSQL 16 + pgvector | Relational joins, JSONB and vectors in one store (Section 4) | MongoDB |
| Tests | pytest + FastAPI TestClient; Vitest for a few UI tests | Fast feedback on parser and scorer math | — |
| Code quality | ruff (lint and format), mypy, ESLint, Prettier, pre-commit | Clean diffs and consistent style across commits | black + flake8 |
| DevOps | Docker Compose (db, backend, frontend), GitHub Actions, Makefile | One command to run; CI badge on the README | Manual setup |

**Why sentence embeddings rather than TF-IDF or an LLM.** TF-IDF only matches the same surface words, so "built RESTful services" never meets "REST API development". Embeddings place those two phrases close together, which is the semantic matching the brief asks for. An LLM judge is slower, costs money, can give different scores on reruns and sends candidate data to a third party. It is kept as an optional stretch for writing a two-line summary, never for the score.

**Optional upgrades, behind config flags:** a cross-encoder such as `cross-encoder/ms-marco-MiniLM-L-6-v2` to re-score requirement–evidence pairs, and Tesseract OCR for scanned PDFs.

Pin exact versions in `requirements.txt` and `package-lock.json`, and check the latest stable releases on day one.

## 4. Database design

Use PostgreSQL 16 with the pgvector extension (Docker image `pgvector/pgvector:pg16`). The data is relational, the parsed output is semi-structured, and matching needs vector similarity; Postgres covers all three in one store.

### Why PostgreSQL over MongoDB

| Need | PostgreSQL + pgvector | MongoDB |
| --- | --- | --- |
| Ranking = join of job × resume × match result | One SQL join with `ORDER BY` on an index | `$lookup` aggregation pipeline |
| One score per job–resume, scores within 0–100 | `UNIQUE`, `CHECK` and foreign keys in the schema | Enforced only in application code |
| Flexible parser output | `JSONB` columns | Native documents |
| Embedding similarity | `vector(384)` columns, cosine operator `<=>`, optional HNSW index | Mainly through managed Atlas Vector Search |
| Skill analytics ("who knows Kafka?") | `GROUP BY` on a bridge table | Aggregation over arrays |

MongoDB fits the parsed-resume document well, but JSONB gives that same flexibility while keeping constraints and joins for rankings.

### Entities and relationships

&#91;embedded content: ER diagram · 12 tables, 13 relationships\]

Deleting a job or a resume cascades to every table beneath it; `skills` and `candidates` are shared and never cascade.

- `jobs` 1–N `job_requirements`, `job_skills`, `upload_batches`, `match_results`
- `skills` is the shared taxonomy; `job_skills` and `resume_skills` are its many-to-many bridges
- `upload_batches` 1–N `resumes`; `candidates` 1–N `resumes` (deduplicated by email)
- `resumes` 1–N `resume_skills`, `work_experiences`, `educations`, `resume_chunks`
- `jobs` M–N `resumes` through `match_results`, one row per pair

### Enum types

| Enum | Values |
| --- | --- |
| `job_status` | draft, parsed, archived |
| `batch_status` | processing, completed, completed\_with\_errors |
| `parse_status` | queued, parsing, parsed, failed |
| `file_type` | pdf, docx |
| `requirement_type` | required, preferred |
| `requirement_category` | skill, experience, education, responsibility, other |
| `skill_source` | skills\_section, experience, projects, summary, other |
| `degree_level` (SMALLINT 0–5) | 0 none, 1 high school, 2 diploma, 3 bachelor's, 4 master's, 5 doctorate |

### Table specifications

**jobs** — one row per JD

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | UUID | PK, `gen_random_uuid()` |
| title | VARCHAR(200) | NOT NULL |
| company | VARCHAR(200) | Nullable |
| raw\_text | TEXT | NOT NULL; the JD as pasted or extracted |
| source\_filename | VARCHAR(255) | Null when pasted |
| min\_experience\_years | NUMERIC(4,1) | Nullable, `CHECK >= 0` |
| max\_experience\_years | NUMERIC(4,1) | Nullable, `CHECK >= min_experience_years` |
| required\_degree\_level | SMALLINT | Nullable, 0–5 |
| required\_fields\_of\_study | TEXT\[\] | e.g. {Computer Science, Information Technology} |
| scoring\_weights | JSONB | Default skills 0.40, semantic 0.30, experience 0.20, education 0.10 |
| parsed\_json | JSONB | Full extractor output, kept for debugging |
| embedding | VECTOR(384) | Whole-JD vector |
| status | job\_status | NOT NULL, default draft |
| created\_at, updated\_at | TIMESTAMPTZ | NOT NULL, default `now()` |

**job\_requirements** — each requirement bullet or sentence, embedded for semantic coverage

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | BIGSERIAL | PK |
| job\_id | UUID | FK → jobs, `ON DELETE CASCADE`, indexed |
| text | TEXT | NOT NULL |
| category | requirement\_category | NOT NULL |
| requirement\_type | requirement\_type | NOT NULL |
| position | SMALLINT | Order in the JD |
| embedding | VECTOR(384) | NOT NULL |

**skills** — the curated taxonomy, seeded from `skills_taxonomy.json`

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | SERIAL | PK |
| canonical\_name | VARCHAR(100) | UNIQUE, NOT NULL (e.g. PostgreSQL) |
| category | VARCHAR(40) | language, framework, database, cloud, devops, tool, methodology, soft |
| aliases | TEXT\[\] | e.g. {postgres, psql, postgre sql}; GIN index |
| embedding | VECTOR(384) | Vector of the canonical name plus a short description |
| is\_custom | BOOLEAN | Default false; true when a recruiter adds a skill |

**job\_skills** — bridge between a job and its required or preferred skills

| Column | Type | Constraints and notes |
| --- | --- | --- |
| job\_id | UUID | FK → jobs, cascade; part of PK |
| skill\_id | INT | FK → skills; part of PK; indexed |
| requirement\_type | requirement\_type | NOT NULL |
| weight | NUMERIC(3,2) | Default 1.00 required, 0.50 preferred; `CHECK 0–1` |
| min\_years | NUMERIC(4,1) | Nullable, from phrases like "5+ years of Java" |
| source\_text | TEXT | The JD phrase it came from |
| added\_by | VARCHAR(10) | parser or recruiter |

**upload\_batches** — one upload action

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | UUID | PK |
| job\_id | UUID | FK → jobs, cascade, indexed |
| total\_files, processed\_files, failed\_files | INT | `CHECK processed_files + failed_files <= total_files` |
| status | batch\_status | NOT NULL |
| created\_at, completed\_at | TIMESTAMPTZ | completed\_at nullable |

**candidates** — the person behind a resume (synthetic data only)

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | UUID | PK |
| full\_name | VARCHAR(200) | Nullable if not found |
| email | VARCHAR(254) | Partial unique index on `lower(email)` where not null |
| phone | VARCHAR(30) | Normalised to E.164 |
| location | VARCHAR(200) | Shown in UI, never used in scoring |
| linkedin\_url, github\_url | TEXT | Nullable |
| created\_at | TIMESTAMPTZ | NOT NULL |

**resumes** — one uploaded document and its parse output

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | UUID | PK |
| batch\_id | UUID | FK → upload\_batches, cascade, indexed |
| candidate\_id | UUID | FK → candidates, nullable until parsed, indexed |
| original\_filename | VARCHAR(255) | NOT NULL |
| storage\_path | TEXT | NOT NULL; file saved as `<uuid>.<ext>` |
| file\_type | file\_type | NOT NULL |
| file\_size\_bytes | INT | `CHECK <= 5242880` (5 MB) |
| file\_sha256 | CHAR(64) | NOT NULL; `UNIQUE (batch_id, file_sha256)` blocks duplicate uploads |
| raw\_text | TEXT | Extracted, cleaned text |
| sections | JSONB | Section name → text |
| parsed\_json | JSONB | Full structured output |
| total\_experience\_months | INT | Union of date ranges, overlaps merged |
| highest\_degree\_level | SMALLINT | 0–5 |
| current\_title | VARCHAR(200) | Most recent role |
| parse\_status | parse\_status | NOT NULL, default queued |
| parse\_error | TEXT | Human-readable reason when failed |
| parse\_confidence | NUMERIC(3,2) | 0–1, share of expected fields found |
| embedding | VECTOR(384) | Whole-resume vector |
| created\_at, parsed\_at | TIMESTAMPTZ | parsed\_at nullable |

**resume\_skills** — bridge between a resume and the skills found in it

| Column | Type | Constraints and notes |
| --- | --- | --- |
| resume\_id | UUID | FK → resumes, cascade; part of PK |
| skill\_id | INT | FK → skills; part of PK; indexed |
| sources | skill\_source\[\] | Sections where it appeared |
| mention\_count | SMALLINT | `CHECK >= 1` |
| years\_used | NUMERIC(4,1) | Sum of durations of roles that mention it |
| evidence | TEXT | Best supporting snippet |

**work\_experiences**

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | BIGSERIAL | PK |
| resume\_id | UUID | FK → resumes, cascade, indexed |
| job\_title, company | VARCHAR(200) | Nullable |
| start\_date, end\_date | DATE | `CHECK end_date IS NULL OR end_date >= start_date` |
| is\_current | BOOLEAN | True for "Present" |
| duration\_months | INT | `CHECK >= 0` |
| description | TEXT | Bullets under the role |
| embedding | VECTOR(384) | Title + description; used for relevance |

**educations**

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | BIGSERIAL | PK |
| resume\_id | UUID | FK → resumes, cascade, indexed |
| degree\_raw | VARCHAR(200) | As written, e.g. "B.Tech" |
| degree\_level | SMALLINT | 0–5 |
| field\_of\_study, institution | VARCHAR(200) | Nullable |
| graduation\_year | SMALLINT | `CHECK 1950–2100` |

**resume\_chunks** — embedded passages for semantic matching and evidence

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | BIGSERIAL | PK |
| resume\_id | UUID | FK → resumes, cascade |
| section | VARCHAR(30) | experience, projects, summary, skills |
| chunk\_index | SMALLINT | `UNIQUE (resume_id, chunk_index)` |
| text | TEXT | NOT NULL |
| embedding | VECTOR(384) | NOT NULL |

**match\_results** — one scored pair of job and resume

| Column | Type | Constraints and notes |
| --- | --- | --- |
| id | UUID | PK |
| job\_id, resume\_id | UUID | FKs, cascade; `UNIQUE (job_id, resume_id)`, upsert on rescore |
| overall\_score | NUMERIC(5,2) | `CHECK 0–100` |
| skill\_score, semantic\_score, experience\_score, education\_score | NUMERIC(4,3) | `CHECK 0–1`; null when a component is inactive |
| required\_skill\_coverage | NUMERIC(4,3) | Share of required skills matched |
| relevant\_experience\_months | INT | Relevance-weighted experience |
| matched\_skills | JSONB | Skill, match type, credit, resume term, similarity, evidence |
| missing\_skills | JSONB | Skill and requirement type |
| requirement\_matches | JSONB | Each JD requirement, best resume chunk, similarity |
| explanation | JSONB | Summary, positives, negatives, points lost per component |
| weights\_used | JSONB | Snapshot of weights for this run |
| scoring\_version | VARCHAR(20) | e.g. v1.0 |
| rank | INT | Position within the job |
| computed\_at | TIMESTAMPTZ | NOT NULL |

### Index and storage decisions

- Index every foreign key; Postgres does not do this automatically.
- `match_results (job_id, overall_score DESC)` serves the ranking table directly.
- `resume_skills (skill_id)` answers "which candidates have Kafka" for dashboard filters.
- No vector index at prototype scale: an exact scan over a few hundred chunks is fast. Add an HNSW index with `vector_cosine_ops` once chunks reach tens of thousands.
- Matched skills, missing skills and explanations are JSONB because they are always read together and are a snapshot of one scoring run. If the taxonomy changes later, past explanations stay as they were.
- Deletes cascade from `jobs` and `resumes`; the data is synthetic, so hard deletes are fine.

## 5. Parsing pipeline

JDs and resumes share one text extractor and one skill extractor, so a skill is recognised the same way on both sides. Resumes then get extra steps for contact details, experience and education.

### 5.1 Text extraction (shared)

1. **Validate.** Accept `.pdf` and `.docx` (plus `.txt` for JDs). Check magic bytes, not just the extension: PDFs start with `%PDF`, and a DOCX is a ZIP containing `word/document.xml`. Limit files to 5 MB and batches to 50 files.
2. **PDF.** Read text blocks with PyMuPDF. Group blocks into columns by x-position, then sort each column top to bottom, so two-column resumes read correctly. Fall back to pdfplumber if PyMuPDF fails.
3. **DOCX.** Read paragraphs in order, then table cells row by row, then headers and footers, where names and contact lines often sit.
4. **Scanned-PDF check.** If a PDF with pages yields under about 100 characters, mark it `failed` with the reason "Looks like a scanned image; OCR is not enabled".
5. **Clean.** Apply Unicode NFKC (fixes ligatures such as "ﬁ"), turn all bullet symbols into "- ", rejoin words split by a hyphen at a line end, and collapse spaces. Keep line breaks, because section detection needs them.

### 5.2 Skills taxonomy

- A JSON file of about 400–600 skills, each with a canonical name, a category and aliases. Examples: JavaScript {js, ecmascript, es6}, Kubernetes {k8s}, PostgreSQL {postgres, psql}, Spring Boot {springboot, spring-boot}, Machine Learning {ml}.
- Build it by hand from your target JDs, then widen it from openly licensed lists such as the ESCO skills classification.
- Ambiguous short aliases ("Go", "R", "C", "ML") match only when case matches or when they sit inside a Skills section.
- Each canonical skill's embedding is computed once at seed time and stored in `skills.embedding`.

### 5.3 Skill extraction (shared)

1. **Exact and alias pass.** A spaCy PhraseMatcher on lower-cased tokens holds every canonical name and alias and maps each hit to a skill id. Token matching means "Java" never fires inside "JavaScript".
2. **Fuzzy pass.** Comma-separated items and noun chunks in Skills sections are compared with rapidfuzz (`token_sort_ratio` ≥ 90) against all aliases. This catches "Node JS" and "Postgre SQL".
3. **Unmapped terms.** Skill-list items that match nothing are kept as `unmapped`. The UI shows them, and the recruiter can add them to the taxonomy.
4. **Provenance.** Store the section each skill came from and the sentence it appeared in; both feed the explanation later.

### 5.4 JD parsing

1. **Title and seniority.** Use a "Job Title:" label if present, otherwise the first short line. Detect junior, mid, senior, lead or principal.
2. **Sections.** Split into Responsibilities, Requirements (Qualifications, Must have) and Preferred (Nice to have, Bonus).
3. **Required or preferred.** The section decides first. Sentence cues then override: "nice to have", "a plus", "preferred", "familiarity with", "bonus" mean preferred; "must", "required", "strong", "proficient", "minimum" mean required. With no signal, a skill is required.
4. **Experience.** Regex patterns read "5+ years", "3–5 years", "minimum of 4 years" and "at least 2 yrs" into min and max years. When years and a skill share a clause ("4+ years of Java"), store it as that skill's `min_years`. The overall minimum is the largest figure found in a general experience sentence.
5. **Education.** Map degree words to levels: B.E., B.Tech, BS, BSc, Bachelor's → 3; M.Tech, MS, MSc, MBA, Master's → 4; PhD → 5; Diploma → 2. Capture fields such as "Computer Science or related". "Or equivalent experience" marks education as soft, which halves its weight.
6. **Requirement sentences.** Every bullet under Requirements and Responsibilities becomes a `job_requirements` row with its own embedding.
7. **Recruiter review.** The extraction is shown as editable chips. Recruiter edits override the parser and are saved with `added_by = recruiter`.

### 5.5 Resume parsing

1. **Section segmentation.** A line is a header if it has 5 words or fewer, no sentence punctuation, and fuzzy-matches (≥ 85) a header dictionary. Upper case or a trailing colon raises confidence. Text before the first header is the contact block.

   | Section | Header variants |
   | --- | --- |
   | Experience | work experience, professional experience, employment history, career history |
   | Education | education, academics, academic qualifications |
   | Skills | skills, technical skills, core competencies, tech stack |
   | Projects | projects, key projects, academic projects |
   | Certifications | certifications, licenses, courses |
   | Summary | summary, profile, objective, about me |
2. **Contact details.** Email by regex. Phone with `phonenumbers.PhoneNumberMatcher`, default region from config (for example IN). LinkedIn and GitHub URLs by regex. Name = the first line in the contact block with 2–4 title-case words and no digits or "@", confirmed by spaCy PERSON when possible. Location = a spaCy GPE entity in the contact block.
3. **Work experience.** Find date ranges in the Experience section: "Jan 2020 – Present", "January 2020 - Mar 2022", "2019 – 2021", "03/2018 – 06/2020", "Since 2021". Parse each end with dateparser; "Present", "Current", "Now" and "Till date" mean today. Each date range anchors one role. Title and company come from the one or two lines beside the date, split on " at ", "|", "," or a dash. The bullets up to the next date line are the description.
4. **Total experience.** Merge overlapping date ranges, then sum them, so two jobs held at once are not double counted. Career gaps are not penalised. Internships (title contains intern or trainee) are listed but left out of total years by default. With no dates at all, fall back to a phrase such as "6 years of experience" in the summary.
5. **Years per skill.** For each skill, add up the durations of roles whose description mentions it, capped at total experience.
6. **Education.** Match degree patterns in the Education section to a level. Institution = a line containing University, College, Institute or School, or a spaCy ORG. Year = a four-digit 19xx or 20xx. Field = the words after "in" or "of", checked against a list of known fields.
7. **Current title.** The role marked current, or the one with the latest end date.
8. **Chunking.** Split experience, projects and summary into chunks of up to about 120 words along role and bullet boundaries, each tagged with its section. `all-MiniLM-L6-v2` truncates input past 256 word pieces, so short chunks lose nothing. Embed all chunks of a resume in one batched call.
9. **Parse confidence.** The share of six checks passed: name, email, phone, at least 3 skills, at least 1 dated role, at least 1 education entry. Below 0.5 the UI flags the resume for manual review.

## 6. Matching algorithm and scoring methodology

The match % is a weighted average of four component scores, each between 0 and 1, multiplied by 100. Default weights: skills 40%, semantic similarity 30%, relevant experience 20%, education 10%. A component the JD does not specify drops out, and the remaining weights are rescaled.

&#91;embedded content: scoring pipeline · 4 components, 2 outputs\]

Skills and semantic similarity carry 70% of the default score. Experience and education drop out when the JD does not ask for them.

### 6.1 Final score

```latex
\text{Score} = 100 \times \frac{\sum_{i \in A} w_i \, S_i}{\sum_{i \in A} w_i}
```

- A is the set of active components. Experience is inactive when the JD gives no years; education is inactive when it names no degree.
- Default weights: skills 0.40, semantic 0.30, experience 0.20, education 0.10. Recruiters can move them with sliders; they are saved in `jobs.scoring_weights` and copied into `match_results.weights_used` for every run.
- **Why these weights:** skills are the most direct and checkable signal. Semantic similarity catches responsibilities and context that skill lists miss. Years of experience matter but are a weak proxy for ability, so they get less. Education predicts least for most tech roles. The weights are a stated starting point, checked against the labelled sample set (Section 13).
- Ties are broken by required-skill coverage, then relevant experience.

### 6.2 Skill score (40%)

Each JD skill j has weight wⱼ: 1.0 if required, 0.5 if preferred. It earns a credit mⱼ from the first tier that fires:

| Tier | Rule | Credit | Example |
| --- | --- | --- | --- |
| 1. Exact | Same canonical skill id | 1.0 | Java ↔ Java |
| 2. Alias or fuzzy | Resume term maps to the same id through an alias or fuzzy match | 1.0 | k8s ↔ Kubernetes |
| 3. Related | Cosine between the two skill vectors ≥ τ\_rel (start 0.80), same category | 0.5 | MySQL ↔ PostgreSQL |
| 4. Contextual | Skill not listed, but a resume experience or project chunk matches the skill with cosine ≥ τ\_ctx (start 0.55) | 0.5 | Microservices ↔ "split a monolith into 8 independently deployed services" |
| 5. Missing | None of the above | 0 | Goes to the missing-skills list |

```latex
S_{\text{skill}} = \frac{\sum_j w_j \, m_j}{\sum_j w_j}
```

- **Years check.** If the JD sets `min_years` for a skill and the resume shows fewer years of use, the credit is multiplied by max(0.5, years used ÷ years required).
- **False-positive guard.** Tiers 3 and 4 need the same skill category, and a "never equivalent" list blocks known traps: Java / JavaScript, C / C#, React / React Native.
- **Required coverage** = share of required skills with any credit. It is reported separately ("4 of 5 required skills") because recruiters read it first.

### 6.3 Semantic similarity (30%)

Two signals, both from sentence embeddings:

1. **Requirement coverage.** For each JD requirement sentence rᵢ, take its best match among the resume's chunks cₖ. Coverage is the weighted mean of those best matches (required 1.0, preferred 0.5).
2. **Document similarity.** Cosine between the whole-JD vector and the whole-resume vector, where each is the normalised mean of its chunk vectors.

```latex
b_i = \max_k \cos(r_i, c_k), \qquad \text{raw} = 0.7 \cdot \overline{b}_{w} + 0.3 \cdot \cos(\text{JD}, \text{R})
```

```latex
S_{\text{sem}} = \operatorname{clip}\left(\frac{\text{raw} - L}{H - L},\ 0,\ 1\right)
```

- **Why calibrate.** Raw cosine scores from these models sit in a narrow band: unrelated text rarely scores near 0 and strong matches rarely near 1. L and H stretch that band to 0–1. Set L to the average raw score of clearly irrelevant sample resumes and H to that of best-fit ones; start with L = 0.20 and H = 0.70.
- **Why requirement-level, not just whole-document.** A single resume vector averages in hobbies and education, so long resumes get diluted. A best match per requirement shows exactly which resume sentence covers which requirement, which powers the explanation.
- **Keyword stuffing.** A bare skills list matches responsibility sentences poorly, so a stuffed resume scores well on skills but lower here.

### 6.4 Relevant experience (20%)

1. Build a role profile vector from the JD title plus its responsibility sentences.
2. For each work entry, compute the cosine between the role profile and that entry's title and description. Map it to a relevance factor: ≥ 0.55 → 1.0 (relevant), 0.40–0.55 → 0.5 (partly relevant), below 0.40 → 0 (unrelated).
3. Walk the career month by month. Each month counts once, at the highest factor of any role active that month, so overlapping jobs are not double counted.
4. Relevant years Y\_rel = sum of monthly factors ÷ 12. With M = the JD's minimum years:

```latex
S_{\text{exp}} = \min\left(1,\ \frac{Y_{\text{rel}}}{M}\right)
```

Being above a JD's maximum is shown as information but not penalised by default, because over-qualification penalties act as a proxy for age.

### 6.5 Education (10%)

| Candidate's degree level vs required | Score |
| --- | --- |
| Equal or higher | 1.0 |
| One level below | 0.5 |
| Two or more below, or not found | 0.2 (not 0, since the parser may have missed it; flagged in the explanation) |

- **Field of study.** If the JD names fields, a matching field keeps the score; a different field multiplies it by 0.8. Matching uses a small equivalence list (Computer Science ≈ IT ≈ Software Engineering) plus embedding cosine ≥ 0.6.
- **"Or equivalent experience".** Education weight is halved, and a candidate with Y\_rel ≥ M + 2 gets 1.0.

### 6.6 Worked example

The JD is a Backend Java Developer role needing 4+ years and a Bachelor's in Computer Science. Required skills: Java, Spring Boot, PostgreSQL, REST APIs, Microservices. Preferred: Docker, Kafka, AWS. Total skill weight = 5 × 1.0 + 3 × 0.5 = 6.5.

Candidate A (synthetic) has 5.5 years in total, 4.5 of them relevant, and a B.Tech in Computer Science.

| JD skill | Type | Weight | Resume evidence | Tier | Credit | Weight × credit |
| --- | --- | --- | --- | --- | --- | --- |
| Java | Required | 1.0 | Java | Exact | 1.0 | 1.00 |
| Spring Boot | Required | 1.0 | Spring Boot | Exact | 1.0 | 1.00 |
| PostgreSQL | Required | 1.0 | MySQL | Related | 0.5 | 0.50 |
| REST APIs | Required | 1.0 | REST | Alias | 1.0 | 1.00 |
| Microservices | Required | 1.0 | "split a monolith into 8 independently deployed services" | Contextual | 0.5 | 0.50 |
| Docker | Preferred | 0.5 | Docker | Exact | 1.0 | 0.50 |
| Kafka | Preferred | 0.5 | RabbitMQ | Related | 0.5 | 0.25 |
| AWS | Preferred | 0.5 | — | Missing | 0 | 0.00 |
| **Total** |  | **6.5** |  |  |  | **4.75** |

Skill score = 4.75 ÷ 6.5 = 0.731. Semantic: coverage 0.62 and document similarity 0.55 give raw = 0.7 × 0.62 + 0.3 × 0.55 = 0.599, so S\_sem = (0.599 − 0.20) ÷ 0.50 = 0.798. Experience: 4.5 ÷ 4 caps at 1.0. Education: Bachelor's in CS meets the requirement, so 1.0.

Candidate C has Java, PostgreSQL, REST and AWS, 2 relevant years, a Bachelor's in CS and a raw semantic score of 0.45. That gives skills 3.5 ÷ 6.5 = 0.538, semantic 0.50, experience 2 ÷ 4 = 0.50 and education 1.0.

| Component | Weight (points) | A: score | A: points | C: score | C: points |
| --- | --- | --- | --- | --- | --- |
| Skills | 40 | 0.731 | 29.2 | 0.538 | 21.5 |
| Semantic similarity | 30 | 0.798 | 23.9 | 0.500 | 15.0 |
| Relevant experience | 20 | 1.000 | 20.0 | 0.500 | 10.0 |
| Education | 10 | 1.000 | 10.0 | 1.000 | 10.0 |
| **Match %** | **100** |  | **83%** |  | **57%** |

Candidate A loses 16.8 points: 10.8 on skills and 6.1 on semantic similarity. Each skill's lost points = 40 × wⱼ × (1 − mⱼ) ÷ 6.5. That is 3.1 each for PostgreSQL (related only), Microservices (inferred only) and AWS (missing), and 1.5 for Kafka (related only). These numbers become the "why" in the explanation.

### 6.7 Thresholds and calibration

| Parameter | Starting value | How to calibrate |
| --- | --- | --- |
| τ\_rel, related-skill cosine | 0.80 | Inspect nearest neighbours of 50 taxonomy skills; set the cut where pairs stop being the same family |
| τ\_ctx, contextual chunk cosine | 0.55 | Label 40 (skill, chunk) pairs yes or no; choose the threshold with the best F1 |
| L and H, semantic floor and ceiling | 0.20 and 0.70 | Average raw score of irrelevant and of best-fit sample resumes |
| Role relevance cut-offs | 0.55 and 0.40 | Label sample roles relevant, partly relevant or unrelated |
| Partial credit for tiers 3 and 4 | 0.5 | Half credit for indirect evidence; check that rankings stay stable at 0.4 and 0.6 |

Every threshold lives in one scoring config module and is tied to `scoring_version`. Each embedding model has its own similarity range, so switching to `bge-small-en-v1.5` means recalibrating. Inference has no randomness, so the same inputs always produce the same score.

## 7. Explainability

Each scoring component returns its score plus structured evidence, and a template-based generator turns that evidence into the reasons shown to the recruiter. No LLM is involved, so the reasons always agree with the number.

**Evidence item fields:** type (skill match, skill missing, requirement match, experience, education), impact in points (earned or lost), a message, the supporting resume snippet, and the section it came from. The explanation generator sorts items by impact and keeps the top ones.

**What the candidate page shows**

1. **Verdict** from the score band: 80+ strong match, 65–79 good match, 50–64 partial match, below 50 weak match.
2. **Score breakdown:** points earned against points available for each component. The four bars add up to the match % (±1 for rounding).
3. **Top strengths:** the largest positive contributions.
4. **Top gaps:** the largest point losses, each with its point value.
5. **Requirement table:** each JD requirement, the best resume sentence for it, the similarity, and a status (covered ≥ 0.55, partial 0.40–0.55, not covered).
6. **Skill chips** with a tier badge (Exact, Alias, Related, Inferred) and the evidence on hover.
7. **Experience comparison:** required years against total and relevant years, with each role's relevance factor.
8. **Data-quality notes:** parse confidence and anything the parser could not find, such as "Education not found; check the original file".

**Message templates**

| Situation | Template | Example output |
| --- | --- | --- |
| Required coverage | Has {n} of {N} required skills: {list}. | Has 5 of 5 required skills: Java, Spring Boot, REST APIs, PostgreSQL (related), Microservices (inferred). |
| Missing skill | Missing {type} skill {skill} (−{pts} points). | Missing preferred skill AWS (−3.1 points). |
| Related credit | {jd\_skill} credited at half: related skill {resume\_skill} found (−{pts} points). | PostgreSQL credited at half: related skill MySQL found (−3.1 points). |
| Contextual credit | {jd\_skill} not listed, but experience says "{snippet}". | Microservices not listed, but experience says "split a monolith into 8 independently deployed services". |
| Requirement covered | Strong match to "{requirement}" ({sim}). | Strong match to "Design and build scalable backend services" (0.71). |
| Experience met | {y\_rel} years of relevant experience meets the {M}-year minimum. | 4.5 years of relevant experience meets the 4-year minimum. |
| Experience short | {y\_rel} of the {M} required years of relevant experience (−{pts} points). | 2.0 of the 4 required years of relevant experience (−10.0 points). |
| Education met | {degree} in {field} meets the {required} requirement. | B.Tech in Computer Science meets the Bachelor's requirement. |

**Optional AI summary (stretch).** Send only the structured result — skills, component scores, years, no name or contact details — to an LLM for a two-sentence summary. Label it "AI-generated summary". It never changes the score.

## 8. API design

A REST API under `/api/v1` with 16 endpoints covers the whole flow. FastAPI generates Swagger docs at `/docs`, which doubles as a demo of the backend.

| Method | Path | Purpose | Request | Response |
| --- | --- | --- | --- | --- |
| POST | `/jobs` | Create a job from pasted JD text | JSON: title (optional), text | 201: job with extracted requirements |
| POST | `/jobs/upload` | Create a job from a JD file | Multipart: one PDF, DOCX or TXT file | 201: same as above |
| GET | `/jobs` | List jobs | `limit`, `offset` | 200: jobs with resume counts and top score |
| GET | `/jobs/{job_id}` | One job with its requirements | — | 200 |
| PATCH | `/jobs/{job_id}/requirements` | Save recruiter edits to skills, years, degree | Skills (id or name, required or preferred, min years), min years, degree level, fields | 200; marks existing scores stale |
| PATCH | `/jobs/{job_id}/weights` | Save scoring weights | skills, semantic, experience, education (≥ 0, sum > 0) | 200; totals recomputed |
| POST | `/jobs/{job_id}/resumes` | Batch upload | Multipart: `files[]`, 1–50 files | 202: batch id, accepted files, rejected files with reasons |
| GET | `/batches/{batch_id}` | Batch progress | — | 200: status, counts, each file's parse status and error |
| POST | `/jobs/{job_id}/match` | Re-score all parsed resumes | Optional weights | 200: number scored |
| GET | `/jobs/{job_id}/rankings` | Dashboard rows | `min_score`, `skill`, `search`, `sort` | 200: rank, name, title, total and relevant years, match %, top matched skills, missing-required count |
| GET | `/jobs/{job_id}/candidates/{resume_id}` | Full candidate analysis | — | 200: candidate details, component scores, matched and missing skills, requirement matches, experience comparison, explanation |
| GET | `/resumes/{resume_id}/file` | Original file for side-by-side viewing | — | File stream |
| GET | `/jobs/{job_id}/rankings/export` | Rankings as CSV | — | `text/csv` |
| GET | `/skills` | Taxonomy autocomplete for the chip editor | `q` | 200: matching skills |
| DELETE | `/jobs/{job_id}` | Delete a job and its data | — | 204 |
| GET | `/health` | Liveness, database and model readiness | — | 200, or 503 while the model loads |

**Errors** share one shape: an `error` object with `code`, `message` and `details`. Status codes: 400 bad input, 404 not found, 409 duplicate file in a batch or a scoring run already in progress, 413 file over 5 MB, 415 unsupported type, 422 validation failure, 503 model not ready.

**Design notes**

- A bad file never fails the batch. It is rejected at upload or marked `failed` during parsing, with a reason the UI shows.
- Changing weights needs no new NLP work, because component scores are stored. The UI previews the new ranking instantly from those stored scores, then `PATCH /weights` saves it.
- Changing requirements re-runs skill matching and embeds only the new requirement sentences; resume embeddings are reused.
- Writes to `match_results` are upserts on `(job_id, resume_id)`, so re-running a score is safe.
- CORS allows only the frontend origin. Uploaded files are stored under UUID names and never served from a user-supplied path.

## 9. Frontend and UX

The UI is a three-step wizard (Job → Resumes → Results) plus a candidate detail page. A recruiter goes from pasted JD to ranked shortlist without leaving the flow.

| Screen | What the recruiter sees and does |
| --- | --- |
| Jobs home | List of jobs with created date, resume count and top score; "New job" button; "Load sample data" button for demos |
| Step 1: Job description | Paste or Upload tabs. "Extract requirements" fills a review panel: title, seniority, minimum years, degree, fields, and skill chips in Required and Preferred columns. Click a chip to move it between columns, × to remove it, "+ Add skill" with autocomplete. Unmapped terms appear with an "Add to taxonomy" action |
| Step 2: Upload resumes | Drop zone for PDF and DOCX (up to 50 files, 5 MB each) with checks before upload. After upload, each file shows queued → parsing → parsed or failed with its reason, under a "9 of 12 parsed" progress bar. Moves on when done |
| Step 3: Ranking dashboard | Summary cards: resumes processed, average match, top match, number meeting all required skills. Table: rank, candidate (name and current title), experience (total, with relevant below), match % (bar, number and verdict word), matched skills (first 4 chips + "+N"), missing-required count, parse quality. Toolbar: search, minimum-score filter, skill filter, weight sliders with live re-ranking, CSV export |
| Candidate detail | Header with name, title, contact, links and parse-confidence badge. Score gauge with verdict and breakdown bars. Tabs: Overview (strengths and gaps), Skills (matched chips with tier badges; missing required and preferred), Experience (required vs total vs relevant; role list with relevance), Requirements (requirement-to-evidence table), Education, Resume (extracted text with matched terms highlighted; link to the original). Previous and Next buttons move through the ranking |

**UX rules**

- Colour is never the only signal: every score shows its verdict word too, and missing skills carry an icon as well as red.
- Skeleton loaders while loading, empty states with a clear next action, toast messages for errors.
- Weight sliders re-rank instantly from stored component scores; "Save" persists them and "Reset" restores defaults.
- The table works with the keyboard, and the layout holds down to tablet width.

**Component map**

- Pages: `JobsPage`, `NewJobPage`, `UploadPage`, `RankingsPage`, `CandidatePage`
- Job input: `JdInput`, `RequirementChips`, `SkillAutocomplete`
- Upload: `FileDropzone`, `BatchStatusList`
- Dashboard: `SummaryCards`, `RankingTable`, `ScoreBar`, `SkillChips`, `WeightSliders`
- Candidate: `ScoreGauge`, `ScoreBreakdown`, `ExplanationList`, `RequirementMatchTable`, `ExperienceComparison`, `ResumeTextViewer`
- Data layer: one API client plus TanStack Query hooks. TypeScript types are generated from the FastAPI OpenAPI schema with `openapi-typescript`, so frontend and backend never drift apart.

## 10. Synthetic test data plan

A script generates 3 JDs and 15 synthetic resumes, each paired with a ground-truth file, so parsing accuracy and ranking quality can be measured. No real person's data is used anywhere.

**JDs:** Backend Java Developer (main demo), Data Scientist (Python, ML), Frontend React Developer.

**Resume personas, scored against the Backend Java JD**

| # | Persona | What it tests | Format | Expected tier |
| --- | --- | --- | --- | --- |
| 1 | Senior Java backend engineer with every required skill plus Docker and Kafka | Top of the ranking | PDF, one column | Strong |
| 2 | Strong Java developer who writes "Postgres", "k8s", "RESTful services" | Alias and semantic matching | DOCX | Strong |
| 3 | Java developer with MySQL and RabbitMQ (Candidate A in Section 6.6) | Related-skill credit | PDF, two columns | Strong |
| 4 | Junior Java developer, 2 years (Candidate C) | Experience shortfall | DOCX | Partial |
| 5 | Python/Django backend developer, 6 years | Transferable but different stack | PDF | Partial |
| 6 | Full-stack JavaScript developer (Node, React) | Java vs JavaScript guard | DOCX | Weak |
| 7 | Keyword stuffer: 60-item skills list, thin experience | Semantic component resists stuffing | PDF | Partial |
| 8 | QA automation engineer moving to backend: 5 years total, 1.5 relevant | Relevance-weighted experience | DOCX | Partial |
| 9 | Freelance and full-time roles at the same time | Overlap merging | PDF | Strong |
| 10 | No dates, "7 years of experience" in the summary | Fallback experience logic | DOCX | Partial |
| 11 | Strong skills, diploma only | Education scoring | PDF | Good |
| 12 | Data scientist | Low for Java JD, high for the Data Scientist JD | PDF | Weak |
| 13 | Accountant | Sets the semantic floor L | DOCX | Weak |
| 14 | Resume built entirely from Word tables | DOCX table extraction | DOCX | Partial |
| 15 | Image-only (scanned) PDF | Graceful failure message | PDF | Failed |

**How to generate them**

1. Write each persona's content as a structured JSON or YAML file: contact details, summary, roles with dates and bullets, skills, education.
2. A script in `scripts/` renders each persona into DOCX (python-docx) and PDF (HTML templates to PDF) in three layouts: one column, two columns, tables.
3. Names come from Faker; emails use `example.com`; phone numbers use fictional ranges; employers are invented ("Acme Fintech").
4. The scanned case is a rendered page image wrapped in a PDF.
5. The script also writes `ground_truth.json`: expected name, email, phone, skills, roles with dates, total months, degree level and expected tier per JD.
6. Commit everything to `sample_data/` and state in the README that all data is synthetic.

Public resume datasets often carry unclear licences or real personal data, so stick to generated data.

## 11. Repository structure

One monorepo with `backend/`, `frontend/`, sample data, scripts and docs. Dependencies point one way: routers → services → repositories → models.

```text
resume-matcher/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app; lifespan hook loads spaCy and the embedding model once
│   │   ├── core/                   config, logging, database session, error handlers
│   │   ├── models/                 SQLAlchemy ORM models
│   │   ├── schemas/                Pydantic request and response models
│   │   ├── api/v1/                 jobs, resumes, batches, matching, skills, health routers
│   │   ├── repositories/           database reads and writes per aggregate
│   │   ├── services/
│   │   │   ├── extraction/         validator, pdf, docx, cleaner
│   │   │   ├── parsing/            sections, contact, skills, experience, education, jd_parser, resume_parser, chunker
│   │   │   ├── nlp/                embedder, spacy_pipeline, taxonomy
│   │   │   ├── matching/           skill_matcher, semantic, experience, education, scorer, explainer, scoring_config
│   │   │   └── pipeline.py         batch orchestration: parse → embed → score
│   │   └── data/skills_taxonomy.json
│   ├── alembic/                    migrations
│   ├── tests/                      unit/, integration/, fixtures/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/                        api/, components/, pages/, hooks/, types/, lib/
│   ├── package.json
│   └── Dockerfile
├── sample_data/                    jds/, personas/, resumes/, ground_truth.json
├── scripts/                        generate_samples, seed_skills, evaluate_parsing, evaluate_ranking
├── docs/                           architecture.md, matching-algorithm.md, database.md, images/
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Makefile
├── .env.example
└── README.md
```

- Parsers and scorers are pure functions over plain data classes, with no database or HTTP inside. They can be unit-tested in milliseconds.
- Models load once in the lifespan hook and are shared through FastAPI dependency injection.
- `scoring_config` holds every weight and threshold from Section 6.7 in one place.
- The Docker image downloads the embedding model at build time, so the first request is not slow and the demo works offline.

## 12. 3-day implementation plan with sequential commits

The build takes 42 commits over 3 days. Day 1 ends with every sample resume parsed into Postgres, Day 2 with rankings served by the API, and Day 3 with the full flow in the browser, plus docs and a demo video.

&#91;embedded content: 3-day roadmap · 3 phases, 3 tagged checkpoints\]

If a day overruns, cut from the list at the end of this section rather than moving a checkpoint.

### Git workflow

- Use Conventional Commits (`feat`, `fix`, `test`, `docs`, `chore`, `ci`) with a scope, e.g. `feat(parse): ...`.
- Open one GitHub Issue per module and reference it in commits ("Closes #4"), so the Issues tab mirrors the plan.
- Work on a branch per day (`day1/parsing`, `day2/matching`, `day3/frontend`). Merge each with a pull request using a merge commit, not squash, so every commit stays visible on `main`.
- Tag each checkpoint: `v0.1.0`, `v0.2.0`, `v1.0.0`. Commit as you go, so the timestamps tell the real story.

### Day 1 — Foundation, database and parsing

Goal: all 15 sample files go through the parser from the command line and land in Postgres.

| # | Commit message | What goes in | Done when |
| --- | --- | --- | --- |
| 1 | `chore: initialize monorepo with README, .gitignore, LICENSE, .env.example` | Folder layout, README skeleton | Repo is on GitHub |
| 2 | `chore(backend): scaffold FastAPI app with config and health endpoint` | pyproject, ruff, settings, `main.py` | `/health` returns 200 |
| 3 | `chore: add docker-compose with Postgres 16 and pgvector` | Database service, volume, Makefile targets | `CREATE EXTENSION vector` works |
| 4 | `feat(db): add job, skill and requirement models with first migration` | jobs, skills, job\_skills, job\_requirements, enums | `alembic upgrade head` succeeds |
| 5 | `feat(db): add resume, candidate, experience, education, chunk and match models` | Remaining 8 tables, constraints, indexes | Migration upgrades and downgrades cleanly |
| 6 | `feat(nlp): add skills taxonomy and seed script` | `skills_taxonomy.json`, seed script | skills table populated |
| 7 | `feat(data): add synthetic personas, sample generator and ground truth` | 3 JDs, 15 personas rendered to PDF and DOCX | 15 files plus `ground_truth.json` in `sample_data/` |
| 8 | `feat(extract): add file validation and PDF/DOCX text extraction` | Validator, column-aware PDF reader, DOCX tables, cleaner, scanned check | Text comes out of all 14 text-based samples |
| 9 | `feat(parse): add resume section segmentation` | Header dictionary, fuzzy header detection | Sections correct on samples |
| 10 | `feat(parse): extract contact details` | Email, phone, links, name, location | Name and email right on samples |
| 11 | `feat(parse): extract skills with PhraseMatcher, aliases and fuzzy matching` | spaCy pipeline, skill extractor with provenance | Skill recall checked against ground truth |
| 12 | `feat(parse): parse work history and merge overlapping dates` | Date patterns, dateparser, interval merge, years per skill | Persona 9 is not double counted |
| 13 | `feat(parse): extract education and map degree levels` | Degree patterns, institution, year | Levels right on samples |
| 14 | `feat(parse): parse JD requirements, years and degree` | JD parser with required and preferred cues | Java JD extraction matches expectations |
| 15 | `test(parse): add unit tests for dates, sections, skills and JD parsing` | pytest fixtures | `pytest` passes |
| 16 | `feat(scripts): add parsing accuracy evaluation against ground truth` | Script prints a markdown accuracy table | First accuracy numbers recorded |

Checkpoint: tag `v0.1.0`.

### Day 2 — Embeddings, matching engine and API

Goal: upload the 15 samples through Swagger and get a sensible ranking for the Java JD.

| # | Commit message | What goes in | Done when |
| --- | --- | --- | --- |
| 17 | `feat(nlp): add embedding service loaded once at startup` | sentence-transformers wrapper, batched and normalised encoding, model name from env | Model loads once; `/health` reports it ready |
| 18 | `feat(parse): chunk resumes and JD requirements and store embeddings` | Chunker, pgvector columns filled | Every parsed resume has chunks with vectors |
| 19 | `feat(api): add job endpoints for paste, upload and requirement edits` | Create, upload, get and patch job routes | JD round-trips through Swagger |
| 20 | `feat(api): add batch resume upload with background parsing` | Upload route, `pipeline.py`, status updates | 15 files accepted, 14 parsed, 1 failed with a reason |
| 21 | `feat(api): add batch status endpoint` | Batch progress route | Counts and per-file statuses are correct |
| 22 | `feat(match): add tiered skill matcher` | Exact, alias, related and contextual tiers; guard list; years check | Candidate A's skill table matches Section 6.6 |
| 23 | `feat(match): add semantic requirement coverage with calibration` | Per-requirement best match, document similarity, L/H scaling | Irrelevant samples land near 0 |
| 24 | `feat(match): add relevance-weighted experience scorer` | Role relevance, month-by-month walk | Persona 8 gets about 1.5 relevant years |
| 25 | `feat(match): add education scorer` | Level and field rules | Persona 11 scores 0.5 on education |
| 26 | `feat(match): combine components with weight renormalisation` | Final scorer, scoring version, tie-breaks | Scores stay within 0–100; inactive components drop out |
| 27 | `feat(match): generate explanations with points lost and evidence` | Explainer and templates | Points add up to the match % |
| 28 | `feat(api): add match, rankings, candidate detail, weights and export endpoints` | Remaining routes | Rankings returned in score order |
| 29 | `test(match): add scorer unit tests and an end-to-end ranking test` | Unit and integration tests | Expected strong personas rank in the top 4 |
| 30 | `chore(match): calibrate thresholds on sample data and record results` | Ranking evaluation script, updated config | Results table saved in `docs/` |

Checkpoint: tag `v0.2.0`.

### Day 3 — Frontend, packaging, docs and demo

Goal: a recruiter can run the whole flow in the browser, and the repo explains itself.

| # | Commit message | What goes in | Done when |
| --- | --- | --- | --- |
| 31 | `chore(frontend): scaffold React, Vite, TypeScript, Tailwind and shadcn/ui` | Router, layout, API client, generated types | App shell loads and calls `/health` |
| 32 | `feat(ui): add job page with JD input and editable requirement chips` | Paste and upload tabs, chip editor, autocomplete | Edits save through `PATCH` |
| 33 | `feat(ui): add batch upload with drop zone and live parse status` | Drop zone, status list, polling | Status updates without a page refresh |
| 34 | `feat(ui): add ranking dashboard with sorting, filters and score bars` | Summary cards, ranking table | Table matches the API ranking |
| 35 | `feat(ui): add candidate detail page with breakdown, skills, experience and reasons` | Gauge, breakdown, tabs, requirement table | Every item in Module 5 is visible |
| 36 | `feat(ui): add weight sliders with live re-ranking and CSV export` | Slider panel, export button | Order changes instantly; CSV downloads |
| 37 | `feat(ui): add loading, empty and error states and a sample-data button` | Skeletons, toasts, empty states | Failed files show their reason |
| 38 | `chore: dockerize backend and frontend for one-command startup` | Dockerfiles, compose services, model baked into image | `docker compose up` runs everything |
| 39 | `ci: add GitHub Actions for lint and tests` | Workflow, README badge | CI passes on `main` |
| 40 | `docs: write README with architecture, setup, ER diagram and API overview` | README, Mermaid ER diagram | A fresh clone runs by following it |
| 41 | `docs: add matching algorithm and scoring methodology write-up` | `docs/matching-algorithm.md` | Worked example included |
| 42 | `docs: add screenshots, accuracy results and demo video link` | Images, results tables, video link | README shows the app at a glance |

Checkpoint: tag `v1.0.0` and record the demo.

**If you fall behind, cut in this order:** CSV export → weight sliders → skill filter → education field matching → contextual skill tier. Never cut the candidate detail page, the explanations or the README; they map straight onto Module 5, the explanation criterion (15%) and the documentation criterion (10%).

## 13. Testing and evaluation

Unit tests cover the pure parsing and scoring functions, one integration test covers the full flow, and two scripts measure parsing accuracy and ranking quality for the README. Measured numbers are the strongest answer to the 15% parsing-accuracy criterion.

**Unit tests**

- Dates: at least 12 formats, including "Present", "Since 2021", "03/2018" and ranges written with an en dash.
- Interval merging: overlapping, nested, back-to-back and gapped roles.
- Sections: upper-case headers, headers with colons, two-column layouts.
- Skills: aliases (k8s), fuzzy variants (Node JS), the Java/JavaScript guard, short ambiguous aliases.
- JD parser: required vs preferred cues, "3–5 years", "5+ years of Java".
- Scorer: weights rescale when a component is inactive; output stays within 0–100; points add up to the total.

**Integration test.** Using FastAPI's TestClient and a pgvector Postgres container: create the Java job, upload all 15 samples, poll until done, fetch rankings. Assert that persona 15 failed with a reason, the strong personas fill the top 4, and persona 13 ranks last.

**Parsing accuracy against ground truth**

| Field | Metric | Target |
| --- | --- | --- |
| Name | Exact match after normalising case and spaces | ≥ 90% |
| Email | Exact match | ≥ 98% |
| Phone | Match after E.164 normalisation | ≥ 95% |
| Skills | Precision, recall and F1 | F1 ≥ 0.85 |
| Total experience | Mean absolute error | ≤ 6 months |
| Degree level | Accuracy | ≥ 90% |
| Sections | Share of sections found | ≥ 90% |

These are goals; publish the measured values in the README, including the misses.

**Ranking quality**

- Spearman correlation between match % and expected tier (strong 3, partial 2, weak 1). Goal: 0.8 or higher.
- Precision at 4: how many of the top 4 are the strong personas.
- **Keyword-only ablation.** Run again with semantic weight 0 and skill tiers 3–4 switched off. Persona 2 (synonyms) should fall and persona 7 (keyword stuffer) should rise. A README table of both rankings proves the system matches on meaning, not only keywords.
- **Weight sensitivity.** Move each weight by ±0.1; the top 3 should stay the same.
- **Speed.** Time a 15-resume batch end to end on your laptop CPU and report it.

**CI.** One GitHub Actions workflow with two jobs. Backend: ruff, then pytest against a `pgvector/pgvector:pg16` service container. Frontend: ESLint, `tsc --noEmit`, Vitest, then a production build.

## 14. README, demo video and interview preparation

The README should let a reviewer run the app in 5 minutes and understand the scoring in 2. The demo video should show the full flow and one score explained point by point.

### README outline

1. Title, one-line pitch, CI badge, demo GIF.
2. Demo video link.
3. Features, mapped to Modules 1–5 of the brief.
4. Architecture diagram with one paragraph of explanation.
5. Tech stack table with a "why" column.
6. Quick start: install Docker, copy `.env.example` to `.env`, run `docker compose up --build`, open the app, click "Load sample data".
7. Local development without Docker.
8. How matching works: the formula, the four components, a link to `docs/matching-algorithm.md`.
9. ER diagram as a Mermaid `erDiagram` block, which GitHub renders natively.
10. API overview, with a link to Swagger at `/docs`.
11. Results: parsing accuracy, ranking quality, the keyword-only ablation, batch timing.
12. Project structure.
13. How to run tests.
14. Limitations and future work.
15. Data and ethics: synthetic data only, protected attributes never scored, a human makes the decision.
16. License.

### Demo video script (about 7 minutes)

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:30 | Title screen | Screening resumes by hand is slow; this ranks a batch and explains each score |
| 0:30–1:15 | Architecture diagram | React → FastAPI → parsing, embeddings, matching → Postgres with pgvector |
| 1:15–2:15 | Paste the Java JD and extract | How required and preferred skills are detected; edit one chip live |
| 2:15–3:00 | Upload 15 resumes | Live statuses; the scanned PDF fails with a clear reason |
| 3:00–3:45 | Ranking dashboard | Sort, filter by skill, read the top candidates |
| 3:45–5:00 | Candidate A detail | 83 = 29.2 + 23.9 + 20 + 10; MySQL earns related credit; microservices inferred from experience |
| 5:00–5:30 | Weight sliders | Raise the experience weight and watch the order change |
| 5:30–6:15 | README results | Accuracy table and the keyword-only ablation |
| 6:15–6:45 | Code tour | Scorer module, tests, CI run |
| 6:45–7:00 | Wrap-up | Limitations and next steps |

Record at 1080p with OBS Studio or Loom, upload as an unlisted YouTube video, and link it in the README.

### Questions to be ready for

| Question | Short answer |
| --- | --- |
| How is the percentage calculated? | Weighted average of four component scores times 100; walk through the worked example in Section 6.6 |
| Why these weights? | Ordered by how directly each signal shows fit; configurable; checked with rank correlation on labelled samples and a ±0.1 sensitivity test |
| Where is the AI? | Sentence embeddings for requirement coverage, related skills, skills inferred from experience and role relevance; spaCy NER for names, organisations and dates |
| Why not compare whole documents only? | One vector per resume dilutes the signal and cannot say which requirement is met; whole-document similarity is kept as 30% of the semantic part |
| Why not ask an LLM for the score? | Scores can change between runs, cost money, are hard to justify and send personal data out; an LLM is optional and only writes a summary |
| How are synonyms handled? | Aliases, fuzzy matching and embeddings (tiers 2–4) |
| How do you stop Java matching JavaScript? | Token-level matching, same-category rule, never-equivalent list, calibrated thresholds |
| What about keyword stuffing? | Semantic coverage needs evidence in experience sentences, which a bare skills list lacks; the ablation table shows it |
| How is experience computed? | Date ranges → merged overlaps → month-by-month relevance → relevant years against the JD minimum |
| What breaks parsing? | Scanned PDFs, unusual layouts, missing dates; parse confidence flags these and the recruiter can read the extracted text |
| How would it scale? | Embeddings are precomputed; add an HNSW index; move background tasks to Celery or RQ; encode on a GPU |
| Is it fair? | Name, gender, age, photo and location are never scored; no penalty for gaps or over-qualification; the recruiter decides |

## 15. Risks, edge cases and stretch goals

The biggest risks are messy PDF layouts and running out of time on Day 3. Both have a planned fallback.

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Two-column PDF read in the wrong order | Wrong sections, missed roles | Column-aware block sorting; a two-column sample in the tests |
| Scanned PDF | No text extracted | Detect it and fail with a clear reason; OCR as a stretch goal |
| Ambiguous or missing dates (03/04/2020, no dates) | Wrong years of experience | Prefer month-and-year formats; fall back to stated years; lower parse confidence |
| Gaps in the skills taxonomy | Skills missed | Show unmapped terms; let the recruiter add skills; embeddings catch near matches |
| Semantic false positives | Inflated scores | Same-category rule, never-equivalent list, calibrated thresholds |
| Model download inside Docker | Slow first start; offline demo fails | Download the model at image build time |
| Memory limits on free hosting | Live demo crashes | PyTorch plus the model need several hundred MB of RAM; check the host's limit, or demo locally with the recorded video as backup |
| Frontend overruns on Day 3 | Unfinished UI | Follow the cut list in Section 12; build from shadcn/ui components |
| The same file uploaded twice | Duplicate rows | SHA-256 unique per batch; return 409 with a message |
| Bias in rankings | Unfair shortlists | Protected attributes never scored; no gap or over-qualification penalty; the recruiter decides |

**Stretch goals, roughly in order of value**

1. Evidence weighting: a skill shown in experience counts more than one only listed.
2. Recency: skills used in recent roles count more.
3. Cross-encoder re-ranking of requirement–evidence pairs for sharper semantic scores.
4. OCR with Tesseract for scanned PDFs.
5. Side-by-side comparison of two or three candidates.
6. An LLM-written two-line summary from structured results only.
7. Server-sent events instead of polling.
8. Recruiter feedback (thumbs up or down) used to tune weights.
9. Login and per-recruiter workspaces.
10. Hosting: frontend on Vercel or Netlify, backend container on Render, Railway or Fly.io, Postgres on Neon or Supabase (both offer pgvector).
