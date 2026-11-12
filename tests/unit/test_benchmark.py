"""Model benchmark: dataset, request capture, checks, statistics and a full run against a fake
Ollama (no network)."""

from __future__ import annotations

import csv
import json

import httpx
import pytest

from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.services.monkey import MonkeyChat, MonkeyTurn
from banana_english.application.services.prompts import GRAMMAR_ASSESSMENT_SYSTEM
from banana_english.application.services.structured_llm import StructuredLLM
from banana_english.benchmark.client import OllamaBenchClient
from banana_english.benchmark.dataset import CATEGORIES, load_dataset, select, validate
from banana_english.benchmark.report import recommendation, write_all
from banana_english.benchmark.runner import BenchConfig, ModelSpec, run_benchmark
from banana_english.benchmark.scoring import (
    DIMENSIONS,
    dimension_scores,
    overall_score,
    paired_difference,
    percentile,
    performance_scores,
    quality_score,
    run_check,
)
from banana_english.benchmark.tasks import Parsed, _Recorder, build_request, parse_output
from banana_english.config.settings import Settings
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository


@pytest.fixture(scope="module")
def repo():
    return JsonContentRepository(Settings().content_dir)


@pytest.fixture(scope="module")
def tests():
    return load_dataset()["tests"]


# --- dataset ---------------------------------------------------------------------------------


def test_dataset_is_valid_and_covers_every_category_and_dimension(tests):
    assert validate(tests) == []
    assert 40 <= len(tests) <= 50
    assert {t["category"] for t in tests} == set(CATEGORIES)
    assert {c["dim"] for t in tests for c in t["checks"]} == set(DIMENSIONS)
    quick = select(tests, "quick")
    assert sorted(t["category"] for t in quick) == sorted(CATEGORIES)  # one per category
    with pytest.raises(ValueError):
        select(tests, "huge")


def test_every_test_builds_a_request(tests, repo):
    for t in tests:
        request = build_request(t, repo)
        assert request.messages and request.max_output_tokens > 0, t["id"]


def test_requests_are_the_production_requests(tests, repo):
    gc = next(t for t in tests if t["id"] == "gc.01")
    req = build_request(gc, repo)
    expected = LLMGrammarAssessmentEngine(StructuredLLM(_Recorder("{}"))).build_request(
        repo.get_exercise("gr.past.004"), "I seen that film yesterday."
    )
    assert req == expected
    assert req.messages[0].content == GRAMMAR_ASSESSMENT_SYSTEM

    vs = next(t for t in tests if t["id"] == "vs.01")
    rec = _Recorder("ok")
    MonkeyChat(rec).reply(
        "A2", [MonkeyTurn("learner", "I goed to the park yesterday with my dog.")]
    )
    assert build_request(vs, repo) == rec.requests[0]


# --- parsing and checks ----------------------------------------------------------------------

GOOD_VERDICT = json.dumps(
    {
        "errors": [
            {
                "fragment": "seen",
                "tag": "verb_tense",
                "correction": "saw",
                "explanation": "Use the past simple 'saw' with yesterday.",
            }
        ],
        "natural": False,
        "corrected_answer": "I saw that film yesterday.",
        "feedback": "Use the past simple with yesterday.",
    }
)


def _gc01(tests):
    return next(t for t in tests if t["id"] == "gc.01")


def test_grammar_reply_is_parsed_like_production_and_scored(tests, repo):
    t = _gc01(tests)
    parsed = parse_output(t, GOOD_VERDICT, repo)
    assert parsed.contract_ok and parsed.fields["is_correct"] is False
    results = [run_check(c, parsed) for c in t["checks"]]
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_invalid_json_fails_the_contract_and_every_field_check(tests, repo):
    t = _gc01(tests)
    parsed = parse_output(t, "The answer is wrong, use saw.", repo)
    assert not parsed.contract_ok
    by_type = {r.type: r for r in (run_check(c, parsed) for c in t["checks"])}
    assert not by_type["contract"].passed
    assert not by_type["verdict"].passed and not by_type["correction"].passed


def test_ungrounded_fragment_is_rejected_by_the_production_contract(tests, repo):
    bad = json.loads(GOOD_VERDICT)
    bad["errors"][0]["fragment"] = "have seen"  # not in the learner's answer
    parsed = parse_output(_gc01(tests), json.dumps(bad), repo)
    assert not parsed.contract_ok


