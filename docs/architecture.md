# Banana English — Architecture

## 1. What it is

Banana English tracks **per-skill mastery** for each learner, finds weak skills, and keeps
bringing practice back to them:

```
Learn ─► Assess (rubric 0-100) ─► Update mastery (EMA per skill tag) ─► Recommend ─► Learn …
```

- There are five modules: Vocabulary, Grammar, Listening, Speaking and Conversation. There is
  also an AI Tutor, which is a presentation layer.
- They all share **one** assessment → mastery → recommendation core.

## 2. Layers and the dependency rule

```
src/banana_english/
├── domain/            pure Python: entities, enums, ports (ABCs)
│   ├── models/        User, LearnerProfile, Skill, SkillMastery, MasteryEvent, Attempt, Assessment,
│   │                  Mistake, VocabularyCard, Listening/Speaking/Scenario content, Conversation, Job
│   ├── interfaces/    LLMProvider, STTProvider, AssessmentEngine, RecommendationEngine, Cache,
│   │                  JobRunner, Clock, repositories + UnitOfWork
│   └── services/      rubric, mastery (EMA), sm2, weakness, fluency, answer matching
├── application/
│   ├── services/      grading engines, prompts (versioned), LLM contracts, structured LLM
│   │                  runner, recommendation engine, conversation partner, tutor, calibration
│   └── use_cases/     vocabulary, attempts (grammar/listening), speaking, conversation, tutor,
│                      learner/dashboard queries, recommendations, jobs
├── infrastructure/    ollama + mock LLMs, faster-whisper + mock STT, instrumentation,
│                      SQLAlchemy (Postgres/SQLite), Redis/memory cache, thread job runner,
│                      JSON content loader, Prometheus metrics, request-id context
├── api/               FastAPI routers, schemas (the contract), mappers, error envelope
└── config/            settings (BANANA_* env) + composition root (container.py)
frontend/              Next.js 15 + React 19 + TypeScript (no UI or chart library: own
                       design system in components/ui + globals.css tokens, SVG charts)
```

**Frontend.** One app shell (`AppShell`: sidebar ≥ 1024 px, header + bottom tabs below) and one
learner context (`LearnerProvider`: a single `/auth/me` per navigation, shared by every screen).
Routes: `/dashboard` (what to do now), `/practice` (hub) and the five module screens, `/monkey`,
`/progress` (mastery charts). Module names, colours and routes live in `lib/modules.tsx`. Grammar
state is in the URL (`?topic=`, `?exercise=`), so back/forward and deep links work.

**The dependency rule is `api → application → domain ← infrastructure`.**

- Only `config/container.py` knows concrete classes.
- Swapping Ollama for a hosted model, Whisper for another STT, or the rule engine for an ML
  ranker changes one class plus the composition root.

## 3. The core loop in detail

### Assessment

Every assessor returns a domain `Assessment` with a score on the unified 0–100 rubric
(`domain/services/rubric.py`).

| Module | How the answer is assessed |
|---|---|
| Vocabulary | Deterministic. The learner presses Again, Hard, Good or Easy (SM-2 quality 1/3/4/5). A typed answer caps the rating: a typo caps it at Hard, a wrong word forces Again |
| Grammar | 1. Empty answer → 0. 2. Match with a reviewed reference answer → 100, with no LLM call. 3. Otherwise the LLM gives a categorical verdict (errors with grounded fragments, plus a `natural` flag), and the rubric computes the score |
| Listening | Match with an accepted answer → 100. Otherwise the LLM judges `understood` as fully / partly / not, which maps to 95 / 55 / 15. The model sees the transcript, never the audio |
| Speaking | Whisper produces a transcript. The grammar grader runs on it, with the task's target grammar as a hint. Deterministic fluency metrics (words per minute, fillers, long pauses) are computed too |
| Conversation | The partner replies in character, and nothing is graded during the conversation. On finish, a background job grades each learner turn with the grammar grader |

