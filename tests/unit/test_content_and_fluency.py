"""Content quality gates + deterministic fluency metrics."""

import csv
import json
import re
import shutil
import wave
from collections import Counter

import pytest

from banana_english.config.settings import PROJECT_ROOT
from banana_english.domain.models import ContentReviewStatus, Module
from banana_english.domain.services.answer_matching import matches_any
from banana_english.domain.services.fluency import Segment, fluency_metrics
from banana_english.infrastructure.content.json_content_repository import (
    ContentError,
    JsonContentRepository,
)

CONTENT = PROJECT_ROOT / "content"


def load(path):
    return json.loads((CONTENT / path).read_text())


def test_vocabulary_is_real_cited_and_matches_cefrj():
    vocab = load("vocabulary/vocabulary.json")
    assert {s["id"] for s in vocab["sources"]} == {"cefrj-1.5", "oewn:2024"}
    assert len(vocab["items"]) > 5000
    assert set(Counter(i["cefr_level"] for i in vocab["items"])) == {"A1", "A2", "B1", "B2"}
    with (CONTENT / "vocabulary/sources/cefrj-vocabulary-profile-1.5.csv").open() as fh:
        source = {(r["headword"].split("/")[0], r["pos"]): r["CEFR"] for r in csv.DictReader(fh)}
    for i in vocab["items"][::50]:
        assert source[(i["word"], i["part_of_speech"])] == i["cefr_level"]
        assert i["definition"] and i["provenance"]["sense_id"].startswith("oewn-")


def test_beginner_flashcards_use_learner_definitions():
    """A1/A2 cards show a simple definition; it never names the answer, and the example
    always contains the word so the card can blank it out."""
    from banana_english.domain.services.vocabulary_exercises import (
        BLANK,
        build_recall_exercise,
    )

    simple = load("vocabulary/learner_definitions.json")["items"]
    vocab = load("vocabulary/vocabulary.json")["items"]
    beginner = [i for i in vocab if i["cefr_level"] in ("A1", "A2")]
    assert {i["id"] for i in beginner} <= set(simple)
    repo = JsonContentRepository(CONTENT)
    ghost = repo.get_vocabulary_item("ghost.noun")
    assert ghost.definition == "the spirit of a dead person that some people believe they can see"
    for record in beginner:
        item = repo.get_vocabulary_item(record["id"])
        card = build_recall_exercise(item)
        assert BLANK in card.prompt, item.id
        forms = (item.word, *item.variants)
        assert not any(
            re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", item.definition, re.I) for f in forms
        ), item.id
        assert not card.prompt.startswith("Definition"), item.id


def test_learner_definition_is_skipped_when_the_sense_changed(content_copy):
    def other_sense(d):
        for i in d["items"]:
            if i["id"] == "ghost.noun":
                i["definition"] = "a faint secondary image on a screen"

    _rewrite(content_copy, "vocabulary/vocabulary.json", other_sense)
    ghost = JsonContentRepository(content_copy).get_vocabulary_item("ghost.noun")
    assert ghost.definition == "a faint secondary image on a screen"


def test_grammar_30_to_50_exercises_5_to_6_topics_with_difficulty():
    grammar = load("grammar/exercises.json")
    assert 30 <= len(grammar["exercises"]) <= 50
    assert 5 <= len({e["skill_id"] for e in grammar["exercises"]}) <= 6
    assert {e["difficulty"] for e in grammar["exercises"]} == {"easy", "medium", "hard"}


def test_listening_lessons_have_real_audio_of_15_to_30_seconds(content):
    lessons = content.list_listening()
    assert 5 <= len(lessons) <= 10
    for lesson in lessons:
        assert 13 <= lesson.duration_seconds <= 30, lesson.id
        assert 2 <= len(lesson.questions) <= 3
        with wave.open(str(content.audio_dir / lesson.audio_file)) as w:
            assert w.getnframes() > 0


def test_speaking_and_conversation_content(content):
    assert len(content.list_speaking()) >= 5
    scenarios = content.list_scenarios()
    assert len(scenarios) >= 3
    assert all(4 <= s.max_learner_turns <= 6 for s in scenarios)
    grammar_skills = {s.id for s in content.list_skills() if s.module is Module.GRAMMAR}
    for s in scenarios:
        assert set(s.target_skills) <= grammar_skills
    for p in content.list_speaking():
        assert p.target_grammar in grammar_skills


def test_calibration_set_is_usable(content):
    items = load("calibration/grammar_calibration.json")["items"]
    assert 15 <= len(items) <= 20
    for item in items:
        exercise = content.get_exercise(item["exercise_id"])
        assert exercise is not None
        # Items must reach the LLM, so they must not be exact reference answers.
        assert not matches_any(item["answer"], exercise.accepted_answers), item["id"]
        assert item["label_is_correct"] == (item["label_score"] >= 70)
    scores = [i["label_score"] for i in items]
    assert min(scores) < 40 and max(scores) >= 90  # covers the rubric range


def test_all_ai_generated_content_carries_review_metadata(content):
    for kind, counts in content.review_counts.items():
        assert sum(counts.values()) > 0, kind


def test_skills_cover_every_module(content):
    assert {s.module for s in content.list_skills()} == set(Module)


def _skip_large(directory: str, names: list[str]) -> set[str]:
    """Word-list sources, and the question bank's shards and recordings (hundreds of MB; the
    content repository reads only bank/skills.json)."""
    skip = {"sources"}
    if directory.endswith("bank"):
        skip |= {"audio", "questions", "passages"}
    return skip & set(names)


