# ADR 0: Phase 0 scope and MVP

- **Status:** Accepted (Phase 0). Partly superseded by [0001-full-product.md](0001-full-product.md): mastery is now an EMA (0-100) and vocabulary uses SM-2, per the product spec.
- **Date:** 2026-09-27

## Context

Banana English is an adaptive English learning platform built around one loop:

```
Learn → Assess → Update Mastery → Recommend → Learn again
```

Phase 0 has to show that this loop works end to end. The foundation also has to
let real AI models, more modules and a real frontend be added later without
rewriting the core.

## Decision: what is in Phase 0

| Area | In scope |
|---|---|
| Modules | **Vocabulary** and **Grammar** only |
| Vocabulary | Real CEFR-aligned data (7,351 items, A1–B2). Deterministic scoring with typo tolerance, per-level mastery, Leitner spaced repetition |
| Grammar | 42 exercises across 6 topics. LLM assessment behind an interface, schema-validated, with deterministic reference matching first |
| Adaptivity | Deterministic mastery model and rule-based recommendations |
| API | 5 required endpoints, plus `POST /learners` and `GET /health` |
| AI | `LLMProvider` interface, a scripted mock for tests, a heuristic mock for dev. **No real model.** |
| Storage | SQLite through SQLAlchemy 2.0 behind repository interfaces |

## Deferred (not implemented, on purpose)

| Feature | Why it is deferred |
|---|---|
| Listening, Speaking, Pronunciation | STT, TTS and audio are separate engineering problems: streaming, latency, cost, accent bias |
| Conversation / AI Tutor | Needs dialogue state, safety and cost controls. Builds on the assessment pipeline once that is proven |
| Advanced progress dashboard | `GET /learner/mastery` already exposes the data. Visualisation is a frontend concern |
| ML-based recommendation | There are no interaction data to train on yet. The rule-based baseline produces that data and is the benchmark to beat |
| Real LLM provider (Ollama/Qwen) | Phase 1. The contract, validation and retry paths are already in place and tested with mocks |
| Authentication | Phase 0 identifies the learner with the `X-Learner-Id` header only. **Not production-safe.** |
| C1/C2 vocabulary | The only open C1/C2 list (Octanove) is CC BY-SA, and its share-alike terms need a licensing decision first |
| Multiple-choice vocabulary, other exercise types | The typed recall exercise is enough to prove the loop |
| DB migrations (Alembic), Postgres | `create_all` is enough for Phase 0 |

## Key decisions

**D1. Contract → interface → implementation.** API schemas (`api/schemas.py`,
snapshotted in `docs/openapi.json`) and domain interfaces (`domain/interfaces/`)
come first. Implementations are wired in one composition root
(`config/container.py`). Business logic never imports a concrete provider.

**D2. Vocabulary data comes from real, licensed sources and is never invented.**
- Headword, part of speech and CEFR level come from the **CEFR-J Wordlist v1.5** (Tono Laboratory,
  TUFS). It is free for research and commercial use if cited. The source CSV is committed under
  `content/vocabulary/sources/`.
- Definitions and examples come from **Open English WordNet 2024** (CC BY 4.0).
- `scripts/build_vocabulary.py` joins the two sources reproducibly. It takes the most frequent WordNet
  sense within the top 3, preferring a sense whose definition does not contain the headword and
  whose example sentence does.
- Function words (313 rows: determiners, prepositions, pronouns and so on) have no WordNet entry and
  are skipped. They belong to grammar. 134 rows have no WordNet match.
- **Known limitation:** the automatic sense choice is sometimes not the one a learner needs
  (e.g. *bank* maps to "sloping land"). Every item is therefore marked `review_status: auto_mapped`
  and keeps its `provenance.sense_id` and `sense_rank`, so a sense can be corrected later.

