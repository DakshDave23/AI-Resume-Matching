"""Domain enums (design doc §4, "Enum types").

String enums are stored as native Postgres ENUM types. The Postgres type
objects are defined once here and shared by every column that uses them.
Their lowercase *values* (not the Python member names) are what the DB stores.
"""

from enum import IntEnum, StrEnum

from sqlalchemy import Enum as SAEnum


class JobStatus(StrEnum):
    DRAFT = "draft"
    PARSED = "parsed"
    ARCHIVED = "archived"


class BatchStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class ParseStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class FileType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"


class RequirementType(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class RequirementCategory(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    RESPONSIBILITY = "responsibility"
    OTHER = "other"


class SkillSource(StrEnum):
    SKILLS_SECTION = "skills_section"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    SUMMARY = "summary"
    OTHER = "other"


class SkillCategory(StrEnum):
    """Taxonomy categories. Related-skill credit (tier 3) only flows within one category,
    so categories are deliberately narrower than "tool" or "framework" alone."""

    LANGUAGE = "language"  # Java, Python, SQL, HTML
    FRAMEWORK = "framework"  # Spring Boot, React, Django
    LIBRARY = "library"  # pandas, NumPy, PyTorch, scikit-learn
    DATABASE = "database"  # PostgreSQL, MongoDB, Redis
    MESSAGING = "messaging"  # Kafka, RabbitMQ, SQS
    CLOUD = "cloud"  # AWS, Azure, S3
    DEVOPS = "devops"  # Docker, Kubernetes, Terraform, CI/CD
    TOOL = "tool"  # Git, Maven, Jira, IntelliJ
    DATA = "data"  # Spark, Airflow, Tableau, ETL
    ML = "ml"  # Machine Learning, NLP, Deep Learning
    TESTING = "testing"  # JUnit, Selenium, Cypress
    CONCEPT = "concept"  # REST APIs, Microservices, OOP
    METHODOLOGY = "methodology"  # Agile, Scrum, TDD
    SOFT = "soft"  # Communication, Leadership
    BUSINESS = "business"  # Accounting, Excel, SAP


class SkillAddedBy(StrEnum):
    """Who attached a skill to a job. Stored as VARCHAR(10) + CHECK, per the design doc."""

    PARSER = "parser"
    RECRUITER = "recruiter"


class Seniority(StrEnum):
    """Read from a JD title (design doc §5.4). Kept in jobs.parsed_json; there is no column."""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


class DegreeLevel(IntEnum):
    """Stored as SMALLINT 0-5 with a CHECK constraint, so levels can be compared with >=."""

    NONE = 0
    HIGH_SCHOOL = 1
    DIPLOMA = 2
    BACHELOR = 3
    MASTER = 4
    DOCTORATE = 5


def _pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


# Shared Postgres ENUM types.
job_status_type = _pg_enum(JobStatus, "job_status")
batch_status_type = _pg_enum(BatchStatus, "batch_status")
parse_status_type = _pg_enum(ParseStatus, "parse_status")
file_type_type = _pg_enum(FileType, "file_type")
requirement_type_type = _pg_enum(RequirementType, "requirement_type")
requirement_category_type = _pg_enum(RequirementCategory, "requirement_category")
skill_source_type = _pg_enum(SkillSource, "skill_source")
