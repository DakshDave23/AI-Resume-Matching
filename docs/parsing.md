# Parsing resumes and job descriptions

How the backend turns an uploaded file into structured data: text extraction, sections, contact details, skills, work history, education, the JD parser, and the vectors stored for matching. Accuracy on the samples is in [parsing-accuracy.md](parsing-accuracy.md); scoring is described in the main [README](../README.md#how-matching-works).

The code is in [`backend/app/services/extraction/`](../backend/app/services/extraction/) and [`backend/app/services/parsing/`](../backend/app/services/parsing/). Every rule below has unit tests in [`backend/tests/unit/`](../backend/tests/unit/).

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
