"""Every scoring weight and threshold lives here (design doc §6.7).

Thresholds belong to one embedding model: each model has its own similarity
range, so changing EMBEDDING_MODEL means measuring these again (step 30 writes
the calibration up in docs/).
"""

from typing import Final

DEFAULT_WEIGHTS: Final[dict[str, float]] = {
    "skills": 0.40,
    "semantic": 0.30,
    "experience": 0.20,
    "education": 0.10,
}

# --- Skill score (§6.2) -------------------------------------------------------------

REQUIRED_SKILL_WEIGHT: Final = 1.0
PREFERRED_SKILL_WEIGHT: Final = 0.5

# Tiers 3 and 4 give partial credit: the evidence is indirect.
PARTIAL_CREDIT: Final = 0.5

# Tier 3, related skill: cosine between the two skills' "Name (category)" vectors,
# same category only. The doc starts at 0.80, but all-MiniLM-L6-v2 never gets there
# for a related pair. Measured on the taxonomy and samples (2026-11-18):
#   fire:      Spring Boot/Spring 0.88, Deep Learning/Machine Learning 0.84,
#              PostgreSQL/MySQL 0.62, PyTorch/TensorFlow 0.62, Kafka/RabbitMQ 0.59
#   must not:  Next.js/Node.js 0.55, Java/Python 0.54, Docker/Jenkins 0.54,
#              Jest/JUnit 0.52, PostgreSQL/MongoDB 0.51
RELATED_MIN_COSINE: Final = 0.58

# Tier 4, contextual: the skill's bare name against a resume experience or project
# chunk. The doc starts at 0.55. Measured over every JD skill x sample resume that
# lacks the skill: the one described-but-unnamed case (sample 3, Microservices:
# "split a monolith into 8 independently deployed services") scores 0.46; the
# highest wrong one 0.40 (sample 10, Microservices). The skill's "Name (category)"
# vector (0.41) and the JD sentence (0.37) separated them less well than the name.
CONTEXT_MIN_COSINE: Final = 0.43

# Pairs that look alike to an embedding model but are different skills (§6.2 guard).
NEVER_EQUIVALENT: Final[frozenset[frozenset[str]]] = frozenset(
    frozenset(pair)
    for pair in [
        ("Java", "JavaScript"),
        ("C", "C#"),
        ("C", "C++"),
        ("React", "React Native"),
    ]
)

# Years check: below a skill's min_years, credit x max(floor, years used / required).
YEARS_CREDIT_FLOOR: Final = 0.5

# --- Semantic similarity (§6.3) -------------------------------------------------------

# raw = 0.7 * requirement coverage + 0.3 * whole-document cosine
COVERAGE_SHARE: Final = 0.7
DOCUMENT_SHARE: Final = 0.3

# Years and degree sentences are scored by the experience and education components.
# Here they would count twice, and they match any summary that states years ("10 years
# of experience in bookkeeping" scores 0.40 against "4+ years of backend development").
# Without them the strong/weak gap in raw scores grows from 0.160 to 0.178.
NOT_SEMANTIC_CATEGORIES: Final = frozenset({"experience", "education"})

# S_sem = clip((raw - L) / (H - L), 0, 1). The doc's rule, applied to the samples: L is
# the mean raw score of the "weak" sample/JD pairs (0.295, n=28), H that of the
# "strong" ones (0.473, n=6), measured with all-MiniLM-L6-v2 on 2026-11-19. The doc's
# starting values (0.20, 0.70) suit a model with a wider spread.
SEMANTIC_FLOOR: Final = 0.30  # L
SEMANTIC_CEILING: Final = 0.47  # H

# Requirement table status (§7.5), from the best passage's cosine. The doc's 0.55 / 0.40
# leave almost nothing covered with this model: the median best match of a strong
# candidate's requirements is 0.40, the accountant's 0.21.
COVERED_MIN_COSINE: Final = 0.40
PARTIAL_MIN_COSINE: Final = 0.30
