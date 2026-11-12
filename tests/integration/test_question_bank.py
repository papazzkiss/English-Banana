"""Question bank: record checks, import, dynamic sets with anti-repetition, instant checking."""

from __future__ import annotations

import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from banana_english.api.app import create_app
from banana_english.config.container import build_container
from banana_english.config.settings import PROJECT_ROOT, Settings
from banana_english.contentbank.importer import import_bank
from banana_english.contentbank.schema import (
    OptionRecord,
    PassageRecord,
    QuestionRecord,
    SourceRef,
)
from banana_english.contentbank.store import iter_records, write_skill
from banana_english.domain.models import CefrLevel, Difficulty, Module
from banana_english.domain.models.bank import BankOption, BankQuestion, QuestionType
from banana_english.domain.services.answer_check import (
    InvalidAnswerError,
    check_answer,
)
from banana_english.infrastructure.ai.mock_llm import HeuristicMockLLMProvider
from banana_english.infrastructure.cache.caches import MemoryCache
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository
from banana_english.infrastructure.jobs.runners import InlineJobRunner
from banana_english.infrastructure.stt.mock_stt import MockSTTProvider
from tests.conftest import T0, MutableClock, create_learner

SRC = SourceRef(id="test", ref="", license="CC0")
OPTS = [
    OptionRecord(id=i, text=t)
    for i, t in zip("abcd", ["goes", "went", "has gone", "going"], strict=True)
]


def mcq(n: int, point: str = "past_simple", level: str = "A1", **kw) -> QuestionRecord:
    return QuestionRecord(
        id=f"gr.{point}.{n:04d}",
        skill="grammar",
        skill_id=f"grammar.{point}",
        level=CefrLevel(level),
        topic="daily_life",
        point=point,
        difficulty=Difficulty.EASY,
        qtype=QuestionType.MCQ,
        instruction="Choose the correct form.",
        prompt=f"Sentence {n}: She ___ to school yesterday.",
        options=OPTS,
        answer={"option": "b"},
        explanation="'Yesterday' is finished past time: past simple.",
        explanation_vi="'Yesterday' là quá khứ: dùng quá khứ đơn.",
        source=SRC,
        quality=0.9,
        **kw,
    )


def reading(pid: str, n: int) -> list[QuestionRecord]:
    return [
        QuestionRecord(
            id=f"rd.{pid}.q{i}",
            skill="reading",
            skill_id="reading.comprehension",
            level=CefrLevel.B1,
            topic="science",
            point="detail" if i else "main_idea",
            difficulty=Difficulty.MEDIUM,
            qtype=QuestionType.TRUE_FALSE,
            instruction="True or false?",
            prompt=f"Statement {i} about {pid}.",
            options=[OptionRecord(id="t", text="True"), OptionRecord(id="f", text="False")],
            answer={"option": "t"},
            explanation="The text says so in the second sentence.",
            passage_id=f"rd.{pid}",
            source=SRC,
            quality=0.8,
        )
        for i in range(n)
    ]


@pytest.fixture
def bank_dir(tmp_path):
    root = tmp_path / "bank"
    write_skill(
        "grammar",
        [mcq(i) for i in range(30)] + [mcq(i, "present_perfect") for i in range(30)],
        bank_dir=root,
    )
    passages = [
        PassageRecord(
            id=f"rd.p{i}",
            skill="reading",
            level=CefrLevel.B1,
            topic="science",
            title=f"Text {i}",
            text="A short text about science. " * 5,
            source=SRC,
            quality=0.8,
        )
        for i in range(4)
    ]
    write_skill(
        "reading", [q for i in range(4) for q in reading(f"p{i}", 4)], passages, bank_dir=root
    )
    return root


@pytest.fixture
def app_env(tmp_path, bank_dir):
    """A container on a file database (shared by the importer and the API)."""
    clock = MutableClock()

    def make(**settings):
        s = Settings(
            database_url=f"sqlite:///{tmp_path / 'bank.db'}", upload_dir=tmp_path / "up", **settings
        )
        c = build_container(
            s,
            llm=HeuristicMockLLMProvider(),
            stt=MockSTTProvider(),
            clock=clock,
            content=JsonContentRepository(
                PROJECT_ROOT / "content", require_reviewed=s.require_reviewed_content
            ),
            runner=InlineJobRunner(),
            cache=MemoryCache(),
        )
        c.bank._rng = random.Random(7)
        return c

    container = make()
    from sqlalchemy.orm import sessionmaker

    from banana_english.infrastructure.database.repositories import create_db_engine

    factory = sessionmaker(
        create_db_engine(f"sqlite:///{tmp_path / 'bank.db'}"), expire_on_commit=False
    )
    import_bank(factory, bank_dir, log=lambda _: None, seed=1)
    return container, clock, factory, make


# --- checker --------------------------------------------------------------------------------


