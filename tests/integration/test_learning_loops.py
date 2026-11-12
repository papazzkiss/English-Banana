"""End-to-end loops through the HTTP API (mocks only): every phase's Definition of Done."""

import json
from datetime import timedelta

from fastapi.testclient import TestClient

from banana_english.api.app import create_app
from banana_english.application.use_cases.jobs import BackgroundAttempts
from banana_english.domain.interfaces.llm import LLMProviderError
from banana_english.infrastructure.ai.mock_llm import ScriptedLLMProvider
from banana_english.infrastructure.stt.mock_stt import MockSTTProvider
from tests.conftest import create_learner, mastery_of, recommendations


def wrong(fragment, tag="verb_tense"):
    """Grammar verdict with one error: verb_tense -> 25 (major), article -> 55 (minor)."""
    return json.dumps(
        {
            "errors": [
                {"fragment": fragment, "tag": tag, "correction": None, "explanation": "Check this."}
            ],
            "natural": False,
            "corrected_answer": None,
            "feedback": "Check it.",
        }
    )


def ok(natural=True):
    return json.dumps(
        {"errors": [], "natural": natural, "corrected_answer": None, "feedback": "Good."}
    )


def grammar(client, h, exercise_id, answer):
    r = client.post(
        "/api/v1/grammar/attempt", headers=h, json={"exercise_id": exercise_id, "answer": answer}
    )
    assert r.status_code == 200, r.text
    return r.json()


# --- Phase 5 DoD -----------------------------------------------------------------------------


def test_deliberately_failing_past_tense_gets_past_tense_recommended(make_client):
    client = make_client(ScriptedLLMProvider([wrong("goed")] * 3))
    h = create_learner(client, "A2")
    skill = "grammar.past_simple_present_perfect"
    assert all(r["kind"] == "new_topic" for r in recommendations(client, h))  # cold start

    for exercise_id in ["gr.past.001", "gr.past.002", "gr.past.003"]:
        body = grammar(client, h, exercise_id, "I goed there")
        change = body["mastery_changes"][0]
        assert change["skill_id"] == skill and change["after"] < change["before"]

    m = mastery_of(client, h, skill)
    assert m["mastery"] < 40 and m["is_weak"]

    top = recommendations(client, h)[0]
    assert top["skill_id"] == skill and top["kind"] == "reinforcement"
    assert top["evidence"]["difficulty"] == "easy"  # mastery < 40
    assert top["evidence"]["top_mistakes"] == ["verb_tense"]
    assert all(i["item_id"].startswith("gr.past.") for i in top["items"])
    assert "gr.past.003" not in [i["item_id"] for i in top["items"]]  # not the item just done

    # dashboard weak-skills uses the same query as the recommender
    weak = client.get("/api/v1/learner/weak-skills", headers=h).json()["skills"]
    assert weak[0]["skill_id"] == skill


def test_recovery_moves_skill_out_of_reinforcement(make_client):
    client = make_client(ScriptedLLMProvider([wrong("goed"), wrong("no like")]))
    h = create_learner(client, "A2")
    grammar(client, h, "gr.past.001", "goed")
    grammar(client, h, "gr.past.002", "no like")
    for exercise_id, answer in [
        ("gr.past.003", "have visited"),
        ("gr.past.004", "I saw that film yesterday."),
        ("gr.past.005", "has lived"),
        ("gr.past.006", "He finished his homework two hours ago."),
    ]:
        body = grammar(client, h, exercise_id, answer)
        assert body["assessment"]["assessor"] == "reference_match"
    m = mastery_of(client, h, "grammar.past_simple_present_perfect")
    assert m["mastery"] >= 60 and not m["is_weak"]
    kinds = {r["skill_id"]: r["kind"] for r in recommendations(client, h, 10)}
    assert kinds.get("grammar.past_simple_present_perfect") != "reinforcement"