@pytest.mark.parametrize(
    ("check", "text", "passed"),
    [
        ({"type": "max_sentences", "max": 2}, "One. Two? Three!", False),
        ({"type": "max_sentences", "max": 3}, "One. Two? Three!", True),
        ({"type": "max_words", "max": 3}, "one two three four", False),
        ({"type": "contains_any", "terms": ["re:\\bwent\\b"]}, "We say went.", True),
        ({"type": "contains_all", "groups": [["a"], ["zzz"]]}, "a b", False),
        ({"type": "not_contains", "terms": ["as an ai"]}, "As an AI, I think", False),
        ({"type": "has_question", "dim": "conversation"}, "Nice! And you?", True),
        ({"type": "regex", "pattern": "\\bfewer \\w+s\\b"}, "fewer apples", True),
        ({"type": "simple_words"}, "internationalization characteristically", False),
        ({"type": "not_repetitive"}, "I like it I like it I like it", False),
        ({"type": "not_repetitive"}, '"has been to" vs "has been to" and "has been to"', True),
        ({"type": "simple_words"}, "That's great! Congratulations! How did you feel?", True),
        ({"type": "differs_from", "text": "I saw it."}, "I saw it yesterday", False),
    ],
)
def test_text_checks(check, text, passed):
    result = run_check({"dim": "naturalness", **check}, Parsed(text, text))
    assert result.passed is passed


def test_voice_checks_look_at_what_would_be_spoken():
    raw = "Great job! (Tip: we say 'went'.) Where did you go? 🍌"
    parsed = Parsed(raw, raw)
    assert run_check(
        {"type": "max_sentences", "field": "spoken", "max": 2, "dim": "x"}, parsed
    ).passed
    assert not run_check({"type": "plain_speech", "dim": "x"}, parsed).passed  # emoji
    leak = Parsed("Okay, the user wants a greeting. Hello!", "Hello!")
    assert not run_check({"type": "no_reasoning_leak", "dim": "x"}, leak).passed


# --- statistics ------------------------------------------------------------------------------


def test_percentile_matches_linear_interpolation():
    values = [1, 2, 3, 4, 10]
    assert percentile(values, 50) == 3
    assert percentile(values, 95) == pytest.approx(8.8)
    assert percentile([], 50) is None


def test_scores_quality_performance_overall():
    dims = dict.fromkeys(DIMENSIONS, 80.0)
    dims["grammar"] = None  # a dimension without checks is skipped, not zero
    assert quality_score(dims) == 80.0
    perf = performance_scores({"fast": (2.0, 20.0), "slow": (4.0, 10.0)})
    assert perf == {"fast": 100.0, "slow": 50.0}
    assert overall_score(80.0, 100.0) == pytest.approx(82.0)
    assert dimension_scores([])["grammar"] is None


# --- full run against a fake Ollama ---------------------------------------------------------


LIB_TEMPLATE = "{{ .Prompt }} /no_think"


def fake_ollama(installed: dict[str, str], reply_for, templates: dict[str, str] | None = None):
    """installed: name -> quantization. reply_for(body) -> reply text."""
    calls = []
    templates = dict(templates or {})
    created = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path == "/api/version":
            return httpx.Response(200, json={"version": "test"})
        if path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": 5e9} for n in installed]}
            )
        if path == "/api/show":
            quant = installed[body["model"]]
            return httpx.Response(
                200,
                json={
                    "details": {"quantization_level": quant, "parameter_size": "8.2B"},
                    "template": templates.get(body["model"], LIB_TEMPLATE),
                    "parameters": 'stop                           "<|im_end|>"\ntop_k 20',
                },
            )
        if path == "/api/create":
            created[body["model"]] = body
            installed[body["model"]] = installed[body["from"]]
            templates[body["model"]] = body["template"]
            return httpx.Response(200, json={"status": "success"})
        if path == "/api/ps":
            return httpx.Response(
                200, json={"models": [{"name": n, "size": 6e9, "size_vram": 0} for n in installed]}
            )
        if path == "/api/generate":
            return httpx.Response(200, json={"done": True})
        if path == "/api/chat":
            calls.append(body)
            text = reply_for(body)
            half = len(text) // 2
            lines = [
                {"message": {"content": text[:half]}, "done": False},
                {"message": {"content": text[half:]}, "done": False},
                {
                    "message": {"content": ""},
                    "done": True,
                    "eval_count": 20,
                    "eval_duration": 1_000_000_000,
                    "prompt_eval_count": 100,
                    "prompt_eval_duration": 200_000_000,
                    "load_duration": 1_000_000,
                },
            ]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    transport.created = created  # type: ignore[attr-defined]
    return transport, calls


