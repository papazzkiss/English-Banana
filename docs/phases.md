# Phase checklist: Definition of Done and evidence

Legend: ✅ done and verified · ⚠️ built and working, but needs a person to close it

| Phase | Status | Evidence |
|---|---|---|
| 0 Scope & MVP | ✅ | Real content in `content/`; decision record `docs/decisions/phase-0-scope.md` |
| 1 Architecture | ✅ | Abstract base classes: `LLMProvider`, `STTProvider`, `RecommendationEngine`, `AssessmentEngine`, `Cache`, `JobRunner`, with mocks. `/health` returns 200. The contract lives in `docs/openapi.json` and a test fails on drift |
| 2 Vocabulary (SM-2) | ✅ | `tests/unit/test_sm2_and_vocabulary.py::test_again_vs_easy_diverge_over_90_simulated_days` and `tests/integration/…::test_vocabulary_sm2_queue_over_simulated_days` |
| 3 Grammar + AI assessment | ⚠️ | Structured output, a unified rubric, retry and 503 fallback, and calibration from v2 to v6 (see `docs/calibration/`). Open: a teacher must verify the 20 calibration labels |
| 4 Profile & mastery | ✅ | EMA with ALPHA 0.3 per skill tag, the `mastery_events` attempt log, `/learner/mastery-history`, and a 14-day simulation on Postgres |
| 5 Weakness + recommendation | ✅ | `test_deliberately_failing_past_tense_gets_past_tense_recommended`, and live: after failing past tense, the next recommendation is past tense |
| 6 Listening | ✅ | 8 lessons with real audio (Piper, 14–25 s). Paraphrases are graded by the LLM; skill tag `listening.comprehension` |
| 7 Speaking | ✅ | Whisper transcribes, then the grammar grader and fluency metrics run on the transcript. The transcript is shown in the UI. Phoneme-level pronunciation is out of scope |
| 8 Conversation | ✅ | 4 scenarios of 5–6 turns. The partner stays in character, the turns are graded as a batch afterwards, and the summary plus skill updates follow. Verified live with qwen3 |
| 9 AI Tutor | ⚠️ | `POST /tutor/explain` works on stored errors and is grounded in the teacher's rule. Open: a teacher must verify `docs/calibration/tutor_check.md` |
| 10 Dashboard | ✅ | Next.js pages: mastery curves, weak skills, and next steps from `/recommendation/next`. Screenshots checked in light, dark and 375 px mobile |
| Auth (beyond the spec) | ✅ | Accounts and sessions, httpOnly cookie, revocation, expiry, login rate limit (`tests/integration/test_auth.py`). Browser flow verified in Chromium |
| 11 Deployment & ops | ✅ | `docker compose up --build` (api, web, postgres, redis). Alembic migrations run on startup. CI workflow, `/metrics` with real LLM/STT latency, prompt version logged on every attempt and in `llm_calls` |

Everything AI-generated is `pending_review`. The totals are 42 grammar exercises, 8 listening
lessons, 6 speaking prompts and 4 scenarios. Approve them with `scripts/review_content.py`,
then set `BANANA_REQUIRE_REVIEWED_CONTENT=true`.

## Measured numbers (qwen3:8b on a 12-core CPU, no GPU)

**Grammar grading and tutor quality** — full history in `docs/calibration/README.md`:

- Calibration with prompt v6 against the AI-drafted labels: MAE 15.7, bias +4.7, and 16/20
  correct/incorrect agreement.
- Two runs of v6 were identical.
- AI Tutor v2, by my pre-review: 6/10 clear and correct, 3 vague, 0 wrong, 1 not applicable.

**Latency** — from `/metrics` on the live stack:

| Call | Latency |
|---|---|
| Grammar grading | p50 10–20 s, p95 ≤ 30 s, mean 13.9 s (n = 8); a cache hit is 0 s |
| Conversation reply | mean 4.1 s |
| Tutor | 7.6 s |
| Listening grading | 2.8 s |
| Whisper `base.en` | 1.6 s for 11 s of audio (warm) |
| Speaking job end to end | about 30 s |

**Whisper round trip on the listening audio:** WER 7.2%. Most of the differences are number
formatting, such as "seven" vs "7".

**14-day simulated learner** (heuristic mock grader, seeded):

- 166 assessed answers.
- Past tense started at 20% ability, became the most recommended grammar skill, and finished
  at a mastery of 79.9.

**SM-2 over 90 days:**

- "Again" is reviewed daily: 90 reviews, and the ease factor falls to 1.3.
- "Easy" follows the intervals 1 → 6 → 16 → 45 days, with 5 reviews.

## Tuning parameters and why they are set this way

| Parameter | Value | Why |
|---|---|---|
| ALPHA (EMA) | 0.3 | The spec's starting point. With the default of 50, one bad answer (score 20) makes a fresh skill weak (41 < 60); three correct answers make it strong (83). Tune it on real learner curves |
| REPEAT_ALPHA | 0.1 | Re-doing an exercise already solved counts for a third. Three drills reach 63.6, versus 82.9 with three new items |
| WEAKNESS_THRESHOLD | 60 | From the spec. It is the same constant for the recommender and the dashboard |
| EASY_BELOW | 40 | From the spec: weak skills below 40 get easy items, otherwise medium |
| Forgetting | 7-day grace, then a 30-day half-life towards 50 | Skills that looked strong but have not been practised come back into rotation |
| Scores from findings | 95 / 80 / 55 / 45 / 25 / 15 | Mid-band values of the unified rubric (see `rubric.py`) |
