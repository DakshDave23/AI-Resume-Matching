"""Typed application settings, loaded from environment variables and `.env`.

Every tunable that is *not* a scoring parameter lives here. Scoring weights and
thresholds live in `app/services/matching/scoring_config.py` (design doc §6.7)
so they can be versioned together with `scoring_version`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win: a backend/.env can override the repo-root .env.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # the shared .env also holds POSTGRES_* and VITE_* keys
    )

    # --- App -------------------------------------------------------------
    app_name: str = "AI Resume Matcher"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_prefix: str = "/api/v1"
    # Comma-separated in the env file; use `cors_origin_list` in code.
    cors_origins: str = "http://localhost:5173"

    # --- Database --------------------------------------------------------
    # Local-development default matching docker-compose; override in .env.
    # 127.0.0.1 rather than localhost: see the note in .env.example.
    database_url: str = "postgresql+psycopg://resume:resume@127.0.0.1:5432/resume_matcher"

    # --- Uploads ---------------------------------------------------------
    upload_dir: Path = Path("./storage/uploads")
    # Capped at 5: resumes.file_size_bytes has a matching CHECK in the database.
    max_file_size_mb: int = Field(default=5, gt=0, le=5)
    max_batch_files: int = Field(default=50, gt=0, le=200)

    # --- Demo ------------------------------------------------------------
    # "Load sample data" creates this JD's job and uploads every file in resumes/.
    sample_data_dir: Path = REPO_ROOT / "sample_data"
    sample_jd: str = "jds/backend_java_developer.txt"

    # --- Parsing / NLP ---------------------------------------------------
    phone_default_region: str = Field(default="IN", min_length=2, max_length=2)
    # Any 384-dimensional sentence-transformers model, e.g. BAAI/bge-small-en-v1.5. After
    # switching, re-embed the skills (scripts/seed_skills.py --reembed) and recalibrate.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = Field(default=32, gt=0, le=256)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process; use as a FastAPI dependency."""
    return Settings()