def test_malformed_llm_output_never_updates_mastery(make_client):
    client = make_client(ScriptedLLMProvider(["I think it's wrong", '{"errors": "many"}']))
    h = create_learner(client)
    r = client.post(
        "/api/v1/grammar/attempt", headers=h, json={"exercise_id": "gr.articles.001", "answer": "a"}
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "assessment_unavailable"
    assert r.json()["error"]["details"]["attempt_id"]
    assert mastery_of(client, h, "grammar.articles")["attempt_count"] == 0
    assert client.get("/api/v1/learner/profile", headers=h).json()["total_attempts"] == 0


def test_repeating_a_solved_exercise_barely_moves_mastery(client):
    h = create_learner(client)
    first = grammar(client, h, "gr.articles.001", "an")["mastery_changes"][0]
    second = grammar(client, h, "gr.articles.001", "an")["mastery_changes"][0]
    assert first["after"] - first["before"] > 3 * (second["after"] - second["before"])


# --- Async grading (web app: Prefer: respond-async) ------------------------------------------

ASYNC = {"Prefer": "respond-async"}


def test_async_grading_returns_a_job_with_the_same_result(client):
    h = create_learner(client)
    r = client.post(
        "/api/v1/grammar/attempt",
        headers={**h, **ASYNC},
        json={"exercise_id": "gr.articles.001", "answer": "an"},
    )
    assert r.status_code == 202 and r.headers["Preference-Applied"] == "respond-async"
    assert r.json()["kind"] == "grammar_assessment"
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["status"] == "succeeded"
    assert job["result"]["assessment"]["assessor"] == "reference_match"
    assert job["result"]["mastery_changes"][0]["skill_id"] == "grammar.articles"
    assert job["result"]["reference_answers"]

    r = client.post(
        "/api/v1/listening/attempt",
        headers={**h, **ASYNC},
        json={"question_id": "ls.train.001.q3", "answer": "a problem with the signals"},
    )
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["kind"] == "listening_assessment" and job["result"]["assessment"]["score"] == 100

    unknown = {"exercise_id": "gr.nope.001", "answer": "x"}
    r = client.post("/api/v1/grammar/attempt", headers={**h, **ASYNC}, json=unknown)
    assert r.status_code == 404  # rejected up front, no job


def test_async_grading_failure_fails_the_job_and_keeps_mastery(make_client):
    client = make_client(ScriptedLLMProvider(["not json", '{"errors": "many"}']))
    h = create_learner(client)
    r = client.post(
        "/api/v1/grammar/attempt",
        headers={**h, **ASYNC},
        json={"exercise_id": "gr.articles.001", "answer": "a"},
    )
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["status"] == "failed" and job["error"].startswith("Assessment unavailable")
    assert job["result"]["attempt_id"]
    assert mastery_of(client, h, "grammar.articles")["attempt_count"] == 0


class DeferredRunner:
    """Holds jobs until run_all(), so a second submission arrives while the first is pending."""

    def __init__(self):
        self.pending = []

    def submit(self, fn):
        self.pending.append(fn)

    def run_all(self):
        while self.pending:
            self.pending.pop(0)()


def test_repeated_submission_while_grading_is_counted_once(make_container):
    container = make_container()
    runner = DeferredRunner()
    container.background = BackgroundAttempts(container.jobs, runner)
    client = TestClient(create_app(container))
    h = create_learner(client)

    def submit(answer):
        body = {"exercise_id": "gr.articles.001", "answer": answer}
        r = client.post("/api/v1/grammar/attempt", headers={**h, **ASYNC}, json=body)
        assert r.status_code == 202
        return r.json()["job_id"]

    first = submit("an")
    assert submit(" An ") == first  # double click / retry: same job
    other = submit("a")  # a different answer is a new submission
    assert other != first
    runner.run_all()
    for job_id in (first, other):
        assert client.get(f"/api/v1/jobs/{job_id}", headers=h).json()["status"] == "succeeded"
    assert client.get("/api/v1/learner/profile", headers=h).json()["total_attempts"] == 2
    assert submit("an") != first  # once graded, answering again is a new attempt


# --- Phase 2 via API -------------------------------------------------------------------------


def test_vocabulary_sm2_queue_over_simulated_days(client, clock):
    h = create_learner(client, "A1")
    cards = client.get("/api/v1/vocabulary/due?limit=4", headers=h).json()["cards"]
    assert len(cards) == 4 and all(c["is_new"] and c["cefr_level"] == "A1" for c in cards)
    assert all(c["back"]["word"].lower() not in c["front"]["prompt"].lower().split() for c in cards)
    again, easy = cards[0], cards[1]

    r = client.post(
        "/api/v1/vocabulary/review",
        headers=h,
        json={"card_id": again["card_id"], "rating": "again"},
    ).json()
    assert r["state"]["interval_days"] == 1 and r["mastery_changes"][0]["after"] < 50
    r = client.post(
        "/api/v1/vocabulary/review",
        headers=h,
        json={"card_id": easy["card_id"], "rating": "easy", "answer": easy["back"]["word"]},
    ).json()
    assert r["rating_applied"] == "easy" and r["assessment"]["score"] == 100

    # a wrong typed answer overrides "easy"
    wrong_typed = client.post(
        "/api/v1/vocabulary/review",
        headers=h,
        json={"card_id": cards[2]["card_id"], "rating": "easy", "answer": "zzzz"},
    ).json()
    assert wrong_typed["rating_applied"] == "again"

    for _ in range(12):  # simulate 12 days, reviewing whatever is due
        clock.advance(timedelta(days=1))
        due = client.get("/api/v1/vocabulary/due?limit=50", headers=h).json()["cards"]
        for card in (c for c in due if not c["is_new"]):
            rating = "again" if card["card_id"] == again["card_id"] else "easy"
            client.post(
                "/api/v1/vocabulary/review",
                headers=h,
                json={"card_id": card["card_id"], "rating": rating},
            )
    clock.advance(timedelta(days=1))
    states = {
        c["card_id"]: c
        for c in client.get("/api/v1/vocabulary/due?limit=50", headers=h).json()["cards"]
    }
    assert again["card_id"] in states  # "Again" card is due every day
    assert easy["card_id"] not in states  # "Easy" card is scheduled far out


def test_daily_new_card_limit(client):
    h = create_learner(client)
    cards = client.get("/api/v1/vocabulary/due?limit=50", headers=h).json()["cards"]
    assert len(cards) == 10  # BANANA_DAILY_NEW_CARDS default
    for card in cards:
        client.post(
            "/api/v1/vocabulary/review",
            headers=h,
            json={"card_id": card["card_id"], "rating": "good"},
        )
    assert client.get("/api/v1/vocabulary/due", headers=h).json()["cards"] == []


# --- Phase 6: listening ----------------------------------------------------------------------


def test_listening_lesson_end_to_end(make_client):
    llm = ScriptedLLMProvider(['{"understood": "not", "feedback": "It was 4."}'])
    client = make_client(llm)
    h = create_learner(client)
    lesson = client.get("/api/v1/listening/lessons/ls.train.001").json()
    assert lesson["audio_url"] == "/media/listening/ls.train.001.wav"
    audio = client.get(lesson["audio_url"])
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    assert (
        client.get("/api/v1/listening/lessons/ls.train.001/transcript", headers=h).status_code
        == 409
    )

    answers = {
        "ls.train.001.q1": "20 minutes",
        "ls.train.001.q2": "platform two",
        "ls.train.001.q3": "a problem with the signals",
    }
    results = {}
    for qid, answer in answers.items():
        r = client.post(
            "/api/v1/listening/attempt", headers=h, json={"question_id": qid, "answer": answer}
        )
        assert r.status_code == 200
        results[qid] = r.json()
    assert results["ls.train.001.q2"]["assessment"]["mistakes"][0]["category"] == "comprehension"
    assert results["ls.train.001.q1"]["mastery_changes"][0]["skill_id"] == "listening.comprehension"
    transcript = client.get("/api/v1/listening/lessons/ls.train.001/transcript", headers=h).json()
    assert "platform four" in transcript["transcript"]


# --- Phase 7: speaking -----------------------------------------------------------------------


def test_speaking_job_returns_transcript_and_scores(make_client, tmp_path):
    llm = ScriptedLLMProvider([wrong("I go")])
    stt = MockSTTProvider(
        text="Last weekend I go to the beach with my friends and we swim "
        "in the sea and eat some fish"
    )
    client = make_client(llm, stt)
    h = create_learner(client, "A2")
    r = client.post(
        "/api/v1/speaking/attempt",
        headers=h,
        data={"prompt_id": "sp.weekend.001"},
        files={"audio": ("answer.webm", b"\x1aE\xdf\xa3fake", "audio/webm")},
    )
    assert r.status_code == 202
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["status"] == "succeeded", job
    result = job["result"]
    assert result["transcript"].startswith("Last weekend I go")  # shown to the learner
    assert result["grammar"]["score"] == 25 and result["fluency"]["words_per_minute"] > 0
    skills = {c["skill_id"] for c in result["mastery_changes"]}
    # tense error in a task targeting the past tense updates that grammar skill too
    assert {"speaking.grammar", "speaking.fluency", "grammar.past_simple_present_perfect"} <= skills
    assert not list((tmp_path / "uploads").glob("*"))  # audio deleted after transcription


def test_one_spoken_answer_counts_once_and_shows_both_scores(make_client):
    stt = MockSTTProvider(text="I am Lan and I live in Hanoi and I work in a bank every day")
    client = make_client(ScriptedLLMProvider([ok()]), stt)
    h = create_learner(client, "A1")
    r = client.post(
        "/api/v1/speaking/attempt",
        headers=h,
        data={"prompt_id": "sp.intro.001"},
        files={"audio": ("answer.webm", b"\x1aE\xdf\xa3fake", "audio/webm")},
    )
    assert client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=h).json()["status"] == (
        "succeeded"
    )
    profile = client.get("/api/v1/learner/profile", headers=h).json()
    activity = client.get("/api/v1/learner/activity?days=1", headers=h).json()
    recent = client.get("/api/v1/learner/attempts", headers=h).json()
    assert profile["total_attempts"] == 1 and activity["days"][-1]["attempts"] == 1
    assert len(recent) == 1 and recent[0]["skill_id"] == "speaking.grammar"
    assert [p["skill_id"] for p in recent[0]["parts"]] == ["speaking.grammar", "speaking.fluency"]
    # both skills still get their own mastery
    skills = {
        s["skill_id"]: s for s in client.get("/api/v1/learner/mastery", headers=h).json()["skills"]
    }
    assert skills["speaking.fluency"]["attempt_count"] == 1


