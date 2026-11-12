"""Question-bank latency and variety against a running stack (no LLM involved).

    docker compose up -d && python3 scripts/bench_bank.py [--sets 30] [--json out.json]

For every skill: builds sets with different filters and answers every question. Reports
p50/p95/max of set generation and of answer checking (the full request: check, attempt,
mastery and history in one transaction), and how many questions repeat across sets.
Standard library only; exits non-zero when a request fails.
"""

import argparse
import json
import os
import random
import statistics
import time
import urllib.error
import urllib.request
import uuid

B = os.environ.get("BANANA_URL", "http://127.0.0.1:3010")
SKILLS = ("grammar", "vocabulary", "reading", "listening")


def call(method, path, body=None, h=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        B + path,
        method=method,
        data=data,
        headers={**({"Content-Type": "application/json"} if data else {}), **(h or {})},
    )
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null"), (time.perf_counter() - t) * 1000
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null"), (time.perf_counter() - t) * 1000


def stats(ms: list[float]) -> dict:
    ms = sorted(ms)
    return {
        "n": len(ms),
        "p50_ms": round(statistics.median(ms), 1),
        "p95_ms": round(ms[int(0.95 * (len(ms) - 1))], 1),
        "max_ms": round(ms[-1], 1),
    }


def some_answer(q: dict, rng: random.Random):
    """A plausible answer of the right shape (right or wrong does not matter here)."""
    if q["qtype"] in ("mcq", "true_false", "error_id"):
        return rng.choice(q["options"])["id"]
    if q["qtype"] == "ordering":
        return rng.sample(q["pieces"], len(q["pieces"]))
    if q["qtype"] == "matching":
        rights = [o["id"] for o in q["options"]]
        return {
            left["id"]: r
            for left, r in zip(q["left"], rng.sample(rights, len(rights)), strict=False)
        }
    return "an answer"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", type=int, default=30, help="sets per skill")
    ap.add_argument("--count", type=int, default=10, help="questions per set")
    ap.add_argument("--json", help="write the report here")
    args = ap.parse_args()
    rng = random.Random(7)

    s, reg, _ = call(
        "POST",
        "/api/v1/auth/register",
        {
            "email": f"bench-{uuid.uuid4().hex[:8]}@example.com",
            "password": "bench-test-pass",
            "display_name": "Bank Bench",
            "current_level": "B1",
        },
    )
    assert s == 201, reg
    h = {"Authorization": f"Bearer {reg['token']}"}
    report: dict = {}
    for skill in SKILLS:
        s, facets, facet_ms = call("GET", f"/api/v1/bank/{skill}/facets", h=h)
        assert s == 200, facets
        levels = [lv for lv, n in facets["levels"].items() if n]
        points = [p for p, n in facets["points"].items() if n >= 50]
        set_ms, answer_ms, seen = [], [], []
        for i in range(args.sets):
            body: dict = {"count": args.count}
            if i % 3 == 1:
                body["levels"] = [rng.choice(levels)]
            elif i % 3 == 2 and points:
                body["points"] = [rng.choice(points)]
            s, got, ms = call("POST", f"/api/v1/bank/{skill}/sets", body, h)
            assert s == 200, got
            set_ms.append(ms)
            for q in got["questions"]:
                seen.append(q["id"])
                s, res, ms = call(
                    "POST",
                    "/api/v1/bank/answer",
                    {"question_id": q["id"], "answer": some_answer(q, rng), "response_time_ms": 1},
                    h,
                )
                assert s == 200, res
                answer_ms.append(ms)
        report[skill] = {
            "pool": facets["total"],
            "facets_ms": round(facet_ms, 1),
            "set": stats(set_ms),
            "answer": stats(answer_ms),
            "questions_served": len(seen),
            "repeated": len(seen) - len(set(seen)),
        }
        r = report[skill]
        print(
            f"{skill:<10} pool {r['pool']:>6}  set p50 {r['set']['p50_ms']:>6} ms "
            f"p95 {r['set']['p95_ms']:>6} ms | answer p50 {r['answer']['p50_ms']:>5} ms "
            f"p95 {r['answer']['p95_ms']:>5} ms | {r['repeated']}/{r['questions_served']} repeated"
        )
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