@pytest.fixture
def content_copy(tmp_path):
    shutil.copytree(CONTENT, tmp_path / "content", ignore=_skip_large)
    return tmp_path / "content"


def _rewrite(root, rel, mutate):
    path = root / rel
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


def test_require_reviewed_serves_only_approved(content_copy):
    def approve_first(d):
        d["exercises"][0]["review"].update(
            status="approved", reviewed_by="teacher", reviewed_at="2026-01-01"
        )

    _rewrite(content_copy, "grammar/exercises.json", approve_first)
    repo = JsonContentRepository(content_copy, require_reviewed=True)
    assert [s.id for s in repo.list_skills() if s.module is Module.GRAMMAR] == [
        "grammar.present_simple_continuous"
    ]
    assert repo.list_listening() == [] and repo.list_scenarios() == []


@pytest.mark.parametrize(
    ("rel", "mutate"),
    [
        ("grammar/exercises.json", lambda d: d["exercises"][0].pop("difficulty")),
        ("grammar/exercises.json", lambda d: d["exercises"][0].update(skill_id="grammar.unknown")),
        ("grammar/exercises.json", lambda d: d["exercises"][0]["review"].update(status="approved")),
        ("listening/lessons.json", lambda d: d["lessons"][0].update(audio_file="missing.wav")),
        ("listening/lessons.json", lambda d: d["lessons"][0].update(questions=[])),
        ("conversation/scenarios.json", lambda d: d["scenarios"][0].update(max_learner_turns=50)),
    ],
)
def test_invalid_content_fails_fast(content_copy, rel, mutate):
    _rewrite(content_copy, rel, mutate)
    with pytest.raises(ContentError):
        JsonContentRepository(content_copy)


def test_review_status_enum_used_everywhere():
    for rel, key in [
        ("grammar/exercises.json", "exercises"),
        ("listening/lessons.json", "lessons"),
        ("speaking/prompts.json", "prompts"),
        ("conversation/scenarios.json", "scenarios"),
    ]:
        for x in load(rel)[key]:
            assert x["review"]["status"] in {s.value for s in ContentReviewStatus}


# --- fluency --------------------------------------------------------------------------------


def seg(start, end, text):
    return Segment(start, end, text)


def test_natural_speech_scores_high():
    text = " ".join(["word"] * 30)  # 30 words in 15 s = 120 wpm
    m = fluency_metrics([seg(0, 15, text)], text)
    assert m.words_per_minute == 120 and m.score == 100


def test_slow_hesitant_speech_scores_low():
    text = "um I uh go um to the uh beach er"
    segments = [seg(0, 4, "um I uh go"), seg(7, 12, "um to the"), seg(15, 20, "uh beach er")]
    m = fluency_metrics(segments, text)
    assert m.filler_count == 5 and m.long_pauses == 2 and m.score < 40


def test_too_short_scores_zero():
    assert fluency_metrics([seg(0, 2, "hello there")], "hello there").score == 0


# --- database migrations -----------------------------------------------------------------


def test_migrations_match_the_models(tmp_path):
    """Alembic head must produce exactly the schema the ORM models describe."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from banana_english.infrastructure.database.repositories import create_db_engine
    from banana_english.infrastructure.database.tables import Base

    engine = create_db_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
    # idempotent: running again on an up-to-date database is a no-op
    create_db_engine(f"sqlite:///{tmp_path / 'm.db'}")
    # a legacy database created with create_all (no alembic_version) is adopted, not recreated
    # A database from before migrations existed: created by create_all, without auth tables.
    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    added_later = {  # tables created by revisions after the initial one
        "accounts",
        "sessions",
        "bank_passages",
        "bank_questions",
        "learner_question_stats",
        "bank_imports",
        "teacher_students",
    }
    pre_auth = [t for name, t in Base.metadata.tables.items() if name not in added_later]
    Base.metadata.create_all(legacy, tables=pre_auth)
    with legacy.begin() as conn:  # users as they were before the role columns (0004)
        conn.exec_driver_sql("DROP INDEX ix_users_role")
        conn.exec_driver_sql("ALTER TABLE users DROP COLUMN role")
        conn.exec_driver_sql("ALTER TABLE users DROP COLUMN is_active")
        conn.exec_driver_sql("INSERT INTO users VALUES ('u1', 'Old', '2026-01-01 00:00:00')")
    engine = create_db_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM users").scalar() == 1
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0004"
        # an existing user became an active student
        assert conn.exec_driver_sql("SELECT role, is_active FROM users").one() == ("student", 1)
        assert conn.exec_driver_sql("SELECT count(*) FROM accounts").scalar() == 0  # added
        assert conn.exec_driver_sql("SELECT count(*) FROM bank_questions").scalar() == 0
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_waits_for_a_late_database(monkeypatch):
    """After a host reboot the DB can come up after the API: retry, don't crash-loop."""
    from sqlalchemy.exc import OperationalError

    from banana_english.infrastructure.database import repositories

    calls = {"n": 0}

    class FlakyEngine:
        def connect(self):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OperationalError("connect", {}, Exception("failed to resolve host 'db'"))
            import contextlib

            return contextlib.nullcontext()

    repositories._wait_for_database(FlakyEngine(), attempts=5, delay_seconds=0)
    assert calls["n"] == 3
    calls["n"] = -100
    import pytest

    with pytest.raises(OperationalError):
        repositories._wait_for_database(FlakyEngine(), attempts=2, delay_seconds=0)