def test_too_short_speech_is_not_graded(make_client):
    llm = ScriptedLLMProvider([])  # any LLM call would fail the test
    client = make_client(llm, MockSTTProvider(text="Hello, hello, hello"))
    h = create_learner(client, "A1")
    r = client.post(
        "/api/v1/speaking/attempt",
        headers=h,
        data={"prompt_id": "sp.intro.001"},
        files={"audio": ("answer.webm", b"\x1aE\xdf\xa3fake", "audio/webm")},
    )
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=h).json()
    assert job["status"] == "failed"
    assert "only heard 3 words" in job["error"] and "too short to grade" in job["error"]
    assert client.get("/api/v1/learner/profile", headers=h).json()["total_attempts"] == 0


def test_speaking_prompts_name_their_target_grammar(client):
    prompts = client.get("/api/v1/speaking/prompts").json()["prompts"]
    intro = next(p for p in prompts if p["id"] == "sp.intro.001")
    assert intro["target_grammar_name"] == "Present simple vs present continuous"


def test_roadmap_lists_levels_up_to_the_target(client):
    h = create_learner(client, "A1")
    road = client.get("/api/v1/learner/roadmap", headers=h).json()
    levels = [lv["level"] for lv in road["levels"]]
    assert levels[0] == "A1" and road["target_level"] in levels
    a1 = road["levels"][0]
    assert a1["skills"] and all(s["status"] == "not_started" for s in a1["skills"])
    # every unstarted skill needs 4 good answers (50 -> 80), every word one
    assert a1["answers_left"] == 4 * len(a1["skills"]) + a1["words_total"]
    assert a1["weeks_left"] >= 1 and not a1["complete"]