def reply_for(body: dict) -> str:
    system = body["messages"][0]["content"]
    if "grading ONE learner answer" in system:
        return GOOD_VERDICT
    if "grammar tutor" in system:
        return json.dumps(
            {
                "explanation": "Use the past simple for a finished time like yesterday. "
                "The present perfect does not go with yesterday.",
                "example": "We visited Rome last year.",
            }
        )
    if "vocabulary card" in system:
        return json.dumps(
            {
                "definition": "Not wanting to do something.",
                "example": "He was reluctant to leave.",
                "synonym": "unwilling",
            }
        )
    if system == "You are a helpful assistant.":  # warm-up
        return "A banana is a sweet yellow fruit."
    if "AI Monkey" in system:
        return "Fun! (Tip: we say 'went'.) Did your dog like the park?"
    if "role-playing" in system:
        return "That's four pounds, please. Cash or card?"
    return (
        "'If I were you' is correct and more formal; 'were' is used for imaginary, unreal "
        "situations, although many people say 'was'."
    )


def test_full_run_writes_results_and_never_fakes_missing_models(tmp_path, repo):
    transport, calls = fake_ollama({"good:q4": "Q4_K_M", "wrong:q5": "Q4_K_M"}, reply_for)
    client = OllamaBenchClient("http://fake", transport=transport)
    config = BenchConfig(
        suite="quick",
        runs=3,
        warmup=2,
        settle_s=0,
        models=(
            ModelSpec("Good Q4", "Q4_K_M", ("good:q4",), "test"),
            ModelSpec("Wrong Q5", "Q5_K_M", ("wrong:q5",), "test"),
            ModelSpec("Missing Q8", "Q8_0", ("missing:q8",), "test"),
        ),
    )
    result = run_benchmark(config, client, repo, log=lambda *_: None)

    status = {a["label"]: a["status"] for a in result["availability"]}
    assert status == {"Good Q4": "ok", "Wrong Q5": "wrong_quantization", "Missing Q8": "missing"}
    assert [s["model"] for s in result["summary"]] == ["Good Q4"]  # nothing invented
    # every run: reload + 2 neutral warm-ups, then the 6 quick tests; same fixed options
    assert len(calls) == 3 * (2 + 6)
    for body in calls:
        assert body["stream"] is True and body["think"] is False
        assert body["options"]["num_ctx"] == 4096 and "seed" in body["options"]
    is_warmup = [c["messages"][0]["content"] == "You are a helpful assistant." for c in calls]
    assert is_warmup == ([True] * 2 + [False] * 6) * 3  # warm-up is never a dataset test
    measured = [c for c, w in zip(calls, is_warmup, strict=True) if not w]
    assert [c["options"]["seed"] for c in measured] == [43] * 6 + [44] * 6 + [45] * 6

    s = result["summary"][0]
    assert s["requests"] == 18 and s["errors"] == 0
    assert s["tokens_per_s"] == 20.0 and s["vram_gb"] == 0.0 and s["memory_gb"] == 6.0
    assert 0 < s["quality"] <= 100 and len(s["quality_by_run"]) == 3
    assert s["overall"] == pytest.approx(0.9 * s["quality"] + 0.1 * s["performance"], abs=0.1)

    paths = write_all(result, tmp_path)
    assert [p.name for p in paths] == [
        "results.json",
        "results.csv",
        "generations.csv",
        "report.md",
    ]
    report = (tmp_path / "report.md").read_text()
    assert "| Model | Quality | P50 | P95 | Tok/s | VRAM | Overall |" in report
    assert "wrong_quantization" in report and "missing" in report
    rows = list(csv.DictReader((tmp_path / "results.csv").open()))
    assert rows[0]["model"] == "Good Q4"
    assert len(list(csv.DictReader((tmp_path / "generations.csv").open()))) == 18
    assert "Good Q4" in recommendation(result["summary"])