def q(qtype, answer, options=(), **kw):
    return BankQuestion(
        id="x",
        skill=Module.GRAMMAR,
        skill_id="g",
        level=CefrLevel.A1,
        topic="t",
        point="p",
        difficulty=Difficulty.EASY,
        qtype=qtype,
        prompt="p",
        instruction="i",
        answer=answer,
        explanation="e",
        options=tuple(BankOption(*o) for o in options),
        **kw,
    )


def test_checker_every_type():
    choice = q(QuestionType.MCQ, {"option": "b"}, [("a", "go"), ("b", "went")])
    assert check_answer(choice, "b").correct and check_answer(choice, "b").correct_answer == "went"
    assert not check_answer(choice, "a").correct
    blank = q(QuestionType.FILL_BLANK, {"accepted": ["has lived", "'s lived"]})
    assert check_answer(blank, "  Has lived. ").correct and check_answer(blank, "’s lived").correct
    assert not check_answer(blank, "lived").correct
    dict_q = q(QuestionType.DICTATION, {"text": "I have two older brothers."})
    near = check_answer(dict_q, "i have two older brother")
    assert not near.correct and 75 <= near.score < 90
    assert check_answer(dict_q, "I have two older brothers").correct
    order = q(QuestionType.ORDERING, {"order": ["She", "is", "happy"]})
    assert check_answer(order, ["she", "is", "happy"]).correct
    assert not check_answer(order, ["is", "she", "happy"]).correct
    match = q(QuestionType.MATCHING, {"pairs": {"1": "a", "2": "b", "3": "c"}})
    partial = check_answer(match, {"1": "a", "2": "c", "3": "b"})
    assert not partial.correct and partial.score == pytest.approx(33.3)
    with pytest.raises(InvalidAnswerError):
        check_answer(choice, ["b"])


def test_records_with_broken_answers_are_rejected():
    with pytest.raises(ValidationError, match="answer is not one of the options"):
        mcq(1).model_copy(update={}).model_validate(
            {**mcq(1).model_dump(), "answer": {"option": "z"}}
        )
    dup = [OptionRecord(id="a", text="went"), OptionRecord(id="b", text="Went")]
    with pytest.raises(ValidationError, match="duplicate option texts"):
        QuestionRecord.model_validate(
            {**mcq(1).model_dump(), "options": [o.model_dump() for o in dup]}
        )
    with pytest.raises(ValidationError, match="need a passage"):
        QuestionRecord.model_validate({**reading("p", 1)[0].model_dump(), "passage_id": None})


# --- import -----------------------------------------------------------------------------------


def test_import_is_incremental(tmp_path, bank_dir, app_env):
    _, _, factory, _ = app_env
    again = import_bank(factory, bank_dir, log=lambda _: None)
    assert again["inserted"] == 0 and again["unchanged"] == 76 and again["disabled"] == 0
    write_skill("grammar", [mcq(i) for i in range(10)], bank_dir=bank_dir)  # 50 removed
    shrunk = import_bank(factory, bank_dir, log=lambda _: None)
    assert shrunk["disabled"] == 50
    assert sum(1 for r in iter_records(bank_dir) if isinstance(r, QuestionRecord)) == 26


# --- sets and answers over the API -------------------------------------------------------------


