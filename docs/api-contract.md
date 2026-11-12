# Banana English API — v1

The machine-readable contract is [`openapi.json`](openapi.json). It is generated from
`src/banana_english/api/schemas/` by `scripts/export_openapi.py`, and a test fails if the code
and the snapshot drift apart. When the server is running, interactive docs are at `/docs`.

## Conventions

- **Base path:** `/api/v1`. Breaking changes require `/api/v2`.
- **Authentication:** register or sign in via `/auth/*`. The response sets an httpOnly,
  SameSite=Lax session cookie (`banana_session`), which the web app uses, and also returns
  the token, which API clients send as `Authorization: Bearer <token>`.
  - Sessions last 30 days. Only the token's SHA-256 is stored, and logout revokes the session.
  - Login failures give one generic message and are limited to 10 per 15 minutes per e-mail.
  - `X-Learner-Id` is accepted only when `BANANA_ALLOW_LEARNER_HEADER=true`, which is for
    development only.
- **Request tracing:** `X-Request-ID` is echoed back and stored in the LLM audit log.
- **Scale:** every score and every mastery value uses the unified 0–100 rubric: 90+ excellent,
  70–89 good, 40–69 minor error, 0–39 major error. `is_correct` means `score >= 70`.
- **Unknown request fields are rejected** with a 422. Exercise payloads never contain answers.
- **Slow grading:** `POST /grammar/attempt` and `POST /listening/attempt` accept
  `Prefer: respond-async` (RFC 7240). They then return 202 with a job, and the job's `result` is
  the usual `AttemptResponse`. Resubmitting the same answer while it is being graded returns the
  same job. A grading failure is a `failed` job with `result.attempt_id`, and mastery is unchanged.
- **Errors** use one envelope: `{"error": {"code", "message", "details"}}`.

| Status | Code | When |
|---|---|---|
| 401 | `unauthorized` | Missing, invalid, expired or revoked session; wrong e-mail or password |
| 404 | `not_found` | Unknown item |
| 429 | `too_many_attempts` | Too many failed logins |
| 409 | `conflict` | The conversation is finished or out of turns, or the transcript is still locked |
| 422 | `validation_error`, `invalid_input` | Schema violation; empty or unsupported upload |
| 503 | `assessment_unavailable` | The LLM output was invalid after a retry. The attempt is recorded (`details.attempt_id`) and **mastery is unchanged** |
| 503 | `provider_unavailable` | The conversation partner could not reply |

## Endpoints