def test_failed_requests_count_against_quality(repo):
    def flaky(body):
        if "role-playing" in body["messages"][0]["content"]:
            raise httpx.ConnectError("boom")
        return reply_for(body)

    def handler_reply(body):
        return flaky(body)

    transport, _ = fake_ollama({"m": "Q4_K_M"}, handler_reply)
    client = OllamaBenchClient("http://fake", transport=transport)
    config = BenchConfig(
        suite="quick", runs=3, warmup=0, models=(ModelSpec("M", "Q4_K_M", ("m",), "test"),)
    )
    result = run_benchmark(config, client, repo, log=lambda *_: None)
    s = result["summary"][0]
    assert s["errors"] == 3  # the conversation test, every run
    assert s["categories"]["conversation"] == 0.0


def test_models_with_another_template_run_through_an_aligned_alias(repo):
    installed = {"qwen3:8b": "Q4_K_M", "hf.co/x/y:Q5_K_M": "Q5_K_M"}
    transport, calls = fake_ollama(installed, reply_for, templates={"hf.co/x/y:Q5_K_M": "HF"})
    client = OllamaBenchClient("http://fake", transport=transport)
    config = BenchConfig(
        suite="quick",
        runs=1,
        warmup=1,
        settle_s=0,
        test_ids=("vs.01",),
        models=(
            ModelSpec("Q4", "Q4_K_M", ("qwen3:8b",), "lib"),
            ModelSpec("Q5", "Q5_K_M", ("hf.co/x/y:Q5_K_M",), "hf"),
        ),
    )
    result = run_benchmark(config, client, repo, log=lambda *_: None)
    q5 = next(a for a in result["availability"] if a["label"] == "Q5")
    assert q5["aligned_from"] == "hf.co/x/y:Q5_K_M" and q5["tag"].startswith("bench/")
    alias = transport.created[q5["tag"]]
    assert alias["template"] == LIB_TEMPLATE and alias["parameters"]["presence_penalty"] == 0
    q4 = next(a for a in result["availability"] if a["label"] == "Q4")
    assert q4["aligned_from"] is None and q4["tag"] == "qwen3:8b"  # reference stays as is
    assert {c["model"] for c in calls} == {"qwen3:8b", q5["tag"]}
    for c in calls:  # identical sampling options for every model
        assert c["options"]["presence_penalty"] == 0 and c["options"]["top_k"] == 20


def test_recommendation_uses_a_paired_test_over_tests():
    base = {"performance": 100.0, "overall": 90.0, "quality": 90.0, "quality_by_run": [90.0]}
    same = {f"t{i}": 80.0 + (i % 3) for i in range(10)}
    noisy_b = {t: v + (5 if i % 2 else -5) for i, (t, v) in enumerate(same.items())}
    tied = [
        {**base, "model": "A", "test_scores": same},
        {**base, "model": "B", "test_scores": noisy_b},
    ]
    assert "not a significant" in recommendation(tied)
    worse = {t: v - 20 for t, v in same.items()}
    clear = [
        {**base, "model": "A", "test_scores": same},
        {**base, "model": "B", "test_scores": worse},
    ]
    assert "a significant difference" in recommendation(clear)
    assert paired_difference(same, worse)[0] == pytest.approx(20.0)


def test_a_model_that_cannot_load_is_reported_not_scored(repo):
    def reply(body):
        if body["model"] == "big":
            raise httpx.ReadError("model requires more system memory")
        return reply_for(body)

    transport, _ = fake_ollama({"small": "Q4_K_M", "big": "Q8_0"}, reply)
    client = OllamaBenchClient("http://fake", transport=transport)
    config = BenchConfig(
        suite="quick",
        runs=3,
        warmup=1,
        settle_s=0,
        test_ids=("vs.01",),
        models=(
            ModelSpec("Small", "Q4_K_M", ("small",), "t"),
            ModelSpec("Big", "Q8_0", ("big",), "t"),
        ),
    )
    result = run_benchmark(config, client, repo, log=lambda *_: None)
    big = next(a for a in result["availability"] if a["label"] == "Big")
    assert big["status"] == "error" and "failed to load" in big["detail"]
    assert [s["model"] for s in result["summary"]] == ["Small"]
