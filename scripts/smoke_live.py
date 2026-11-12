"""Live smoke test against a running stack (real LLM + STT): every module end to end.

    docker compose up -d && python3 scripts/smoke_live.py [path/to/spoken_answer.wav]

Standard library only. Prints scores and latencies; exits non-zero on any failed step.
"""

import json
import os
import sys
import time
import urllib.request
import uuid

B = os.environ.get("BANANA_URL", "http://127.0.0.1:3010")


def call(method, path, body=None, h=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(
        B + path,
        method=method,
        data=data,
        headers={**({"Content-Type": ctype} if data else {}), **(h or {})},
    )
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read() or b"null"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null"), time.time() - t


s, reg, _ = call(
    "POST",
    "/api/v1/auth/register",
    {
        "email": f"smoke-{uuid.uuid4().hex[:8]}@example.com",
        "password": "smoke-test-pass",
        "display_name": "Live Test",
        "current_level": "A2",
    },
)
assert s == 201, reg
p = reg["profile"]
h = {"Authorization": f"Bearer {reg['token']}"}
# the configuration summary is for admins only; a new account sees {"status": "ok"}
print("health", call("GET", "/api/v1/health", h=h)[1].get("status"))
# grammar: wrong past tense x2 (LLM), then the same answer again (cache)
for ex, ans in [
    ("gr.past.004", "I have saw that film yesterday"),
    ("gr.past.006", "He has finish his homework two hours ago."),
    ("gr.past.004", "I have saw that film yesterday"),
]:
    s, r, dt = call("POST", "/api/v1/grammar/attempt", {"exercise_id": ex, "answer": ans}, h)
    a = r["assessment"]
    print(
        f"grammar {s} {dt:5.1f}s score={a['score']} {a['band']} mistakes={[m['category'] for m in a['mistakes']]} | {a['feedback'][:80]}"
    )
    last = r
# alternative correct answer via LLM
s, r, dt = call(
    "POST",
    "/api/v1/grammar/attempt",
    {"exercise_id": "gr.past.004", "answer": "Yesterday I saw that film."},
    h,
)
print(f"grammar-alt {s} {dt:5.1f}s score={r['assessment']['score']} {r['assessment']['assessor']}")
top = call("GET", "/api/v1/recommendation/next?n=3", h=h)[1]["recommendations"][0]
print(
    "next:", top["kind"], top["skill_id"], [i["item_id"] for i in top["items"]], "|", top["reason"]
)
# tutor
s, r, dt = call(
    "POST", "/api/v1/tutor/explain", {"attempt_id": last["attempt_id"], "mistake_index": 0}, h
)
print(f"tutor {s} {dt:5.1f}s {r.get('explanation', r)[:160]}")
# listening paraphrase
s, r, dt = call(
    "POST",
    "/api/v1/listening/attempt",
    {"question_id": "ls.train.001.q3", "answer": "the signals were broken"},
    h,
)
print(
    f"listening {s} {dt:5.1f}s score={r['assessment']['score']} {r['assessment']['assessor']} | {r['assessment']['feedback'][:80]}"
)
# speaking: real TTS audio -> whisper -> qwen
default_audio = os.path.join(
    os.path.dirname(__file__), "..", "content/listening/audio/ls.routine.001.wav"
)
# default audio = a daily-routine monologue -> pair it with the matching "introduce yourself" task
prompt_id = "sp.weekend.001" if len(sys.argv) > 1 else "sp.intro.001"
audio = open(sys.argv[1] if len(sys.argv) > 1 else default_audio, "rb").read()
bnd = uuid.uuid4().hex
body = (
    (
        f'--{bnd}\r\nContent-Disposition: form-data; name="prompt_id"\r\n\r\n{prompt_id}\r\n--{bnd}\r\nContent-Disposition: form-data; name="audio"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'
    ).encode()
    + audio
    + f"\r\n--{bnd}--\r\n".encode()
)
s, job, _ = call(
    "POST", "/api/v1/speaking/attempt", raw=body, h=h, ctype=f"multipart/form-data; boundary={bnd}"
)
t = time.time()
while True:
    j = call("GET", f"/api/v1/jobs/{job['job_id']}", h=h)[1]
    if j["status"] in ("succeeded", "failed"):
        break
    time.sleep(2)
res = j["result"] or {}
print(f"speaking {j['status']} {time.time() - t:5.1f}s transcript={res.get('transcript')!r}")
if res:
    print(
        "   grammar",
        res["grammar"]["score"],
        [m["category"] for m in res["grammar"]["mistakes"]],
        "fluency",
        res["fluency"]["score"],
        res["fluency"]["words_per_minute"],
        "wpm",
        [c["skill_id"] for c in res["mastery_changes"]],
    )
else:
    print("   error", j["error"])
# conversation 4 turns
s, c, dt = call("POST", "/api/v1/conversations", {"scenario_id": "cv.cafe.001"}, h)
print("waiter:", c["turns"][0]["text"])
for line in [
    "Hello, I want a coffee please.",
    "Yes, I would like a cheese sandwich.",
    "How much it cost?",
    "I pay with card, thank you.",
]:
    s, c, dt = call("POST", f"/api/v1/conversations/{c['id']}/messages", {"text": line}, h)
    print(f"  me: {line}\n  waiter ({dt:4.1f}s): {c['turns'][-1]['text']}")
s, job, _ = call("POST", f"/api/v1/conversations/{c['id']}/finish", h=h)
t = time.time()
while True:
    j = call("GET", f"/api/v1/jobs/{job['job_id']}", h=h)[1]
    if j["status"] in ("succeeded", "failed"):
        break
    time.sleep(2)
print(
    f"summary {j['status']} {time.time() - t:5.1f}s avg={j['result']['average_score']} errors={j['result']['error_counts']}"
)
for t_ in j["result"]["turns"]:
    a = t_["assessment"]
    print("   ", t_["text"], "->", a and a["score"], a and [m["category"] for m in a["mistakes"]])
print(
    "weak:",
    [
        (w["skill_id"], w["mastery"])
        for w in call("GET", "/api/v1/learner/weak-skills", h=h)[1]["skills"]
    ],
)
print("LEARNER", p["learner_id"])
assert j["status"] == "succeeded", j
