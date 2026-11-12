# Calibration: grammar grading and the AI Tutor

All numbers on this page were measured with `ollama:qwen3:8b` on CPU, at temperature 0.

## Labels are not yet human-verified

The 20 calibration labels in `content/calibration/grammar_calibration.json` were drafted by an
AI following the rubric. Every item has `human_verified: false`.

- Until a teacher confirms or corrects them, the numbers below mean "the LLM agrees with the
  rubric draft". They do not yet mean "the LLM agrees with a teacher".
- Re-run `scripts/calibrate.py` after the labels are verified. Only then quote the numbers
  externally.

## Grammar prompt history

| Prompt | Change | Graded | MAE | Bias (LLM − label) | Within ±20 | is_correct agree |
|---|---|---|---|---|---|---|
| v2 | Score first, then errors | 19/20 | 20.7 | **+20.2** | 12/19 | 12/19 |
| v3 | Errors listed before the score | **5/20** | 25.0 | +25.0 | 1/5 | 5/5 |
| v4 | LLM gives categories only; score computed by the rubric; fragments grounded in the answer | 20/20 | 26.4 | **−25.4** | 8/20 | 14/20 |
| v5 | Severity derived from the error tag | 20/20 | 19.4 | −14.9 | 13/20 | 14/20 |
| **v6** | No reference answer for rewrite tasks; `point_tested` added | **20/20** | **15.7** | **+4.7** | **14/20** | **16/20** |

What each run taught us:

- **v2 — the model named the error, then scored 85–95 anyway.**
  - Feedback such as "You forgot the article 'an'" came with a passing score.
  - This consistent +20 bias is the "rubric bug" the spec warns about.
- **v3 — errors first made things worse.**
  - The model used `errors` as a checklist, adding entries like "The sentence is correct…".
  - It also graded the *exercise* sentence instead of the answer: for the answer "My sister is
    engineer" it reported the fragment "a engineer", which the learner never wrote.
  - The validator rejected 15 of 20 verdicts. Without that layer, those wrong scores would have
    reached mastery.
- **v4 — categories plus deterministic scoring.**
  - The LLM now only returns `errors`, with each fragment checked to appear in the answer, plus
    a `natural` flag. `domain/services/rubric.py` turns these into a score in the right band.
  - Every real error was caught.
  - But correct alternatives were marked wrong ("Yesterday I saw that film"), and every error
    was labelled "major".
- **v5 — severity comes from the error tag, not from the model.**
  - For example, `article` is minor and `verb_tense` is major.
  - The model still marked 6 of 6 correct alternatives as wrong: it anchored on the reference
    answer.
- **v6 — the reference answer is shown only for gap-fills.**
  - For gap-fills the expected word matters. For rewrites, the teacher's explanation is sent as
    `point_tested` instead of a reference answer.
  - Result: bias is near 0 and 16/20 verdicts agree with the labels.
  - Remaining misses: cal.004 (past perfect with "ago") and cal.016 (the rewrite changed the
    tense) are accepted when they should not be. cal.009 and cal.012 are penalised when they
    should not be.
  - **Two v6 runs gave identical scores (drift 0).** The run takes 235 s for 20 items.

Further mitigations in the product:

- Exact matches against reviewed answers never reach the LLM.
- The verdict cache makes identical answers score identically.
- The cheapest improvement is for the teacher to add the valid alternatives found here to
  `accepted_answers` (`scripts/review_content.py`, action `e`).

### Regression gate

`tests/unit/test_calibration_gate.py` runs in CI and fails when:

- the prompt version changed and calibration was not re-run for it;
- the recorded run has a bias or MAE of 20 or more, or any failures;
- any item drifted more than 10 points against `baseline.json`.

## Live findings beyond the calibration set

- **Free speech (Phase 7).** "Last weekend I go to the beach… we swim… we eat" first scored
  95. Speaking tasks now pass their target grammar as a hint ("past events need past tenses").
  After the fix the same transcript scores 15, with the three verb errors quoted exactly. The
  correct version scores 95, and a present-tense introduction still scores 95.
- **Cache key bug, found live.** The verdict cache key did not include the new hint, so Redis
  served the stale score of 95. Keys are now hashed from the full rendered prompt, and a
  regression test covers this.
- **Feedback text was not trustworthy.** For "I have saw that film yesterday", the score and
  error tag were right, but the LLM's feedback suggested "have seen". **Fixed:** for reviewed
  exercises, the feedback and corrections are now built from reviewed content, and an LLM
  correction is kept only when it appears in a reviewed answer. A regression test covers this.

## AI Tutor check (Phase 9)

`scripts/tutor_check.py` runs the tutor on real errors from the calibration set and writes
`tutor_check.md`, with a column for the teacher. The counts below are my own pre-review; a
teacher still has to verify them.

| Tutor prompt | ✅ clear & correct | ⚠️ vague | ❌ wrong | n/a (grader found no error) |
|---|---|---|---|---|
| v1 | 6 | 1 | **2** | 1 |
| **v2** — grounded in the exercise's teacher-written rule | 6 | 3 | **0** | 1 |

In v1, explanation #1 recommended "have seen" with "yesterday", and #5 inverted the rule about
"the" before a superlative. v2 passes the human-reviewed rule and the reviewed answer, and the
prompt tells the tutor never to contradict them.

## Files

- `latest.json`, `report.md` — the most recent run
- `baseline.json` — accepted scores used for the drift check
- `history/` — every prompt version's run
- `tutor_check.md` — the latest tutor explanations, for teacher review