**LLM safety pipeline** (`structured_llm.py`, `llm_contracts.py`). Raw text passes through
these steps, in order:

1. Strip any `<think>` block and a single code fence.
2. Parse JSON.
3. Validate with Pydantic: `extra=forbid`, enums, lengths.
4. Check grounding: every error fragment must appear in the learner's answer.
5. Convert to an `Assessment`.

If validation fails, the call is retried once. If it still fails, the attempt is stored as
`assessment_failed`, the API returns HTTP 503, and **mastery is never touched**.

**Learner-facing text.** For reviewed exercises, the score and the grounded error fragments
come from the LLM, but the feedback, the corrected answer and any correction come from
reviewed content. A live check showed a correct score arriving with wrong advice ("use 'have
seen'"). Listening feedback is templated from the accepted answer.

**Consistency.** Verdicts are cached in Redis under a key hashed from the prompt version, the
provider, and the *fully rendered prompt* with the answer normalised. Identical answers
therefore get identical scores, and any context change misses the cache.

### Mastery (`domain/services/mastery.py`)

The model is an EMA on a 0–100 scale, per skill tag, starting at 50:
`m = 0.3 · score + 0.7 · m`.

- Repeating an already-solved item uses alpha 0.1 (anti-gaming).
- `confidence` is the share of the EMA weight that comes from real attempts.
- **Forgetting** is applied at read time: after 7 idle days, mastery above 50 decays towards 50
  with a 30-day half-life.
- Every change is written to `mastery_events` (the attempt log). That table drives the
  history charts.

Free production also updates the grammar skills it reveals, via `grammar_skills_for`. For
example, an article error in a conversation updates `grammar.articles`, and a tense error
updates the tense skill the task targets.

### Recommendation (`application/services/recommendation_engine.py`)

`next_exercises(context, n)` is pure and deterministic. It builds the list in this order:

1. **Weak skills first.** Take up to 3 skills whose effective mastery is below 60, weakest
   first. Items are easy when mastery is below 40, otherwise medium.
2. **Due SM-2 cards.**
3. **Default mix.** This fills the rest of the list, and on cold start it is the whole list:
   - one new topic per module, at or below the learner's level;
   - then "keep fresh" practice for the least recently practised skills (hard items above
     80).

When picking items within a skill:

- The target difficulty comes first.
- Then unseen items, then failed items (oldest first), then the least recently practised.
- The item attempted last is never repeated.

`find_weak_skills` is the *same function* behind `GET /learner/weak-skills`, so the dashboard
cannot disagree with the recommender.

### Spaced repetition (`domain/services/sm2.py`)

This is SM-2 as in Anki, implemented as a pure function.

- There is a daily limit on new cards (default 10).
- Reviewing a card before it is due counts as a repeat: alpha 0.1 in the mastery update.

## 4. Asynchronous work

- LLM calls always run **outside** DB transactions.
- Speaking (STT + LLM) and the conversation summary (N grading calls) run as background jobs:
  - `ThreadPoolJobRunner` executes them; state lives in the `jobs` table.
  - Clients poll `GET /jobs/{id}`.
  - A crashed job is marked `failed`, never left `running`.
- Grammar and listening attempts answer synchronously, unless the client sends
  `Prefer: respond-async`. Then they return 202 with a job whose result is the normal response.
  - The web app always does this: CPU grading can take over 30 s, longer than the Next.js proxy
    keeps a request open. The attempt used to be recorded while the browser showed an error.
  - Repeating the same answer to the same item while it is still being graded returns the same
    job, so a double click or a retry is counted once (`BackgroundAttempts`, in-process).
- Everything else uses sync endpoints, which FastAPI runs in its thread pool. The web proxy
  timeout is 120 s for the ones that still wait for the LLM (tutor, conversation replies).

**Resilience after a host reboot:**
- `db` and `redis` have `restart: unless-stopped`.
- At startup the API waits up to about 60 s for the database instead of crash-looping.
- Pooled connections are pre-pinged, so a database restart is survived at runtime.
- When the API is unreachable, the web app shows a clear message instead of "Request failed
  (500)".

The job runner assumes a single host with a single API process. That is the stated scope for
Phase 11. A Redis-backed queue would slot in behind `JobRunner`.

### AI Monkey (free chat)

AI Monkey is a separate tab. It is not part of the learning loop and does not touch the
scripted conversation.

- **Chat.** `POST /monkey/chat` takes the history from the client, so the server stores
  nothing. The prompt `monkey_chat_v1` asks for short, level-appropriate replies with at most
  one grammar tip. Nothing is graded and mastery never changes.
- **Voice.** The browser records audio, `POST /monkey/transcribe` runs Whisper in a worker
  thread and deletes the audio, and the browser's own speech synthesis reads the reply aloud.
- **UI state.** `MonkeyProvider` in the root layout holds the history (in `sessionStorage`,
  per learner), the microphone and speech. Leaving `/monkey` stops both. A reply that arrives
  elsewhere lights a dot on the tab. On phones the tab is pinned to the right of the scrolling
  tab row.
- **Talk mode (hands-free, `frontend/lib/talk/`).** Talk runs as a voice loop with no Send
  button:
  ```
  listening → hearing → processing (Whisper) → thinking (qwen3) → speaking (TTS) → 300 ms → listening
  ```
  - `vad.ts` detects voice on the microphone level, read with an `AnalyserNode` every 50 ms.
    - It calibrates the noise floor for 500 ms, then ignores sounds under 300 ms.
    - An utterance ends after 1,200 ms of silence and is cut at 30 s.
    - The noise floor keeps adapting slowly.
  - `session.ts` is the state machine.
    - Every browser API is injected, so Vitest runs the whole loop with fakes.
    - Each Talk session has a generation id and an `AbortController`, so a late reply from an
      ended session is dropped.
    - Only one request is ever in flight, and the microphone is ignored while the monkey
      thinks or speaks.
  - **The monkey's voice comes from the server.** `POST /monkey/speech` runs Piper
    (`en_US-ljspeech-medium`), taking about 0.1–0.25 s per reply. The voice is downloaded once
    into `/models/piper` and warmed up at start-up.
    - Browsers cannot be relied on: Brave and Chromium on Linux have no `speechSynthesis`
      voices, and `speak()` fails with `synthesis-failed` after about 4 ms.
    - `audio.ts` plays every reply through ONE shared `<audio>` element. The Start Talk / 🔊
      click calls `unlock()` synchronously (a 50 ms silence) before any `await`.
    - If `play()` is still refused (`NotAllowedError`), a "🔊 Bấm để nghe" button appears. The
      reply waits, with no timeout, and plays on that click.
    - A server without a voice (404, 5xx, network) falls back to `speechSynthesis`.
    - Request status, content type and size, and play start, end and rejection, are logged as
      `[talk-tts]`.
  - `tts.ts` speaks the reply without its "(Tip: …)" part.
    - A chunk counts as spoken only when `end` comes after `start`, or when no `end` arrives
      within words × 500 ms + 3 s of `start` (Chrome's `onend` is unreliable).
    - `end` before `start`, a `start` that never comes within 5 s, or an `interrupted` /
      `canceled` error it did not cause: retried once, never taken as "done".
    - `not-allowed` (the browser refuses to speak): replies stay as text, with one notice.
    - It never calls `cancel()` right before `speak()`. If something is still queued, it
      cancels, waits 150 ms, then speaks.
  - Every utterance is kept referenced until it ends (Chrome garbage-collects them and drops
    their events). Diagnostics go to the console as `[talk-tts]` lines and to
    `window.__talkTtsLog`: speak, start and end with timings, and `error` with `e.error`.
  - The microphone is closed while the monkey speaks and reopened 300 ms after the speech
    ended, as the tap-to-talk mode always did.
  - Empty or noise-like transcripts ("", "you", "…") never become a message or an LLM call.
  - Barge-in is designed for but off (`bargeIn: false`): in `speaking`, a detected voice
    would cancel TTS and go to `hearing`.
  - Talk stops completely on End Talk, when leaving `/monkey`, when the tab stays hidden for
    0.5 s, and on `pagehide`. That means the recorder, tracks, `AudioContext`, TTS, timers and the request.
    It never restarts by itself.
  - On iOS Safari, which only speaks from a tap, Talk falls back to the manual microphone.
- **Feature flag.** `BANANA_FEATURE_AI_MONKEY=false` hides the tab (`GET /features`) and makes
  the endpoints return 404.

## 5. Authentication

- **Accounts** hold an e-mail and a password hash (`hashlib.scrypt`, n=2¹⁴, with a
  per-password salt).
- **Sessions** are 256-bit random tokens. Only their SHA-256 is stored, and the `sessions` table
  allows revocation. They expire after 30 days.
- **Transport:** the web app uses an httpOnly, SameSite=Lax cookie that JavaScript never sees.
  Next.js proxies `/api`, so there is a single origin. API clients use a Bearer token.
- **Login hardening:** unknown e-mails still pay the scrypt cost (a dummy hash), so response
  time does not reveal which e-mails exist. The message is generic, and failures are limited to
  10 per 15 minutes per e-mail (in-process, single-host scope).
- Every protected endpoint depends on `current_principal`: one query reads the session, the
  user's role and whether the account is active (a disabled account gets 403
  `account_disabled`). Learner endpoints use `current_learner`, derived from it, and never take
  a user id. `X-Learner-Id` works only with `BANANA_ALLOW_LEARNER_HEADER=true` and never grants
  more than the student role.
- **Authorization:** roles `student`, `teacher`, `admin` with a static permission map
  (`domain/services/access.py`), enforced by router dependencies and again in the use cases;
  teachers see only the students an admin assigned them. Details and the endpoint map:
  [access-control.md](access-control.md).

## 6. Data (PostgreSQL; SQLite in tests)

| Table | Contents |
|---|---|
| `users`, `learner_profiles` | Identity, role (`admin` / `teacher` / `student`), `is_active`, and the learner profile |
| `accounts`, `sessions` | Login credentials (scrypt hash) and revocable sessions (token hash) |
| `teacher_students` | Which students each teacher may follow (set by an admin) |
| `skill_mastery` | One row per learner and skill: mastery, confidence, counts, `last_practiced_at` |
| `mastery_events` | The attempt log: skill, score, mastery before/after, time, source |
| `attempts` | Assessment inline, including **`prompt_version` and `model`**, plus `details` (JSON) |
| `mistakes` | The errors found in each attempt |
| `vocabulary_cards` | SM-2 state per learner and word |
| `conversations` | Turns as JSON, plus the summary |
| `jobs` | Background job state |
| `llm_calls` | Audit log: `request_id`, task, prompt version, provider/model, latency, tokens, ok/error, raw response (truncated) |
| `bank_passages`, `bank_questions` | The question bank: passages (reading texts, listening recordings) and questions with skill, level, topic, grammar point, type, difficulty, answer (JSON), explanations (EN + VI), source, quality, status (`draft` / `validated` / `approved` / `disabled`), content hash and an indexed random key `rand` |
| `learner_question_stats` | Per learner and bank question: times seen and correct, last result, `last_seen_at`: the anti-repetition and review history |
| `bank_imports` | One row per bank import: manifest hash, counts, time |

**Migrations (Alembic, `infrastructure/database/migrations/`).** The app runs
`upgrade head` on startup.

- Revisions: `0001` is the pre-auth schema; `0002` adds accounts and sessions; `0003` adds
  the four question-bank tables and their indexes (new tables only, nothing existing changes).
  `0004` adds the user role and status, `teacher_students` and the question review columns
  (additive; existing users became active students). See [access-control.md](access-control.md).
- A database created before migrations existed (tables present, no `alembic_version`) is
  stamped `0001` and then upgraded, with no data touched. This was verified on the running
  Postgres: 4 existing users were kept.
- A test checks that `head` matches the ORM models exactly.
- To create a new revision: `uv run alembic revision --autogenerate -m "…"`.

## 7. Content (versioned in git, validated at startup)

| Content | Source |
|---|---|
| Vocabulary | 7,351 items. CEFR level from the CEFR-J Wordlist 1.5; definition and example from Open English WordNet 2024 (CC BY 4.0) |
| Grammar | 42 exercises in 6 topics, with difficulty easy / medium / hard |
| Listening | 8 lessons. Scripts written by AI; audio generated with Piper TTS (LJSpeech voice, public-domain data) |
| Speaking | 6 prompts |
| Conversation | 4 scenarios |
| Calibration | 20 labelled answers |

- All AI-written content is `pending_review` until a teacher approves it.
- With `BANANA_REQUIRE_REVIEWED_CONTENT=true`, only approved content is served.

## 8. Observability

| Signal | What it records |
|---|---|
| `/metrics` (Prometheus) | `banana_llm_call_seconds` (histogram per provider and task), `banana_llm_calls_total{outcome}`, `banana_llm_tokens_total`, `banana_llm_cost_usd_total`, `banana_stt_seconds`, `banana_stt_audio_seconds_total`, `banana_http_request_seconds`, `banana_assessments_total{module,assessor}`, `banana_assessment_failures_total` |
| `X-Request-ID` | Accepted from the client or generated. Logged in JSON logs and stored in `llm_calls`, so a wrong grade can be traced to the exact prompt version and raw response |
| Prompt versions | Stored on every attempt, which answers "did the score change because the learner improved, or because we changed the prompt?" |

## 9. Configuration (`BANANA_*`)

| Setting | Default |
|---|---|
| `DATABASE_URL` | `sqlite:///…` (compose uses Postgres) |
| `REDIS_URL` | unset (in-memory cache) |
| `LLM_PROVIDER` | `mock` |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://127.0.0.1:11434` / unset, required with `ollama` (Compose: `banana/qwen3-8b:q6_K`, Qwen3-8B Q6_K) |
| `LLM_CONTEXT_LENGTH` / `LLM_TIMEOUT_SECONDS` | `8192` / `180` |
| `LLM_TEMPERATURE` / `LLM_MAX_OUTPUT_TOKENS` | unset (each task's own values) |
| `LLM_KEEP_ALIVE` / `LLM_WARM_UP` / `LLM_FALLBACK_MODEL` | `30m` / `true` / unset (no fallback) |
| `STT_PROVIDER` | `mock` (or `whisper`) |
| `WHISPER_MODEL` | `base.en` |
| `LLM_MAX_RETRIES` | `1` |
| `LLM_COST_PER_1K_TOKENS` | `0` |
| `REQUIRE_REVIEWED_CONTENT` | `false` |
| `DAILY_NEW_CARDS` | `10` |
| `JOB_WORKERS` | `2` |
| `MAX_UPLOAD_MB` | `10` |
| `SESSION_DAYS` | `30` |
| `COOKIE_SECURE` | `false` (set `true` behind HTTPS; compose reads `COOKIE_SECURE` from `.env`) |
| `ALLOW_LEARNER_HEADER` | `false` (development only) |
| `FEATURE_AI_MONKEY` | `true` |
| `LOG_JSON` | `false` |

## 10. Tests (159, no network or model needed)

| Level | What it covers |
|---|---|
| Unit | EMA properties; SM-2 over a 90-day simulation; the rubric; 11 kinds of schema rejection; grounding; retries; the cache key; the recommendation rules (including the past-tense scenario); content quality gates; fluency; the calibration regression gate |
| Integration (HTTP) | Every phase's loop end to end, the 503 path, request id → audit log, `/metrics`, the OpenAPI snapshot, and that exercise payloads never leak answers |
| Live (manual) | `scripts/smoke_live.py`, `scripts/calibrate.py`, `scripts/tutor_check.py` |