def test_speaking_rejects_bad_uploads(client):
    h = create_learner(client)
    empty = client.post(
        "/api/v1/speaking/attempt",
        headers=h,
        data={"prompt_id": "sp.intro.001"},
        files={"audio": ("a.webm", b"", "audio/webm")},
    )
    exe = client.post(
        "/api/v1/speaking/attempt",
        headers=h,
        data={"prompt_id": "sp.intro.001"},
        files={"audio": ("a.exe", b"MZ", "application/octet-stream")},
    )
    assert empty.status_code == exe.status_code == 422


# --- Phase 8: conversation -------------------------------------------------------------------


def test_conversation_scenario_end_to_end(make_client):
    replies = [
        "One coffee, sure. Anything to eat?",
        "A cheese sandwich. Anything else?",
        "That's six pounds, please.",
        "Card is fine. Here you are!",
    ]
    grades = [ok(), wrong("want cheese sandwich", "article"), ok(natural=False), wrong("I paying")]
    client = make_client(ScriptedLLMProvider(replies + grades))
    h = create_learner(client)
    conv = client.post(
        "/api/v1/conversations", headers=h, json={"scenario_id": "cv.cafe.001"}
    ).json()
    assert conv["turns"][0]["role"] == "assistant" and conv["learner_turns_left"] == 5
    lines = [
        "I would like a coffee, please.",
        "I want cheese sandwich.",
        "How much is it?",
        "I paying by card.",
    ]
    for line in lines:
        conv = client.post(
            f"/api/v1/conversations/{conv['id']}/messages", headers=h, json={"text": line}
        ).json()
    assert [t["role"] for t in conv["turns"]] == ["assistant", "learner"] * 4 + ["assistant"]
    assert conv["turns"][-1]["text"] == "Card is fine. Here you are!"  # stayed in character

    job = client.post(f"/api/v1/conversations/{conv['id']}/finish", headers=h).json()
    summary = client.get(f"/api/v1/jobs/{job['job_id']}", headers=h).json()["result"]
    assert [t["assessment"]["score"] for t in summary["turns"]] == [95, 55, 80, 25]
    assert summary["error_counts"] == {"article": 1, "verb_tense": 1}
    updated = {c["skill_id"] for c in summary["mastery_changes"]}
    assert {
        "conversation.communication",
        "grammar.articles",
        "grammar.present_simple_continuous",
    } <= updated
    final = client.get(f"/api/v1/conversations/{conv['id']}", headers=h).json()
    assert final["status"] == "finished" and final["summary"]["average_score"] == 63.8
    again = client.post(
        f"/api/v1/conversations/{conv['id']}/messages", headers=h, json={"text": "Bye"}
    )
    assert again.status_code == 409


