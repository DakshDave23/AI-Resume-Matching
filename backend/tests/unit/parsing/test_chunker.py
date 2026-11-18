from datetime import date

import pytest

from app.services.parsing.chunker import MAX_CHUNK_WORDS, Chunk, chunk_resume, chunk_section
from app.services.parsing.experience import parse_experience
from app.services.parsing.resume_parser import parse_resume
from app.services.parsing.sections import segment
from tests.samples import AS_OF, TEXT_RESUMES, resume_text

TODAY = date(2026, 11, 1)


def chunks_of(text: str) -> list[Chunk]:
    sections = segment(text)
    work = parse_experience(sections.text_of("experience"), today=TODAY)
    return chunk_resume(sections, work)


def bullet(n: int, words: int = 10) -> str:
    return f"- Bullet {n} " + " ".join(["word"] * (words - 2)) + "."


# --- Roles ------------------------------------------------------------------------------


def test_a_role_is_one_chunk_headed_by_title_and_company() -> None:
    text = """\
Experience
Java Developer | Contoso Payments
Jun 2022 – Present
- Built REST endpoints with Spring Boot and MySQL for wallet
top-ups and refunds.
- Packaged every service as a Docker image."""
    assert chunks_of(text) == [
        Chunk(
            "experience",
            "Java Developer | Contoso Payments\n"
            "- Built REST endpoints with Spring Boot and MySQL for wallet top-ups and refunds.\n"
            "- Packaged every service as a Docker image.",
        )
    ]


def test_a_long_role_splits_between_bullets_and_repeats_its_header() -> None:
    bullets = "\n".join(bullet(n, 30) for n in range(1, 6))  # 150 words of bullets
    text = f"Experience\nBackend Engineer | Acme\nJan 2020 – Present\n{bullets}"
    chunks = chunks_of(text)

    assert len(chunks) == 2
    assert all(c.text.startswith("Backend Engineer | Acme\n- Bullet") for c in chunks)
    assert all(c.words <= MAX_CHUNK_WORDS for c in chunks)
    assert [c.text.count("- Bullet") for c in chunks] == [3, 2]  # no bullet cut in half


def test_a_bullet_too_long_for_one_chunk_splits_by_sentence() -> None:
    sentence = "Built " + " ".join(["things"] * 48) + "."  # 50 words
    text = f"Experience\nEngineer | Acme\nJan 2020 – Present\n- {sentence} {sentence} {sentence}"
    chunks = chunks_of(text)
    assert len(chunks) == 2
    assert all(c.words <= MAX_CHUNK_WORDS for c in chunks)


def test_a_single_endless_sentence_is_cut_by_words() -> None:
    text = "Summary\n" + " ".join(["word"] * 300)
    chunks = chunks_of(text)
    assert [c.words for c in chunks] == [120, 120, 60]


def test_a_role_without_bullets_still_gives_its_header() -> None:
    text = "Experience\nJava Developer | Initech\n2019 – 2021"
    assert chunks_of(text) == [Chunk("experience", "Java Developer | Initech")]


# --- Other sections -----------------------------------------------------------------------


def test_the_summary_is_one_paragraph() -> None:
    text = "Summary\nJava developer with 5 years in the industry,\nbuilding payment systems.\n"
    assert chunks_of(text) == [
        Chunk("summary", "Java developer with 5 years in the industry, building payment systems.")
    ]


def test_projects_group_bullets_under_their_name() -> None:
    text = """\
Payments Gateway | Java, Kafka
- Routed card payments through three acquirers.
- Cut failed payments by 12%.
Inventory Bot
- Wrote a Slack bot that reports stock levels."""
    assert chunk_section("projects", text) == [
        Chunk(
            "projects",
            "Payments Gateway | Java, Kafka\n"
            "- Routed card payments through three acquirers.\n- Cut failed payments by 12%.",
        ),
        Chunk("projects", "Inventory Bot\n- Wrote a Slack bot that reports stock levels."),
    ]


def test_sections_come_in_order_and_skills_are_not_chunked() -> None:
    text = """\
Asha Rao
Projects
Inventory Bot
- Wrote a Slack bot.
Skills
Java, Spring Boot, Kafka
Experience
Engineer | Acme
Jan 2020 – Present
- Built APIs.
Summary
Backend developer."""
    assert [c.section for c in chunks_of(text)] == ["summary", "experience", "projects"]


def test_nothing_to_chunk() -> None:
    assert chunks_of("Asha Rao\nSkills\nJava") == []


# --- The samples ----------------------------------------------------------------------------


@pytest.mark.parametrize("resume", TEXT_RESUMES, ids=lambda r: r["file"])
def test_every_sample_bullet_lands_in_exactly_one_chunk(resume: dict[str, object]) -> None:
    parsed = parse_resume(resume_text(resume), today=AS_OF, region="IN")
    chunks = chunk_resume(parsed.sections, parsed.work)

    assert chunks, "every sample has experience to chunk"
    assert all(c.words <= MAX_CHUNK_WORDS for c in chunks)
    flat = [" ".join(c.text.split()) for c in chunks]
    for role in parsed.work.roles:
        for line in role.description.split("\n- "):
            words = " ".join(line.removeprefix("- ").split())
            assert sum(words in text for text in flat) == 1, words
