"""Authorization: roles, resource ownership, account status and the question bank's review.

Every rule is checked over HTTP, the way an attacker would try it: with another role's token,
another user's id, a disabled account, an expired session or a forged field.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from banana_english.contentbank.importer import import_bank
from banana_english.contentbank.schema import (
    OptionRecord,
    PassageRecord,
    QuestionRecord,
    SourceRef,
)
from banana_english.contentbank.store import write_skill
from banana_english.domain.models import CefrLevel, Difficulty
from banana_english.domain.models.bank import QuestionType
from tests.conftest import create_learner, create_user

SRC = SourceRef(id="test", ref="", license="CC0")


def _grammar(n: int, prompt: str = "She ___ to school yesterday.") -> QuestionRecord:
    return QuestionRecord(
        id=f"gr.past_simple.{n:012x}",
        skill="grammar",
        skill_id="grammar.past_simple",
        level=CefrLevel.A1,
        topic="daily_life",
        point="past_simple",
        difficulty=Difficulty.EASY,
        qtype=QuestionType.MCQ,
        instruction="Choose the correct form.",
        prompt=f"{prompt} ({n})",
        options=[OptionRecord(id="a", text="goes"), OptionRecord(id="b", text="went")],
        answer={"option": "b"},
        explanation="'Yesterday' is finished past time: past simple.",
        explanation_vi="Quá khứ đơn.",
        source=SRC,
        quality=0.9,
    )


def _listening() -> tuple[PassageRecord, QuestionRecord]:
    passage = PassageRecord(
        id="ls.s.000000000001",
        skill="listening",
        level=CefrLevel.A1,
        topic="daily_life",
        title="Listen to the sentence",
        text="She looked surprised at the letter.",
        audio="ls/00/ls.s.000000000001.ogg",
        source=SRC,
        quality=0.9,
    )
    question = QuestionRecord(
        id="ls.dictation.000000000001",
        skill="listening",
        skill_id="listening.comprehension",
        level=CefrLevel.A1,
        topic="daily_life",
        point="dictation",
        difficulty=Difficulty.MEDIUM,
        qtype=QuestionType.DICTATION,
        instruction="Write what you hear.",
        prompt="Write the sentence.",
        options=[],
        answer={"text": "She looked surprised at the letter."},
        explanation="You heard the whole sentence.",
        passage_id=passage.id,
        source=SRC,
        quality=0.9,
    )
    return passage, question


def _import(client, bank_dir) -> dict:
    factory = client.app.state.container.uow_factory()._session_factory
    return import_bank(factory, bank_dir, log=lambda _: None, seed=1)


@pytest.fixture
def bank(client, tmp_path):
    root = tmp_path / "bank"
    write_skill("grammar", [_grammar(i) for i in range(12)], bank_dir=root)
    passage, question = _listening()
    write_skill("listening", [question], [passage], bank_dir=root)
    _import(client, root)
    return root


@pytest.fixture
def users(client):
    return {role: create_user(client, role) for role in ("admin", "teacher", "student")}


# --- role x endpoint ------------------------------------------------------------------------

ADMIN_ONLY = [("GET", "/api/v1/admin/users"), ("GET", "/api/v1/admin/stats")]
TEACHER_AND_ADMIN = [
    ("GET", "/api/v1/teacher/students"),
    ("GET", "/api/v1/bank/grammar/review"),
]
EVERY_ROLE = [
    ("GET", "/api/v1/learner/mastery"),
    ("GET", "/api/v1/learner/attempts"),
    ("GET", "/api/v1/bank/grammar/facets"),
    ("GET", "/api/v1/auth/me"),
]


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [(m, p, {"admin"}) for m, p in ADMIN_ONLY]
    + [(m, p, {"admin", "teacher"}) for m, p in TEACHER_AND_ADMIN]
    + [(m, p, {"admin", "teacher", "student"}) for m, p in EVERY_ROLE],
)
def test_role_matrix(client, users, method, path, allowed):
    for role, (headers, _) in users.items():
        r = client.request(method, path, headers=headers)
        expected = 200 if role in allowed else 403
        assert r.status_code == expected, (role, path, r.text)
        if expected == 403:
            assert r.json()["error"]["code"] == "forbidden"
    assert client.request(method, path).status_code == 401  # nobody signed in


def test_the_profile_tells_the_web_app_the_role(client, users):
    for role, (headers, _) in users.items():
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == role


# --- privilege escalation --------------------------------------------------------------------


def test_nobody_can_pick_their_own_role(client, users):
    # at sign-up: unknown fields are rejected, a role in the body is never read
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "sneaky@example.com",
            "password": "correct horse",
            "display_name": "Sneaky",
            "role": "admin",
        },
    )
    assert r.status_code == 422
    student, student_id = users["student"]
    teacher, teacher_id = users["teacher"]
    for headers, uid in ((student, student_id), (teacher, teacher_id)):
        r = client.patch(f"/api/v1/admin/users/{uid}", json={"role": "admin"}, headers=headers)
        assert r.status_code == 403
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] != "admin"
    # the dev-only header never grants a role (and is off unless explicitly enabled)
    r = client.get("/api/v1/admin/users", headers={"X-Learner-Id": users["admin"][1]})
    assert r.status_code == 401


def test_admin_changes_roles_but_not_their_own(client, users):
    admin, admin_id = users["admin"]
    student, student_id = users["student"]
    r = client.patch(f"/api/v1/admin/users/{admin_id}", json={"role": "student"}, headers=admin)
    assert r.status_code == 403  # no self-demotion, no lock-out
    r = client.patch(f"/api/v1/admin/users/{admin_id}", json={"is_active": False}, headers=admin)
    assert r.status_code == 403
    r = client.patch(
        f"/api/v1/admin/users/{student_id}", json={"email": "x@example.com"}, headers=admin
    )
    assert r.status_code == 422  # only role and status can change
    r = client.patch(f"/api/v1/admin/users/{student_id}", json={"role": "teacher"}, headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "teacher"
    # the same session gets the new rights on its next request: the role is read every time
    assert client.get("/api/v1/teacher/students", headers=student).status_code == 200
    assert (
        client.patch(
            "/api/v1/admin/users/nope", json={"role": "teacher"}, headers=admin
        ).status_code
        == 404
    )


def test_admin_lists_and_searches_users_with_their_totals(client, users):
    admin, _ = users["admin"]
    student, student_id = users["student"]
    body = client.get("/api/v1/admin/users", headers=admin).json()
    assert body["total"] == 3
    assert {u["role"] for u in body["users"]} == {"admin", "teacher", "student"}
    only = client.get("/api/v1/admin/users?role=student", headers=admin).json()
    assert [u["user_id"] for u in only["users"]] == [student_id]
    found = client.get("/api/v1/admin/users?q=STUDENT-", headers=admin).json()  # e-mail, any case
    assert found["total"] == 1 and found["users"][0]["email"].startswith("student-")
    detail = client.get(f"/api/v1/admin/users/{student_id}", headers=admin).json()
    assert detail["attempts"] == 0 and detail["is_active"] is True
    assert "password" not in str(detail).lower()  # no hashes or tokens in admin views
    stats = client.get("/api/v1/admin/stats", headers=admin).json()
    assert stats["users"]["student"]["active"] == 1
    assert stats["system"]["prompt_versions"]


# --- account status and sessions -------------------------------------------------------------


def test_a_disabled_account_is_locked_out_at_once(client, users):
    admin, _ = users["admin"]
    student, student_id = users["student"]
    r = client.patch(f"/api/v1/admin/users/{student_id}", json={"is_active": False}, headers=admin)
    assert r.status_code == 200 and r.json()["is_active"] is False
    # its sessions were revoked, and it cannot sign in again (right password or not)
    assert client.get("/api/v1/learner/mastery", headers=student).status_code == 401
    email = r.json()["email"]
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct horse"})
    assert login.status_code == 403 and login.json()["error"]["code"] == "account_disabled"
    wrong = client.post("/api/v1/auth/login", json={"email": email, "password": "not it at all"})
    assert wrong.status_code == 401  # a wrong password does not reveal the status
    client.patch(f"/api/v1/admin/users/{student_id}", json={"is_active": True}, headers=admin)
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct horse"})
    assert login.status_code == 200


def test_a_session_of_an_account_disabled_elsewhere_stops_working(client, users):
    """Disabled directly in the database (sessions left behind): refused on every request."""
    student, student_id = users["student"]
    with client.app.state.container.uow_factory() as uow:
        uow.users.set_active(student_id, False)
        uow.commit()
    r = client.get("/api/v1/learner/mastery", headers=student)
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_disabled"
    assert client.post("/api/v1/bank/answer", headers=student, json={}).status_code in (403, 422)


def test_invalid_and_expired_sessions(client, clock):
    headers = create_learner(client)
    assert client.get("/api/v1/learner/mastery", headers=headers).status_code == 200
    bad = {"Authorization": "Bearer forged-token"}
    assert client.get("/api/v1/learner/mastery", headers=bad).status_code == 401
    clock.advance(timedelta(days=31))
    r = client.get("/api/v1/learner/mastery", headers=headers)
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"]


# --- resource ownership (IDOR) ---------------------------------------------------------------


def test_teachers_see_only_their_students(client, users):
    admin, _ = users["admin"]
    teacher, teacher_id = users["teacher"]
    student, student_id = users["student"]
    other, other_id = create_user(client, "student")
    progress = f"/api/v1/teacher/students/{student_id}/progress"
    # not assigned yet: knowing the id is not enough
    assert client.get(progress, headers=teacher).status_code == 403
    assert client.get(f"{progress[:-9]}/attempts", headers=teacher).status_code == 403
    assert client.get("/api/v1/teacher/students", headers=teacher).json()["total"] == 0
    r = client.put(f"/api/v1/admin/users/{teacher_id}/students/{student_id}", headers=admin)
    assert r.status_code == 200 and r.json()["student_ids"] == [student_id]
    body = client.get(progress, headers=teacher).json()
    assert body["student"]["user_id"] == student_id and "skills" in body["mastery"]
    assert (
        client.get(f"/api/v1/teacher/students/{student_id}/attempts", headers=teacher).json() == []
    )
    listed = client.get("/api/v1/teacher/students", headers=teacher).json()
    assert [u["user_id"] for u in listed["users"]] == [student_id]
    # still not the other student
    other_progress = f"/api/v1/teacher/students/{other_id}/progress"
    assert client.get(other_progress, headers=teacher).status_code == 403
    # a student can never read another student, nor themselves through this door
    assert client.get(other_progress, headers=student).status_code == 403
    assert client.get(progress, headers=other).status_code == 403
    # an admin reads anyone
    assert client.get(other_progress, headers=admin).status_code == 200
    # only a teacher can follow, only a student can be followed
    bad = client.put(f"/api/v1/admin/users/{student_id}/students/{other_id}", headers=admin)
    assert bad.status_code == 422
    client.delete(f"/api/v1/admin/users/{teacher_id}/students/{student_id}", headers=admin)
    assert client.get(progress, headers=teacher).status_code == 403


def test_learners_only_ever_reach_their_own_records(client):
    a = create_learner(client)
    b = create_learner(client)
    conv = client.post("/api/v1/conversations", json={"scenario_id": "cv.cafe.001"}, headers=a)
    assert conv.status_code == 201, conv.text
    cid = conv.json()["id"]
    assert client.get(f"/api/v1/conversations/{cid}", headers=a).status_code == 200
    # another learner gets "not found", not the conversation (nor a hint that it exists)
    assert client.get(f"/api/v1/conversations/{cid}", headers=b).status_code == 404
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"text": "hi"}, headers=b)
    assert r.status_code == 404
    r = client.post(
        "/api/v1/tutor/explain", json={"attempt_id": cid, "mistake_index": 0}, headers=b
    )
    assert r.status_code == 404


# --- the question bank ----------------------------------------------------------------------


def test_students_answer_but_only_reviewers_manage_questions(client, users, bank):
    student, _ = users["student"]
    teacher, teacher_id = users["teacher"]
    qid = f"gr.past_simple.{0:012x}"
    r = client.post(
        "/api/v1/bank/answer", json={"question_id": qid, "answer": "b"}, headers=student
    )
    assert r.status_code == 200 and r.json()["correct"]
    page = client.get("/api/v1/bank/grammar/review", headers=teacher).json()
    assert page["total"] == 12 and page["questions"][0]["answer"] == {"option": "b"}
    assert client.get("/api/v1/bank/grammar/review", headers=student).status_code == 403
    for status in ("approved", "disabled"):
        r = client.patch(f"/api/v1/bank/questions/{qid}", json={"status": status}, headers=student)
        assert r.status_code == 403
    r = client.patch(f"/api/v1/bank/questions/{qid}", json={"status": "draft"}, headers=teacher)
    assert r.status_code == 422
    r = client.patch(f"/api/v1/bank/questions/{qid}", json={"status": "disabled"}, headers=teacher)
    assert r.status_code == 200
    assert r.json()["status"] == "disabled" and r.json()["reviewed_by"] == teacher_id
    # a disabled question is neither served nor answerable (its answer stays hidden)
    r = client.post(
        "/api/v1/bank/answer", json={"question_id": qid, "answer": "b"}, headers=student
    )
    assert r.status_code == 404
    sets = client.post("/api/v1/bank/grammar/sets", json={"count": 20}, headers=student).json()
    assert qid not in {q["id"] for q in sets["questions"]}


def test_review_decisions_survive_a_new_import(client, users, bank):
    teacher, _ = users["teacher"]
    approved, disabled = f"gr.past_simple.{1:012x}", f"gr.past_simple.{2:012x}"
    for qid, status in ((approved, "approved"), (disabled, "disabled")):
        client.patch(f"/api/v1/bank/questions/{qid}", json={"status": status}, headers=teacher)
    # a new build: question 2 is rewritten, question 1 is the same
    items = [_grammar(i) for i in range(12)]
    items[2] = _grammar(2, "They ___ home late last night.")
    write_skill("grammar", items, bank_dir=bank)
    _import(client, bank)
    page = client.get("/api/v1/bank/grammar/review?limit=100", headers=teacher).json()
    by_id = {q["id"]: q for q in page["questions"]}
    assert by_id[approved]["status"] == "approved" and by_id[approved]["reviewed_by"]
    # changed content: the old decision no longer applies; it needs a new review
    assert by_id[disabled]["status"] == "validated" and by_id[disabled]["reviewed_by"] is None


def test_a_transcript_only_after_answering(client, bank):
    h = create_learner(client)
    passage_id = "ls.s.000000000001"
    r = client.get(f"/api/v1/bank/passages/{passage_id}/transcript", headers=h)
    assert r.status_code == 409  # it holds the dictation answer
    client.post(
        "/api/v1/bank/answer",
        json={"question_id": "ls.dictation.000000000001", "answer": "she looked"},
        headers=h,
    )
    r = client.get(f"/api/v1/bank/passages/{passage_id}/transcript", headers=h)
    assert r.status_code == 200 and "surprised" in r.json()["transcript"]