def test_sets_hide_answers_and_answers_are_checked_instantly(app_env):
    container, _, _, _ = app_env
    client = TestClient(create_app(container))
    h = create_learner(client, "A2")
    r = client.post("/api/v1/bank/grammar/sets", headers=h, json={"count": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["questions"]) == 10
    assert all("answer" not in qq and "explanation" not in qq for qq in body["questions"])
    first = body["questions"][0]
    a = client.post(
        "/api/v1/bank/answer", headers=h, json={"question_id": first["id"], "answer": "b"}
    )
    assert a.status_code == 200, a.text
    res = a.json()
    assert res["correct"] and res["correct_answer"] == "went" and res["explanation_vi"]
    assert res["mastery"]["skill_id"] == first["id"].rsplit(".", 1)[0].replace("gr.", "grammar.")
    wrong = client.post(
        "/api/v1/bank/answer",
        headers=h,
        json={"question_id": body["questions"][1]["id"], "answer": "a"},
    ).json()
    assert not wrong["correct"] and wrong["correct_answer"] == "went"
    summary = client.get("/api/v1/bank/grammar/summary", headers=h).json()
    assert summary == {
        "skill": "grammar",
        "pool_size": 60,
        "questions_seen": 2,
        "correct_answers": 1,
        "wrong_answers": 1,
        "to_review": 1,
    }
    history = client.get("/api/v1/learner/attempts", headers=h).json()
    assert {x["item_id"] for x in history} == {first["id"], body["questions"][1]["id"]}
    assert {x["module"] for x in history} == {"grammar"}


def test_filters_and_facets(app_env):
    container, _, _, _ = app_env
    client = TestClient(create_app(container))
    h = create_learner(client)
    facets = client.get("/api/v1/bank/grammar/facets", headers=h).json()
    assert facets["total"] == 60 and facets["points"] == {"past_simple": 30, "present_perfect": 30}
    assert facets["point_names"]["present_perfect"] == "Present perfect"
    r = client.post(
        "/api/v1/bank/grammar/sets", headers=h, json={"points": ["present_perfect"], "count": 12}
    ).json()
    assert {x["point"] for x in r["questions"]} == {"present_perfect"}
    assert client.post("/api/v1/bank/speaking/sets", headers=h, json={}).status_code == 422


def test_new_sets_avoid_seen_questions_then_review_wrong_ones(app_env):
    container, clock, _, _ = app_env
    client = TestClient(create_app(container))
    h = create_learner(client)
    seen: set[str] = set()
    for _ in range(3):  # 3 sets of 20 = the whole pool of 60, never a repeat
        qs = client.post("/api/v1/bank/grammar/sets", headers=h, json={"count": 20}).json()[
            "questions"
        ]
        ids = {x["id"] for x in qs}
        assert not ids & seen
        seen |= ids
        for x in qs:  # answer everything; a third wrong
            ans = "a" if int(x["id"][-4:]) % 3 == 0 else "b"
            client.post(
                "/api/v1/bank/answer", headers=h, json={"question_id": x["id"], "answer": ans}
            )
    assert len(seen) == 60
    clock.advance(timedelta(days=1))
    qs = client.post("/api/v1/bank/grammar/sets", headers=h, json={"count": 8}).json()
    wrong_ids = [x["id"] for x in qs["questions"] if int(x["id"][-4:]) % 3 == 0]
    assert qs["review_count"] == 2 and len(wrong_ids) >= 2  # 25% review of what was wrong


def test_weak_skills_get_a_share_of_new_sets(app_env):
    container, clock, _, _ = app_env
    client = TestClient(create_app(container))
    h = create_learner(client)
    for point, ans in (("present_perfect", "a"), ("past_simple", "b")):  # wrong / right
        qs = client.post(
            "/api/v1/bank/grammar/sets", headers=h, json={"points": [point], "count": 6}
        ).json()["questions"]
        for x in qs:
            client.post(
                "/api/v1/bank/answer", headers=h, json={"question_id": x["id"], "answer": ans}
            )
    weak = {
        s["skill_id"] for s in client.get("/api/v1/learner/weak-skills", headers=h).json()["skills"]
    }
    assert "grammar.present_perfect" in weak and "grammar.past_simple" not in weak
    clock.advance(timedelta(hours=2))  # past the no-repeat hour, before any review is due
    for _ in range(3):
        qs = client.post("/api/v1/bank/grammar/sets", headers=h, json={"count": 10}).json()
        assert qs["review_count"] == 0
        points = [x["point"] for x in qs["questions"]]
        assert points.count("present_perfect") >= 4  # 40% of the new questions: the weak skill


def test_two_learners_get_different_sets_from_the_same_pool(app_env):
    container, _, _, _ = app_env
    client = TestClient(create_app(container))
    a = create_learner(client)
    first = {
        x["id"]
        for x in client.post("/api/v1/bank/grammar/sets", headers=a, json={"count": 10}).json()[
            "questions"
        ]
    }
    second = {
        x["id"]
        for x in client.post("/api/v1/bank/grammar/sets", headers=a, json={"count": 10}).json()[
            "questions"
        ]
    }
    assert first != second  # nothing answered yet: still a new draw each time


def test_reading_sets_come_by_passage(app_env):
    container, _, _, _ = app_env
    client = TestClient(create_app(container))
    h = create_learner(client, "B1")
    r = client.post("/api/v1/bank/reading/sets", headers=h, json={"count": 6}).json()
    pids = {x["passage_id"] for x in r["questions"]}
    assert len(r["passages"]) == len(pids) == 2  # 4 questions per text: two texts
    assert all(p["text"] for p in r["passages"])
    assert r["questions"][0]["point"] == "main_idea"  # the gist question first


def test_approved_only_mode_serves_no_machine_validated_questions(app_env):
    _, _, _, make = app_env
    container = make(require_reviewed_content=True)
    client = TestClient(create_app(container))
    h = create_learner(client)
    r = client.post("/api/v1/bank/grammar/sets", headers=h, json={"count": 5}).json()
    assert r["questions"] == []
    assert "reading.comprehension" not in {s.id for s in container.content.list_skills()}


def test_answer_path_never_calls_the_llm(app_env):
    container, _, _, _ = app_env
    calls_before = container.llm._inner.calls  # heuristic mock counts its calls
    client = TestClient(create_app(container))
    h = create_learner(client)
    qid = client.post("/api/v1/bank/grammar/sets", headers=h, json={"count": 1}).json()[
        "questions"
    ][0]["id"]
    client.post("/api/v1/bank/answer", headers=h, json={"question_id": qid, "answer": "b"})
    assert container.llm._inner.calls == calls_before


def test_t0_clock_is_used(app_env):
    _, clock, _, _ = app_env
    assert clock.now() == T0