| Method & path | Phase | Purpose |
|---|---|---|
| `POST /auth/register` | — | `{email, password (≥ 8), display_name, current_level, target_level, native_language?}`. Returns 201 with `{token, expires_in_seconds, profile}` and sets the cookie. A duplicate e-mail returns 409 |
| `POST /auth/login` | — | `{email, password}`. Returns 200, same shape as register; 401 or 429 on failure |
| `POST /auth/logout` | — | Revokes the session and clears the cookie. Returns 204 |
| `GET /auth/me` | — | The signed-in learner's profile |
| `GET /learner/profile` | 4 | Profile, plus assessed and correct attempt counts |
| `GET /learner/mastery` | 4 | Every skill tag: mastery, effective mastery (after forgetting), confidence, counts, `is_weak` |
| `GET /learner/weak-skills?limit=` | 5/10 | Skills below 60, weakest first — **the same query the recommender uses** |
| `GET /learner/mastery-history?skill_id=&days=` | 10 | Mastery after every attempt, from `mastery_events` |
| `GET /learner/activity?days=` | 10 | Attempts per day, days active, current streak |
| `GET /learner/attempts?limit=` | 9 | Recent attempts, with their ids, for the tutor |
| `GET /recommendation/next?n=` | 5 | Next activities, each with `kind` (reinforcement / review / new_topic / practice), `reason_code`, `reason`, `evidence` and `items` |
| `GET /vocabulary/due?limit=` | 2 | Due cards first, then new cards up to the daily limit. Each has a front (definition + blanked example), a back (word) and its SM-2 state |
| `POST /vocabulary/review` | 2 | `{card_id, rating: again\|hard\|good\|easy, answer?}`. Returns the applied rating, the new SM-2 state, and the mastery change |
| `GET /grammar/topics`, `GET /grammar/exercises?skill_id=&difficulty=`, `GET /grammar/exercises/{id}` | 3 | Browse grammar exercises |
| `POST /grammar/attempt` | 3 | `{exercise_id, answer}`. Returns an `AttemptResponse`, or 503. With `Prefer: respond-async`: 202 and a job |
| `GET /listening/lessons`, `GET /listening/lessons/{id}` | 6 | Lessons, with `audio_url` (`/media/listening/*.wav`) and the questions |
| `GET /listening/lessons/{id}/transcript` | 6 | The transcript and answers. Returns 409 until every question has been attempted |
| `POST /listening/attempt` | 6 | `{question_id, answer}`. Returns an `AttemptResponse`. With `Prefer: respond-async`: 202 and a job |
| `GET /speaking/prompts` | 7 | Speaking tasks |
| `POST /speaking/attempt` (multipart: `prompt_id`, `audio`) | 7 | Returns 202 with a job. Poll `GET /jobs/{id}` for `{transcript, grammar, fluency, mastery_changes}` |
| `GET /conversation/scenarios` | 8 | The role-play scenarios |
| `POST /conversations` → `POST /conversations/{id}/messages` → `POST /conversations/{id}/finish` | 8 | Start, talk (the partner replies in character), then finish. Finishing returns 202 with a job whose result is the graded turns, error counts and mastery changes |
| `GET /conversations/{id}` | 8 | Turns, status, and the summary |
| `POST /tutor/explain` | 9 | `{attempt_id, mistake_index}`. Returns `{error_tag, explanation, example, prompt_version, model}` |
| `POST /monkey/chat` | AI Monkey | `{messages: [{role: learner\|monkey, text}], preferences?}`, oldest first, ending with the learner. Returns `{reply, prompt_version, model, preferences, policy, changes}`. The server keeps no history, and only the last 12 turns reach the model. Not graded, and mastery is never changed. 503 `provider_unavailable` if the model is down. Optional `preferences` (bilingual tutor): `{mode: auto\|immersion\|vietnamese_support\|bilingual\|free_chat\|custom, conversation_language, explanation_language, correction_language: auto\|en\|vi, corrections: auto\|off\|strict}`, all `auto` by default. Natural commands in the message ("từ giờ chỉ nói tiếng Anh", "đừng sửa lỗi nữa") come back as updated `preferences` and human-readable `changes`; the client keeps them and sends them with the next message. Without `preferences`, they are rebuilt from the commands in the history. `policy` is what this reply used (auto resolved) |
| `POST /monkey/transcribe` (multipart: `audio`) | AI Monkey | Returns `{text, duration_seconds}` from Whisper. The audio is deleted right after transcription |
| `POST /monkey/speech` | AI Monkey | `{text}` (at most 600 characters). Returns `audio/wav` (Piper, 16-bit PCM) with `Cache-Control: no-store`. 503 `provider_unavailable` if there is no voice |
| `GET /bank/{skill}/facets` | Question bank | `skill`: grammar \| vocabulary \| reading \| listening. Counts of the served pool per level, topic, grammar point, question type and difficulty, plus `point_names` |
| `POST /bank/{skill}/sets` | Question bank | `{levels?, topics?, points?, qtypes?, difficulties?, count (1–50, default 10)}`; an empty list means "any". Returns `{skill, questions, passages, review_count}`: a new set drawn from the pool on every call, unseen questions first, plus a share of due reviews and weak-skill questions. **Questions carry no answers**; listening passages carry `audio_url` but `text: null` |
| `POST /bank/answer` | Question bank | `{question_id, answer, response_time_ms?}`. `answer` is an option id (mcq, true_false, error_id), text (fill_blank, dictation), the pieces in order (ordering) or `{left_id: option_id}` (matching). Checked by rules, never by the LLM: returns `{attempt_id, correct, score, correct_answer, explanation, explanation_vi, detail, mastery}` in the same request. Records an attempt (`assessor: deterministic`), the mastery change and the learner's history of the question. 422 for an answer of the wrong shape, 404 for an unknown or disabled question |
| `GET /bank/passages/{id}/transcript` | Question bank | A listening recording's transcript. 409 until the learner has answered a question about it |
| `GET /bank/{skill}/summary` | Question bank | `{pool_size, questions_seen, correct_answers, wrong_answers, to_review}` for the signed-in learner |
| `GET /bank/{skill}/review` | Access control | Teachers and admins (403 otherwise). `?status=&level=&point=&q=&limit=&offset=`. Questions of any status **with their answers** and explanations, plus `reviewed_by` / `reviewed_at` |
| `PATCH /bank/questions/{id}` | Access control | Teachers and admins. `{status: approved\|validated\|disabled}`. The decision is kept across bank imports while the question's content does not change |
| `GET /teacher/students` | Access control | Teachers (their assigned students) and admins (all students). `?q=&limit=&offset=`. `{total, users: [{user_id, display_name, email, role, is_active, created_at, attempts, correct, last_active}]}` |
| `GET /teacher/students/{id}/progress`, `/attempts` | Access control | `{student, mastery, weak_skills, activity}` (the learner's own shapes) and recent attempts. 403 for a student not assigned to the teacher |
| `GET /admin/users`, `GET /admin/users/{id}` | Access control | Admins only. Search by name or e-mail, filter `role`, `active`; detail adds `teacher_ids`, `student_ids` |
| `PATCH /admin/users/{id}` | Access control | Admins only. `{role?, is_active?}` (anything else is a 422). 403 on your own account; 409 for the last active admin. Disabling revokes every session |
| `PUT` / `DELETE /admin/users/{teacher_id}/students/{student_id}` | Access control | Admins only. Link or unlink a teacher and a student (422 unless teacher → student) |
| `GET /admin/stats` | Access control | Admins only. Users per role and status, answers in 7 days, bank questions per skill and status, last import, configuration summary |
| `GET /features` | — | `{ai_monkey}`. Public. When a flag is off, the feature's endpoints return 404 |
| `GET /jobs/{id}` | 3/6/7/8 | `queued \| running \| succeeded \| failed`, with the `result` or the `error` |
| `GET /health`, `GET /api/v1/health`, `GET /metrics` | 11 | Liveness; `/api/v1/health` adds the configuration and prompt versions for admins only; Prometheus metrics (API port only, not proxied) |

## `AttemptResponse`

Returned by the grammar and listening attempt endpoints. The vocabulary review response has
the same parts, plus the card's SM-2 state.

```json
{
  "attempt_id": "…", "item_id": "gr.past.004", "skill_id": "grammar.past_simple_present_perfect",
  "submitted_at": "…",
  "assessment": {
    "score": 25, "is_correct": false, "band": "major_error",
    "feedback": "…", "corrected_answer": "…",
    "mistakes": [{"category": "verb_form", "explanation": "…", "fragment": "have saw", "correction": "saw"}],
    "assessor": "llm", "prompt_version": "grammar_assessment_v6", "model": "banana/qwen3-8b:q6_K"
  },
  "reference_answers": ["I saw that film yesterday."],
  "explanation": "'Yesterday' is a finished past time. …",
  "mastery_changes": [{"skill_id": "grammar.past_simple_present_perfect", "before": 50.0, "after": 42.5, "attempt_count": 1}],
  "next_recommendation": {"kind": "reinforcement", "skill_id": "…", "reason": "…", "items": […]}
}
```

- `assessor` is one of `deterministic`, `self_rated`, `reference_match` or `llm`.
- `reference_answers` and `explanation` always come from reviewed content, never from the LLM.
- For reviewed exercises, the learner-facing `feedback` and `corrected_answer` are also built
  from reviewed content: "Check “<fragment>”. A correct answer: “<closest reviewed answer>”".
  A `mistakes[].correction` is kept only if it appears in a reviewed answer.
- LLM free text is shown only for free production (speaking and conversation), where no
  reviewed answer exists.

## LLM output contracts (internal)

The model is never asked for a number. It returns categories, and the platform computes the
score with the rubric.

**Grammar (`grammar_assessment_v6`):**

```json
{"errors": [{"fragment": "<copied from the answer>", "tag": "<grammar tag>", "correction": "…", "explanation": "…"}],
 "natural": true, "corrected_answer": "…|null", "feedback": "…"}
```

- The score is 95 or 80 when there are no errors (natural or not).
- One minor error scores 55, two or more minor errors score 45.
- One major error scores 25, two or more major errors score 15.
- Severity comes from the tag: article, preposition, spelling, word_choice and
  comparative_form are minor; the rest are major.

**Listening (`listening_assessment_v2`):** `{"understood": "fully|partly|not", "feedback": "…"}`,
scored 95 / 55 / 15.

**Tutor (`tutor_explain_v2`):** `{"explanation": "…", "example": "<a new sentence>"}`. It is
grounded in the exercise's teacher-written rule.

**AI Monkey (`monkey_chat_v1`):** plain text, 1–3 sentences at the learner's CEFR level, with at most one "(Tip: …)". Role labels, quotes and emoji are stripped.

**Conversation (`conversation_reply_v1`):** plain text. Any `<think>` block, role labels and
quotes are stripped, and the reply is capped at 400 characters.
