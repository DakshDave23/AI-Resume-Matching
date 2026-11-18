"""Every scoring weight and threshold lives here (design doc §6.7).

Step 4 only needs the default weights (used as the jobs.scoring_weights default).
Thresholds and SCORING_VERSION are added with the matching engine in steps 22-26.
"""

from typing import Final

DEFAULT_WEIGHTS: Final[dict[str, float]] = {
    "skills": 0.40,
    "semantic": 0.30,
    "experience": 0.20,
    "education": 0.10,
}
