# ADR 0001: From the Phase 0 MVP to the full product (Phases 1–11)

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

The product spec defines 11 phases. Phase 0 built vocabulary and grammar around a decayed Beta
mastery model and Leitner boxes. The spec asks for specific mechanics:

- EMA mastery per skill tag on a 0–100 scale;
- SM-2 spaced repetition with four buttons;
- a rubric-prompted LLM;
- a rule engine with a weakness threshold of 60.

It also adds Listening, Speaking, Conversation, a Tutor, a Dashboard and Ops.

## Decisions

1. **Follow the spec's learning mechanics.**
   - Mastery is an EMA (ALPHA 0.3), SM-2 replaces Leitner, and the rubric bands are shared.
   - Phase 0's layered architecture, contracts and tests are kept. Only the algorithms behind
     them changed.
2. **One rubric, one scale.** Every assessor returns 0–100 using the bands in
   `domain/services/rubric.py`. Vocabulary buttons map to 20 / 70 / 85 / 100.
3. **The LLM classifies; the platform scores.** Calibration (v2→v6) showed the local model
   names errors reliably but picks inconsistent numbers. The model now returns grounded,
   categorical judgements, and the score is computed from them. This deviates from the spec's
   "LLM returns score", on purpose and with evidence (`docs/calibration/README.md`).
4. **Caching is part of consistency.** Verdicts are cached in Redis under a hash of the full
   rendered prompt, so identical answers score identically and a prompt change starts fresh.
5. **Free production feeds grammar skills.** Errors found in speaking and conversation update
   the grammar skill they reveal: articles, prepositions, comparatives, conditionals, or the
   task's target tense.
6. **Async scope.** STT + LLM (speaking) and the conversation summary run as background jobs on
   an in-process runner, with state in Postgres. Everything else is sync in FastAPI's thread
   pool. A Redis queue can replace `JobRunner` when there is more than one API process.
7. **Frontend.** Next.js 15 with hand-written SVG charts following the data-viz rules: one
   axis, 2 px lines, a validated CVD-safe palette, and a table view. The web app proxies `/api`
   to the API, so there is a single origin and no CORS in production.
8. **Authentication.** It was first deferred behind an `X-Learner-Id` header, and later added
   as scrypt accounts with hashed, revocable session tokens: an httpOnly cookie for the web app,
   a Bearer token for API clients. The header remains as a development-only switch.
9. **Learner-facing text for reviewed exercises is built from reviewed content.** The LLM
   provides the score category and the grounded error fragments; the advice text comes from the
   reviewed answers (see architecture §3).
10. **Alembic migrations** replace `create_all`. Pre-migration databases are adopted by stamping
    them.

## Consequences

- Phase 0's `/api/v1/recommendations` endpoint became `/api/v1/recommendation/next`, as in the
  spec. The mastery scale moved from 0–1 to 0–100. The contract snapshot was regenerated.
- The items that need a person are listed in `docs/phases.md`.