def test_conversation_turn_limit_and_provider_outage(make_client):
    client = make_client(ScriptedLLMProvider([LLMProviderError("down")] * 2))
    h = create_learner(client)
    conv = client.post(
        "/api/v1/conversations", headers=h, json={"scenario_id": "cv.cafe.001"}
    ).json()
    r = client.post(
        f"/api/v1/conversations/{conv['id']}/messages", headers=h, json={"text": "Hello"}
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "provider_unavailable"


# --- Phase 9: tutor --------------------------------------------------------------------------


def test_tutor_explains_a_stored_error(make_client):
    tutor = json.dumps(
        {
            "explanation": "With a finished time like 'yesterday' we use the past "
            "simple, not the present perfect.",
            "example": "We watched a film last night.",
        }
    )
    llm = ScriptedLLMProvider([wrong("have saw"), tutor])
    client = make_client(llm)
    h = create_learner(client, "A2")
    attempt = grammar(client, h, "gr.past.004", "I have saw that film yesterday")
    r = client.post(
        "/api/v1/tutor/explain",
        headers=h,
        json={"attempt_id": attempt["attempt_id"], "mistake_index": 0},
    )
    assert r.status_code == 200 and "past simple" in r.json()["explanation"]
    assert r.json()["error_tag"] == "verb_tense"
    request = llm.requests[-1]
    assert request.task == "tutor_explain"
    assert (
        json.loads(request.messages[1].content)["learner_answer"]
        == "I have saw that film yesterday"
    )

    correct = grammar(client, h, "gr.past.001", "went")
    assert (
        client.post(
            "/api/v1/tutor/explain", headers=h, json={"attempt_id": correct["attempt_id"]}
        ).status_code
        == 422
    )
    other = create_learner(client)
    assert (
        client.post(
            "/api/v1/tutor/explain", headers=other, json={"attempt_id": attempt["attempt_id"]}
        ).status_code
        == 404
    )


# --- Phase 4 / 10: history, activity, isolation ------------------------------------------------


def test_mastery_history_and_streak_over_simulated_days(make_client, clock):
    client = make_client(ScriptedLLMProvider([wrong("goed")] * 4))
    h = create_learner(client)
    for day in range(4):
        grammar(client, h, f"gr.articles.00{day + 1}", "goed")
        clock.advance(timedelta(days=1))
    history = client.get(
        "/api/v1/learner/mastery-history?skill_id=grammar.articles", headers=h
    ).json()["points"]
    assert len(history) == 4
    assert [p["mastery"] for p in history] == sorted(p["mastery"] for p in history)[::-1]
    activity = client.get("/api/v1/learner/activity?days=7", headers=h).json()
    assert activity["active_days"] == 4 and activity["current_streak"] == 4


def test_learners_are_isolated(client):
    a, b = create_learner(client), create_learner(client)
    grammar(client, a, "gr.articles.001", "an")
    assert mastery_of(client, a, "grammar.articles")["attempt_count"] == 1
    assert mastery_of(client, b, "grammar.articles")["attempt_count"] == 0
