# Matching algorithm and scoring methodology

How a parsed resume becomes a 0–100 match score against a job description, how each point is explained, and how every threshold was measured. Scoring version **v1.0**, embedding model `sentence-transformers/all-MiniLM-L6-v2`.

The rules:

- **Deterministic.** The same resume, JD and weights always give the same score. No randomness, no LLM.
- **Explainable.** Every point earned or lost comes from a rule and points at the resume text behind it.
- **Measured.** Every threshold was set by measuring the samples with this model, and the measurements are written next to the value in [`scoring_config.py`](../backend/app/services/matching/scoring_config.py).
- **Fair by construction.** Name, gender, age, photo and location are never inputs. Career gaps and over-qualification are never penalised.

The code is in [`backend/app/services/matching/`](../backend/app/services/matching/): one module per component, `scorer.py` to combine them, `explainer.py` for the reasons. How resumes and JDs are parsed into the inputs is in [parsing.md](parsing.md).

## Contents

1. [The score](#1-the-score)
2. [When scoring runs](#2-when-scoring-runs)
3. [Skills](#3-skills)
4. [Semantic similarity](#4-semantic-similarity)
5. [Relevant experience](#5-relevant-experience)
6. [Education](#6-education)
7. [From score to explanation](#7-from-score-to-explanation)
8. [Worked example: Candidate A and the Backend Java JD](#8-worked-example-candidate-a-and-the-backend-java-jd)
9. [Every sample against the Java JD](#9-every-sample-against-the-java-jd)
10. [Calibration](#10-calibration)
11. [Configuration reference](#11-configuration-reference)

## 1. The score

```
Score = 100 × Σ(wᵢ · Sᵢ) / Σ(wᵢ)        over the active components i
```

| Component | Sᵢ (0–1) measures | Default wᵢ |
| --- | --- | --- |
| Skills | The JD's skills found in the resume, directly or indirectly | 0.40 |
| Semantic similarity | How well the resume's passages cover the JD's requirement sentences | 0.30 |
| Relevant experience | Years in roles relevant to this job, against the JD's minimum | 0.20 |
| Education | The highest degree and its field, against the JD's | 0.10 |

- **Active components.** A component the JD gives nothing to score on drops out, and the others are rescaled so the weights still sum to 1. Experience drops out without a minimum number of years, education without a degree, skills without skills, semantic without requirement sentences. With no years and no degree, skills and semantic count 0.57 and 0.43.
- **"Or equivalent experience"** in the JD halves education's weight before rescaling.
- **Weights are relative.** The recruiter's sliders need not sum to anything; only their shares matter. Each result stores the weights it used.
- **Ties** are broken by required-skill coverage, then relevant experience, then a fixed id, so the order never depends on chance.

## 2. When scoring runs

- **After parsing.** Each resume is scored against its job right after it is parsed, in the same transaction that marks it parsed, so a finished batch is fully scored and ranked. Scoring runs in its own savepoint: a scoring bug never undoes a good parse.
- **Stored, not recomputed.** Component scores, matched and missing skills, the requirement table and the explanation are stored on `match_results`, with the weights and `scoring_version`. Pages only read them.
- **Rescoring** (`POST /match`, or saving new weights) recomputes every parsed resume of the job from the stored passages and vectors; no resume is parsed or embedded again. Results are upserted on (job, resume), and ranks are reassigned in SQL over the whole job.
- **Stale scores.** Editing the JD's requirements marks the job's results stale; the dashboard offers "Re-score now".
- **Weights preview.** Because the four component scores are stored, the browser can re-rank instantly under new weights with the formula above (`frontend/src/lib/weights.ts`). Saving runs the same computation on the server.

## 3. Skills

Each JD skill *j* has a weight wⱼ (1.0 if required, 0.5 if preferred) and earns a credit mⱼ from the first tier that fires:

| Tier | Rule | Credit mⱼ |
| --- | --- | --- |
| Exact | The resume has the skill under its canonical name | 1.0 |
| Alias | The same skill under an alias or a fuzzy variant (`k8s`, `Postgress SQL`) | 1.0 |
| Related | The best resume skill of the **same category** has cosine ≥ **0.58** with it (each skill embedded as "Name (category)") | 0.5 |
| Contextual ("Inferred") | Not listed, but an experience or project passage has cosine ≥ **0.43** with the skill's name | 0.5 |
| Missing | None of the above | 0 |

```
S_skill = Σ wⱼ · mⱼ / Σ wⱼ
```

- **Years check.** When the JD asks for "5+ years of Java" and the resume's roles mentioning Java add up to fewer years, the credit is multiplied by max(0.5, years used ÷ years required).
- **Never equivalent.** Java/JavaScript, C/C#, C/C++ and React/React Native look alike to an embedding model but are different skills. They never earn related credit for each other, and a passage naming the other one never counts as context.
- **Custom skills** added by the recruiter are in no extractor dictionary, so their names are looked up in the resume text directly.
- **Why the skills list alone isn't enough.** Listing a skill earns the exact tier, but the semantic and experience components only reward described work. A keyword-stuffed skills section scores well on skills and poorly on everything else (sample 7 in [section 9](#9-every-sample-against-the-java-jd)).

## 4. Semantic similarity

The JD's requirement sentences (responsibilities, requirements, preferred) are compared with the resume's passages: each role with its bullets, each project, and the summary. The skills section is not a passage, so a bare list of names can't pass for described experience.

```
bestᵢ    = max over passages p of cos(requirementᵢ, p)
coverage = Σ wᵢ · bestᵢ / Σ wᵢ                     (required 1.0, preferred 0.5)
raw      = 0.7 × coverage + 0.3 × cos(whole JD, whole resume)
S_sem    = clip((raw − 0.30) / (0.47 − 0.30), 0, 1)
```

- **Whole-document vectors** are the normalised mean of the JD's requirement vectors and of the resume's passage vectors.
- **Years and degree sentences are left out.** "4+ years of professional experience" matches any summary that states years: it scores 0.40 against the accountant's. Those sentences are scored by the experience and education components instead.
- **Calibration (L = 0.30, H = 0.47).** Raw cosines from this model sit in a narrow band. L is the mean raw score of the "weak" sample/JD pairs (0.295, n = 28) and H that of the "strong" pairs (0.473, n = 6). Below L scores 0, above H scores 1, and the band between is linear. This makes the component a strong relevant/irrelevant separator; skills and experience do the fine ranking.
- **Requirement table.** Each requirement keeps its best passage, the cosine and a status: **covered** ≥ 0.40, **partial** 0.30–0.40, **not covered** below 0.30. (A strong candidate's median best match is 0.40; the accountant's is 0.21.)

## 5. Relevant experience

Total years can mislead: a QA engineer with 5 years who moved to backend work 18 months ago has 1.5 years of backend experience.

1. **Role profile.** The JD's title and responsibility sentences, embedded as one text.
2. **Each role** (title and bullets) is compared with the profile:

   | Cosine | Factor | Meaning |
   | --- | --- | --- |
   | ≥ 0.55 | 1.0 | relevant |
   | 0.42–0.55 | 0.5 | partly relevant |
   | < 0.42 | 0 | not relevant |

3. **Month by month,** each month counts once, at the highest factor of any role held that month, so overlapping jobs are never counted twice. Internships are listed but not counted.
4. **Score:** Y_rel = Σ monthly factors ÷ 12, and S_exp = min(1, Y_rel ÷ the JD's minimum).

- A resume with no dated roles uses a stated total ("7 years of experience") times the best role's factor.
- Experience above the JD's maximum is shown as a note but **never penalised**: such a penalty works as a proxy for age.

## 6. Education

| Highest degree vs the JD's | Level score |
| --- | --- |
| Equal or higher | 1.0 |
| One level below | 0.5 |
| Two or more below, or none found | 0.2 (not 0: the parser may have missed it) |

Levels: high school 1, diploma 2, bachelor's 3, master's 4, doctorate 5.

- **Field of study.** When the JD names fields and none of the candidate's degrees is in one, the score is multiplied by 0.8. Fields are the same when they share an equivalence group (Computer Science ≈ IT ≈ Computer Engineering ≈ Computer Applications …; Electronics ≈ Electrical; Mathematics ≈ Statistics; Commerce ≈ Accounting ≈ Finance), or their names have cosine ≥ 0.6. A degree with no field written is not penalised.
- **"Or equivalent experience."** Education's weight is halved, and relevant years ≥ the JD's minimum + 2 stand in for the degree (score 1.0).

## 7. From score to explanation

The explanation is built from the same numbers by fixed templates ([`explainer.py`](../backend/app/services/matching/explainer.py)), so it always agrees with the score.

- **Verdict:** 80+ strong, 65–79 good, 50–64 partial, below 50 weak. The UI always shows the word next to the colour.
- **Breakdown.** Each active component has points available = 100 × its effective weight, split into earned = available × Sᵢ and lost = available − earned. The earned points add up to the match % **as displayed**: rounding uses the largest-remainder method, so the parts never sum to 89.1 when the total says 89.2.
- **Skill items.** Skill *j* earns available_skills × wⱼ × mⱼ ÷ Σw and loses available_skills × wⱼ × (1 − mⱼ) ÷ Σw. Each is rounded on its own, so equal skills show equal points.
- **Requirement items.** The semantic points earned are shared among the covered requirements in proportion to weight × similarity.
- **Experience and education items** say whether the minimum and the degree are met, with the points lost when not.
- **Strengths and gaps:** the five largest positive and the five largest negative items, each with its resume snippet and the section it came from.
- **Notes** flag data quality rather than score: "Education not found; check the original file", or experience above the JD's maximum (shown, not penalised).

## 8. Worked example: Candidate A and the Backend Java JD

Sample 3 ([`03_candidate_a_two_column.pdf`](../sample_data/resumes/03_candidate_a_two_column.pdf)) is Rahul Verma, a Java developer with a two-column resume. The JD is [`backend_java_developer.txt`](../sample_data/jds/backend_java_developer.txt). Every number below was produced by the code with the real model, and the tests pin them: [`test_worked_example.py`](../backend/tests/unit/matching/test_worked_example.py) (the skill table) and [`test_explainer_samples.py`](../backend/tests/unit/matching/test_explainer_samples.py) (the explanation and points).

**What the JD asks for** (after parsing)

| | |
| --- | --- |
| Required skills (w = 1.0) | Java, Spring Boot, REST APIs, Microservices, PostgreSQL |
| Preferred skills (w = 0.5) | Docker, Kafka, AWS |
| Experience | 4+ years |
| Education | Bachelor's in Computer Science or Information Technology |
| Requirement sentences | 11 required, 3 preferred (after leaving out the years and degree sentences) |

**What the resume has:** Java Developer at Contoso Payments since Jun 2022, and Technical Support Engineer at Initrode Telecom, Jun 2021 – May 2022. Skills listed: Java, Spring Boot, MySQL, REST, Docker, RabbitMQ, Git. Education: B.Tech in Computer Science, 2021.

### Skills: 0.731

| JD skill | w | Tier | Evidence | m | w · m |
| --- | --- | --- | --- | --- | --- |
| Java | 1.0 | Exact | "Java Developer" | 1.0 | 1.00 |
| Spring Boot | 1.0 | Exact | "Built REST endpoints with Spring Boot and MySQL…" | 1.0 | 1.00 |
| REST APIs | 1.0 | Alias | "REST" in the skills list | 1.0 | 1.00 |
| Microservices | 1.0 | Contextual | Not listed; the Contoso Payments role ("…Split a monolith into 8 independently deployed services…") has cosine 0.456 ≥ 0.43 with "Microservices" | 0.5 | 0.50 |
| PostgreSQL | 1.0 | Related | MySQL, same category (cosine 0.617 ≥ 0.58) | 0.5 | 0.50 |
| Docker | 0.5 | Exact | "Packaged every service as a Docker image…" | 1.0 | 0.50 |
| Kafka | 0.5 | Related | RabbitMQ, same category (cosine 0.594) | 0.5 | 0.25 |
| AWS | 0.5 | Missing | — | 0 | 0 |
| **Total** | **6.5** | | | | **4.75** |

S_skill = 4.75 ÷ 6.5 = **0.731**. All 5 required skills are present, two of them only indirectly.

### Semantic similarity: 1.0

The best passage for each requirement (most are the Contoso Payments role):

| Requirement | Type | Best cosine | Status |
| --- | --- | --- | --- |
| Design and build scalable backend services that process high volumes of payment transactions. | required | 0.490 | covered |
| Monitor services in production and help resolve incidents. | required | 0.455 | covered |
| Strong proficiency in Java and Spring Boot. | required | 0.437 | covered |
| Work with product managers and other engineers to plan and ship features. | required | 0.430 | covered |
| Experience designing and building REST APIs. | required | 0.414 | covered |
| Break down and evolve our microservices architecture, owning services end to end. | required | 0.413 | covered |
| Develop and maintain REST APIs consumed by web, mobile and partner applications. | required | 0.407 | covered |
| Write automated tests and review pull requests from teammates. | required | 0.379 | partial |
| Solid understanding of Microservices architecture. | required | 0.370 | partial |
| Hands-on experience with PostgreSQL. | required | 0.349 | partial |
| Write efficient queries and tune database schemas for performance. | required | 0.319 | partial |
| Experience with Docker. | preferred | 0.437 | covered |
| Exposure to AWS is a plus. | preferred | 0.265 | not covered |
| Familiarity with Kafka or other event streaming platforms. | preferred | 0.258 | not covered |

```
coverage = (4.463 × 1.0 + 0.960 × 0.5) / (11 × 1.0 + 3 × 0.5) = 4.943 / 12.5 = 0.395
raw      = 0.7 × 0.395 + 0.3 × 0.664 (whole JD vs whole resume)  = 0.476
S_sem    = clip((0.476 − 0.30) / 0.17, 0, 1) = clip(1.035) = 1.0
```

Above the "strong" mean of 0.47, so full marks: the role describes exactly this kind of work.

### Relevant experience: 1.0

| Role | Months | Cosine with the role profile | Factor | Counts |
| --- | --- | --- | --- | --- |
| Java Developer, Contoso Payments (Jun 2022 – now) | 54 | 0.673 | 1.0 | 54 months |
| Technical Support Engineer, Initrode Telecom (Jun 2021 – May 2022) | 12 | 0.341 | 0 | 0 |

Total experience is 5.5 years, but relevant experience is 54 ÷ 12 = **4.5 years**. S_exp = min(1, 4.5 ÷ 4) = **1.0**.

### Education: 1.0

B.Tech (bachelor's, level 3) meets the required bachelor's (level 3), and Computer Science is one of the JD's fields. S_edu = **1.0**.

### The score: 89.2, strong match

```
Score = 100 × (0.40 × 0.731 + 0.30 × 1.0 + 0.20 × 1.0 + 0.10 × 1.0) / 1.0
      = 100 × (0.2923 + 0.3 + 0.2 + 0.1) = 89.23
```

| Component | Available | Earned | Lost |
| --- | --- | --- | --- |
| Skills | 40.0 | 29.2 | 10.8 |
| Semantic similarity | 30.0 | 30.0 | 0 |
| Relevant experience | 20.0 | 20.0 | 0 |
| Education | 10.0 | 10.0 | 0 |
| **Total** | **100** | **89.2** | **10.8** |

All 10.8 lost points are on skills. Each skill's share is 40 × wⱼ × (1 − mⱼ) ÷ 6.5:

| Skill | Calculation | Lost |
| --- | --- | --- |
| Microservices (inferred only) | 40 × 1.0 × 0.5 ÷ 6.5 | 3.1 |
| PostgreSQL (related only) | 40 × 1.0 × 0.5 ÷ 6.5 | 3.1 |
| AWS (missing, preferred) | 40 × 0.5 × 1.0 ÷ 6.5 | 3.1 |
| Kafka (related only, preferred) | 40 × 0.5 × 0.5 ÷ 6.5 | 1.5 |

### What the recruiter sees

> **Strong match (89%).** Has 5 of 5 required skills: REST APIs, Microservices (inferred), Java, Spring Boot, PostgreSQL (related).

| Top strengths | Points |
| --- | --- |
| 4.5 years of relevant experience meets the 4-year minimum. | +20.0 |
| B.Tech in Computer Science meets the Bachelor's requirement. | +10.0 |
| Has REST APIs. ("Built REST endpoints with Spring Boot and MySQL…") | +6.2 |
| Has Java. ("Java Developer") | +6.2 |
| Has Spring Boot. | +6.2 |

| Top gaps | Points |
| --- | --- |
| Microservices not listed, but inferred from the "Java Developer \| Contoso Payments" role. | −3.1 |
| PostgreSQL credited at half: related skill MySQL found. | −3.1 |
| Missing preferred skill AWS. | −3.1 |
| Kafka credited at half: related skill RabbitMQ found. | −1.5 |

The 30 semantic points are shared among the 8 covered requirements by weight × similarity, from 4.5 points for the payment-services requirement down to 2.0 for "Experience with Docker" (a preferred one).

### What would change it

- **Listing PostgreSQL by name** would move it from related to exact: skills 5.25 ÷ 6.5 = 0.808, score **92.3**.
- **Skills-only weights** (the dashboard's sliders): the score is the skill score alone, **73.1**, and the keyword stuffer jumps from 11th to 2nd. That is why the semantic and experience components exist.
- **Keyword-only matching** (semantic weight 0, no related or inferred tiers) costs it 15.6 points: Microservices, PostgreSQL and Kafka count as missing, so the resume describes the right work without getting credit for it.

## 9. Every sample against the Java JD

Default weights, as `make eval-ranking` scores them (the full report is [ranking-results.md](ranking-results.md)):

| Rank | Sample | Expected | Skills | Semantic | Experience (relevant years) | Education | Score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 9 overlapping roles | strong | 1.00 | 0.91 | 1.00 (8.1) | 1.00 | 97.4 |
| 2 | 1 senior Java engineer | strong | 0.92 | 1.00 | 1.00 (7.5) | 1.00 | 96.9 |
| 3 | 2 Java, aliases only | strong | 0.85 | 1.00 | 1.00 (7.6) | 1.00 | 93.8 |
| 4 | 11 diploma only | good | 0.92 | 1.00 | 1.00 (6.1) | 0.50 | 91.9 |
| 5 | **3 Candidate A** | strong | 0.73 | 1.00 | 1.00 (4.5) | 1.00 | 89.2 |
| 6 | 5 Python/Django backend | partial | 0.46 | 0.99 | 1.00 (4.4) | 1.00 | 78.2 |
| 7 | 10 no dates | partial | 0.46 | 0.95 | 1.00 (7.0) | 1.00 | 76.9 |
| 8 | 14 table layout | partial | 0.54 | 0.85 | 0.96 (3.8) | 1.00 | 76.1 |
| 9 | 8 QA to backend | partial | 0.62 | 1.00 | 0.38 (1.5) | 0.80 | 70.1 |
| 10 | 4 junior Java | partial | 0.54 | 0.90 | 0.50 (2.0) | 1.00 | 68.6 |
| 11 | 7 keyword stuffer | partial | 1.00 | 0.01 | 0.00 (0.0) | 1.00 | 50.4 |
| 12 | 6 full-stack JavaScript | weak | 0.15 | 0.47 | 0.60 (2.4) | 1.00 | 42.3 |
| 13 | 12 data scientist | weak | 0.00 | 0.03 | 0.00 (0.0) | 0.80 | 9.0 |
| 14 | 13 accountant | weak | 0.00 | 0.00 | 0.00 (0.0) | 0.80 | 8.0 |

How to read it:

- **The keyword stuffer (7)** lists every JD skill (skills 1.00) but describes none of the work: semantic 0.01, no relevant experience. 40 + 0.3 + 0 + 10 = 50.4.
- **QA to backend (8)** has 5 years of experience, but only its last 1.5 are backend: experience 1.5 ÷ 4 = 0.38. Its Electronics degree meets the level but not the field: 0.8.
- **The known miss.** Sample 11 (rated "good": every skill exact, but a diploma) ranks above sample 3 (rated "strong"). The diploma costs it 5 points; Candidate A's indirect skills cost 10.8. Only raising education's weight to 0.2 swaps them. The design doc's 40/30/20/10 were kept rather than tuned to one pair of samples; the end-to-end test records this as an expected failure.
- Spearman correlation between score and expected tier: **0.93**.

## 10. Calibration

The design doc's starting thresholds assume a model with a wider similarity range than `all-MiniLM-L6-v2`. Each was re-measured on the samples:

| Threshold | Doc | Used | Measured |
| --- | --- | --- | --- |
| Related skill | 0.80 | **0.58** | Intended pairs fire: Spring Boot/Spring 0.88, PostgreSQL/MySQL 0.62, PyTorch/TensorFlow 0.62, Kafka/RabbitMQ 0.59. Wrong pairs stay out: Next.js/Node.js 0.55, Java/Python 0.54, Docker/Jenkins 0.54 |
| Contextual skill | 0.55 | **0.43** | The one described-but-unnamed skill (sample 3, Microservices) scores 0.46; the highest wrong one 0.40 |
| Semantic L / H | 0.20 / 0.70 | **0.30 / 0.47** | Mean raw score of the weak pairs 0.295 (n = 28) and of the strong pairs 0.473 (n = 6) |
| Covered / partial requirement | 0.55 / 0.40 | **0.40 / 0.30** | A strong candidate's median best match is 0.40; the accountant's 0.21 |
| Relevant / partly relevant role | 0.55 / 0.40 | **0.55 / 0.42** | Backend roles 0.66–0.72; QA 0.39, support 0.34, accounting 0.31–0.37. At 0.40 the QA role would have sat 0.01 below the cut |
| Same field of study | 0.6 | **0.6** | Unrelated fields top out at 0.54; related pairs the model scores lower are listed as equivalence groups |

- **The margins are thin**, so the tests pin every indirect match across the samples: a model or threshold change that adds or loses one fails a test.
- **Sensitivity** (from `make eval-ranking`): partial credit at 0.4 or 0.6 instead of 0.5 gives identical rankings. Moving any weight by ±0.1 keeps the same top 3, apart from two candidates 0.5 points apart, and except lowering education, which lets sample 11 into the top 3.
- **To recalibrate** (a new model, or new samples): run `make eval-ranking`, adjust the values in `scoring_config.py` with the measurements beside them, and bump `SCORING_VERSION`, so old and new scores are never compared as if they were the same scale.

## 11. Configuration reference

Every value lives in [`scoring_config.py`](../backend/app/services/matching/scoring_config.py).

| Setting | Value |
| --- | --- |
| Default weights (skills, semantic, experience, education) | 0.40, 0.30, 0.20, 0.10 |
| Skill weight (required, preferred) | 1.0, 0.5 |
| Partial credit (related, contextual) | 0.5 |
| Related skill minimum cosine (same category) | 0.58 |
| Contextual skill minimum cosine | 0.43 |
| Years-check floor | 0.5 |
| Semantic mix (coverage, whole document) | 0.7, 0.3 |
| Semantic calibration (L, H) | 0.30, 0.47 |
| Requirement status (covered, partial) | ≥ 0.40, ≥ 0.30 |
| Role relevance (full, half) | ≥ 0.55, ≥ 0.42 |
| Degree level scores (meets, one below, further) | 1.0, 0.5, 0.2 |
| Field mismatch factor | 0.8 |
| Same field minimum cosine | 0.6 |
| "Or equivalent experience" (education weight, extra years) | × 0.5, minimum + 2 |
| Verdict bands (strong, good, partial) | 80, 65, 50 |
| Strengths and gaps shown | 5 each |
| Scoring version | v1.0 |
