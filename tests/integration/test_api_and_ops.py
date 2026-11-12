import json
import uuid

from banana_english.application.services.prompts import GRAMMAR_ASSESSMENT_VERSION
from banana_english.config.settings import PROJECT_ROOT
from banana_english.infrastructure.ai.mock_llm import ScriptedLLMProvider
from tests.conftest import create_learner, create_user

OPENAPI_SNAPSHOT = PROJECT_ROOT / "docs/openapi.json"

REQUIRED_ROUTES = {
    ("post", "/api/v1/auth/register"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/logout"),
    ("get", "/api/v1/auth/me"),
    ("get", "/api/v1/learner/profile"),
    ("get", "/api/v1/learner/mastery"),
    ("get", "/api/v1/learner/weak-skills"),
    ("get", "/api/v1/learner/mastery-history"),
    ("get", "/api/v1/learner/activity"),
    ("get", "/api/v1/recommendation/next"),
    ("get", "/api/v1/vocabulary/due"),
    ("post", "/api/v1/vocabulary/review"),
    ("post", "/api/v1/grammar/attempt"),
    ("get", "/api/v1/listening/lessons"),
    ("post", "/api/v1/listening/attempt"),
    ("post", "/api/v1/speaking/attempt"),
    ("post", "/api/v1/conversations"),
    ("post", "/api/v1/conversations/{conversation_id}/messages"),
    ("post", "/api/v1/conversations/{conversation_id}/finish"),
    ("post", "/api/v1/tutor/explain"),
    ("get", "/api/v1/jobs/{job_id}"),
    ("post", "/api/v1/monkey/chat"),
    ("post", "/api/v1/monkey/transcribe"),
    ("post", "/api/v1/monkey/speech"),
    ("get", "/api/v1/features"),
    ("get", "/health"),
}


def test_every_phase_endpoint_exists(client):
    spec = client.get("/openapi.json").json()
    assert {(m, p) for p, ops in spec["paths"].items() for m in ops} >= REQUIRED_ROUTES


def test_openapi_snapshot_is_up_to_date(client):
    """docs/openapi.json is the published contract. Regenerate: scripts/export_openapi.py."""
    assert json.loads(OPENAPI_SNAPSHOT.read_text()) == client.get("/openapi.json").json()


def test_health_and_metrics(client):
    assert client.get("/health").json() == {"status": "ok"}
    # public through the web proxy: no configuration for anonymous users or learners
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    student, _ = create_user(client, "student")
    assert client.get("/api/v1/health", headers=student).json() == {"status": "ok"}
    admin, _ = create_user(client, "admin")
    details = client.get("/api/v1/health", headers=admin).json()
    assert details["prompt_versions"]["grammar"] == GRAMMAR_ASSESSMENT_VERSION
    assert client.get("/metrics").status_code == 200


def test_exercise_payloads_never_leak_answers(client):
    h = create_learner(client)
    ex = client.get("/api/v1/grammar/exercises/gr.articles.001").json()
    assert "accepted_answers" not in ex and "an" not in json.dumps(ex).split('"')
    lesson = client.get("/api/v1/listening/lessons/ls.train.001").json()
    assert "transcript" not in lesson and "accepted_answers" not in json.dumps(lesson)
    cards = client.get("/api/v1/vocabulary/due?limit=5", headers=h).json()["cards"]
    for c in cards:
        assert c["back"]["word"].lower() not in c["front"]["prompt"].lower().split()


def test_error_envelope_and_validation(client):
    r = client.get("/api/v1/learner/profile", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert client.get("/api/v1/learner/mastery").status_code == 401
    # the dev-only header is ignored unless explicitly enabled
    r = client.get("/api/v1/learner/mastery", headers={"X-Learner-Id": str(uuid.uuid4())})
    assert r.status_code == 401
    h = create_learner(client)
    bad = [
        client.post(
            "/api/v1/grammar/attempt",
            headers=h,
            json={"exercise_id": "gr.articles.001", "answer": "x" * 301},
        ),
        client.post(
            "/api/v1/grammar/attempt",
            headers=h,
            json={"exercise_id": "gr.articles.001", "answer": "an", "score": 100},
        ),
        client.post(
            "/api/v1/vocabulary/review",
            headers=h,
            json={"card_id": "apple.noun", "rating": "perfect"},
        ),
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "a@b.co",
                "password": "longenough",
                "display_name": "A",
                "current_level": "D1",
            },
        ),
        client.get("/api/v1/recommendation/next?n=0", headers=h),
    ]
    assert {r.status_code for r in bad} == {422}
    missing = client.post(
        "/api/v1/grammar/attempt", headers=h, json={"exercise_id": "gr.articles.999", "answer": "a"}
    )
    assert missing.status_code == 404


def test_request_id_is_propagated_into_llm_audit_log(make_client, make_container):
    llm = ScriptedLLMProvider(
        [
            '{"errors": [{"fragment": "a", "tag": "article", "correction": '
            '"an", "explanation": "Use an."}], "natural": false, '
            '"corrected_answer": "an", "feedback": "Use an."}'
        ]
    )
    from fastapi.testclient import TestClient

    from banana_english.api.app import create_app

    container = make_container(llm)
    client = TestClient(create_app(container))
    h = create_learner(client)
    r = client.post(
        "/api/v1/grammar/attempt",
        headers={**h, "X-Request-ID": "trace-123"},
        json={"exercise_id": "gr.articles.001", "answer": "a"},
    )
    assert r.headers["X-Request-ID"] == "trace-123"
    body = r.json()
    assert body["assessment"]["prompt_version"] == GRAMMAR_ASSESSMENT_VERSION
    rows = container.llm_calls.recent(5)
    assert (
        rows[0]["request_id"] == "trace-123"
        and rows[0]["prompt_version"] == GRAMMAR_ASSESSMENT_VERSION
    )
    assert "Use an." in rows[0]["response_text"]
    metrics = client.get("/metrics").text
    assert (
        'banana_llm_call_seconds_count{provider="scripted-mock",task="grammar_assessment"}'
        in metrics
    )
    assert 'banana_assessments_total{assessor="llm",module="grammar"}' in metrics