**D3. Grammar exercises are AI-generated candidates behind a human review gate.**
All 42 exercises were written by an AI (`authored_by: ai:claude-opus-5-5`) and have
`status: pending_review`.
- `scripts/review_grammar.py` records approve or reject decisions with the reviewer and a timestamp.
- The content loader refuses an `approved` exercise that has no reviewer.
- With `BANANA_REQUIRE_REVIEWED_CONTENT=true`, only approved exercises are served.
- The dev default serves candidates and logs a warning at startup.

**D4. Raw LLM output never touches the database.** The path is:

`LLMProvider.complete` → raw text → JSON parse → Pydantic schema (`extra=forbid`,
ranges, lengths, allowed categories) → semantic consistency check → domain `Assessment`
→ mastery update.

- The consistency check requires that `is_correct` matches `score ≥ 0.8`, that a correct answer
  lists no mistakes, and that an incorrect one lists at least one.
- Invalid output is retried (`BANANA_LLM_MAX_RETRIES`, default 1). If it is still invalid, the
  attempt is stored as `assessment_failed`, the API returns HTTP 503, and **mastery is unchanged**.

**D5. Grammar is matched against reference answers before the LLM is called.** If the normalised
answer equals one of the reviewed accepted answers, it scores 1.0 and no LLM call is made. This is
cheaper, faster and cannot be wrong. The LLM is used only for answers that are not covered.

**D6. Mastery is a decayed Beta estimate** (`domain/services/mastery.py`). It is pure, deterministic
and replayable from history:
- Prior Beta(1, 1), decay 0.9 per attempt (an effective memory of about 10 attempts).
- `confidence = n / (n + 2)`.
- It is documented in the module and pinned by 20+ unit tests.

**D7. Partial credit for incorrect answers is halved.** Without this, an LLM score of
0.6 on a *wrong* answer raised mastery above the 0.5 prior; the first smoke test caught
this. With the factor, any incorrect answer on a fresh skill lands in reinforcement.

**D8. Recommendations are rule-based, explainable and interleaved.** The bands follow the spec
(below 0.5 reinforcement, 0.5 to 0.75 practice, above 0.75 advance), plus two more kinds:
`introduce` for skills that have not been started and `review` for spaced-repetition items that
are due.
- Every recommendation carries a `reason_code`, a human-readable `reason` and `evidence`
  (mastery, confidence, top mistakes).
- Modules are interleaved within each kind, so a short list mixes grammar and vocabulary.
- There is no LLM dependency.

**D9. Package layout is `src/banana_english/{api,domain,application,infrastructure,config}`.** The
spec's layers are kept as they are, but inside one named package. Top-level packages called `api`
or `config` would collide with third-party modules.

**D10. Endpoints are synchronous, and the LLM call happens outside the DB transaction.**
FastAPI runs sync endpoints in a thread pool, which is fine for Phase 0 load. Assessing
first and then committing attempt, mastery and review state in one short transaction
keeps locks short even with a slow model.

## Definition of Done

| Item | Status |
|---|---|
| Real vocabulary data exists | ✅ 7,351 items, CEFR-J + OEWN, cited, reproducible build |
| 30–50 **reviewed** grammar exercises exist | ⚠️ **42 exercises exist and the review gate is in place, but they have not been reviewed by a person yet.** An AI cannot honestly approve its own content. A teacher needs to run `scripts/review_grammar.py` (about 30 minutes). |
| API contracts exist | ✅ `docs/api-contract.md`, `docs/openapi.json` (drift-tested) |
| Domain models exist | ✅ `domain/models/` |
| Interfaces + mocks exist | ✅ `LLMProvider`, `AssessmentEngine`, `RecommendationEngine`, repositories, `Clock`; `ScriptedLLMProvider`, `HeuristicMockLLMProvider` |
| Mastery engine tested | ✅ `tests/unit/test_mastery.py` |
| Recommendation engine tested | ✅ `tests/unit/test_recommendation_engine.py` |
| End-to-end loop works with mocks | ✅ `tests/integration/test_learning_loop.py` |
| Tests pass | ✅ 123 passed |
| Scope and deferred features documented | ✅ this file |

**Phase 1 must not start until the grammar review item above is closed.**
