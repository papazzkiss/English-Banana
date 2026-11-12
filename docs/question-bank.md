# Question bank

The question bank is a pool of about 100,000 grammar, vocabulary, reading and listening
questions (A1–C1). Every practice set is drawn from it on request, and every answer is checked
by rules in the same request. The LLM is never on the answer path; it is only used when the
learner asks the AI Tutor or AI Monkey for a deeper explanation.

It extends the existing app: the lesson content, the LLM-graded grammar and listening
exercises, mastery, the recommender and history all work as before. A bank answer is recorded
as an ordinary attempt (`assessor: deterministic`), so it moves mastery and appears in history
and on the dashboard like any other answer.

## Pipeline

```
fetch ─► parse (spaCy, cached) ─► classify (CEFR, topic) ─► generate ─► validate ─► dedupe
      ─► score quality ─► select (quotas per level / point / type) ─► write shards ─► import
```

```bash
uv sync --group content                                   # spaCy + model, wordfreq, lemminflect
uv run python -m banana_english.contentbank fetch         # download the corpora (resumable)
uv run python -m banana_english.contentbank build grammar vocabulary reading listening
uv run python -m banana_english.contentbank audio         # listening recordings (Piper, resumable)
uv run python -m banana_english.contentbank import        # into the database (idempotent)
python scripts/audit_content.py [--db] [--json report.json]
python3 scripts/bench_bank.py                             # latency against a running stack
```

- **Sources.** Tatoeba sentences with human Vietnamese translations (CC BY 2.0 FR), Simple
  English and English Wikipedia (CC BY-SA 4.0), Vietnamese and English Wiktionary via kaikki
  (CC BY-SA 4.0), CEFR-J 1.5, Open English WordNet 2024 (CC BY 4.0) and wordfreq. Every
  download is recorded with its size and hash in `var/content_sources/sources.lock.json`.
- **Resumable.** Parsed text is cached per 20,000-text chunk in `var/content_cache/`, audio
  files that exist are kept, and the import only writes what changed.
- **Output.** `content/bank/{questions,passages}/<skill>-NNN.jsonl.gz` (5,000 records per
  shard, byte-stable) and `content/bank/manifest.json` (counts, shard hashes and one overall
  hash). Audio goes to `content/bank/audio/` and is mounted into the API container, not baked
  into the image. Each recording is named after its passage id and a hash of its text, so a
  changed text is recorded again; `audio` removes recordings no passage uses any more. Run
  `audio` after every `build listening`: it also writes each recording's duration, and a
  passage whose audio failed becomes a draft.
- **Import.** On startup the API compares the manifest hash with the last import and, when it
  changed, imports in a background thread (`BANANA_BANK_AUTO_IMPORT`, on by default). Records
  are upserted by content hash; records that left the bank are set to `disabled`, never
  deleted, so learner history keeps pointing at them.

## One right answer

Questions are generated from real sentences, so the generators only ask what the sentence
itself decides. Each rule below has a unit test in `tests/unit/test_contentbank.py`.

- **Tense choice** only when a signal in the sentence ("yesterday", "since 2010", "at the
  moment") rules out every distractor, and never with a distractor that could also fit (no
  past continuous against the past simple).
- **Form questions** offer the right form and forms that are wrong in agreement or verb form
  ("has come", "have came", "have coming" for "have come").
- **Left out:** verbs with two past participles (got/gotten), ergative verbs in the passive
  ("was filled"), verbs whose past equals the base (put, cut) in past-simple questions,
  collective-noun subjects in agreement questions, and "there + be" distractors of the right
  number in another tense.
- **Linkers** are tested only with distractors that are grammatically impossible in the gap
  ("despite" before a clause).
- **Reading and listening.** False statements change one number or one person or organisation
  (never a place: Paris and France can both be true). Name distractors never share a word with
  the answer ("Brunei" / "Brunei Darussalam"). Wikipedia passages are shown under a neutral
  title, because the article title is the answer to "What is the text mainly about?".
- **Vocabulary.** Synonyms must be each other's first WordNet sense and both be learner words;
  words with 8 or more senses get no definition question. A Vietnamese-meaning question is
  asked only when the meaning is clear: it is confirmed from the Vietnamese side (the English
  Wiktionary glosses "vịnh" as "bay", so "bay" means "vịnh", not "ngựa hồng"), or the word has
  a single meaning. No other meaning of the word is ever a distractor. Wiktionary notes
  ("xem …", "dạng quá khứ của …") are never used as meanings.
- **Content filter.** Violence, drugs, sex, insults and similar vocabulary are blocked.

## Quality and status

Every record is validated against a strict schema (`contentbank/schema.py`): required fields,
an answer that exists among the options, no duplicate options, lengths, and levels. A quality
score (0–1) starts from the generator's confidence in the question type and is adjusted for
sentence length, the number of names and digits, and (for Tatoeba) whether a person
translated the sentence into Vietnamese; passages lose points for being very short or
number-heavy. Status:

| Status | Meaning | Served |
|---|---|---|
| `draft` | Quality below 0.6 | No |
| `validated` | Passed every automatic check | Yes |
| `approved` | Reviewed by a teacher | Yes; the only status served with `BANANA_REQUIRE_REVIEWED_CONTENT=true` |
| `disabled` | Removed from the bank, or turned off by hand | No |

Near-duplicates are removed before selection: the key normalises case, punctuation, names and
numbers, so "Tom is a teacher." and "Mary is a teacher." count as one.

## Practice sets and anti-repetition

`POST /api/v1/bank/{skill}/sets` builds a set in one short transaction:

1. **Review:** up to 25% of the set are questions the learner got wrong more than 12 hours ago.
2. **Weak skills:** 40% of the rest come from the learner's weakest skills in that module
   (unless the learner picked a grammar point).
3. **New:** the rest are questions the learner has never seen, spread over grammar points.
4. **Fallback:** when the filtered pool is used up, the questions seen longest ago come back,
   but never one seen in the last hour.

Reading and listening sets are built from whole passages (up to 6 questions each, main idea
first), preferring passages the learner has not read.

**No `ORDER BY RANDOM()`.** Each question has a random key `rand` in a composite index
(`skill, status, level, rand`). A set reads `rand >= pivot ORDER BY rand LIMIT k` from a random
pivot (wrapping around), with a `NOT EXISTS` on the learner's history, so the cost does not grow
with the pool.

## Answer checking

`domain/services/answer_check.py` is pure Python and takes microseconds:

| Type | Check |
|---|---|
| `mcq`, `true_false`, `error_id` | The option id |
| `fill_blank` | Normalised text against every accepted answer |
| `dictation` | Word-level accuracy; 90% or more counts as correct, the score is the accuracy |
| `ordering` | The pieces in order |
| `matching` | Each pair; the score is the share of right pairs |

The request returns the result, the correct answer, the explanation in English and
Vietnamese, and the mastery change. Questions are sent without answers, and listening
transcripts only after the learner has answered.

## What the bank holds (audit, 2026-09-29)

| | A1 | A2 | B1 | B2 | C1 | Total |
|---|---:|---:|---:|---:|---:|---:|
| Grammar | 3,035 | 5,502 | 7,169 | 5,993 | 4,301 | 26,000 |
| Vocabulary | 3,489 | 4,872 | 6,615 | 6,063 | 4,961 | 26,000 |
| Reading | 4,385 | 4,229 | 4,863 | 6,893 | 5,640 | 26,010 |
| Listening | 5,386 | 3,484 | 3,716 | 8,750 | 3,974 | 25,310 |
| **Total** | 16,295 | 18,087 | 22,363 | 27,699 | 18,876 | **103,320** |

- Served (`validated`): 103,320; `draft`: 70 (listening, below the quality bar).
- 13,031 passages: 6,391 reading texts and 6,640 recordings (52.5 hours, 400 MB, Ogg Opus).
- 25 grammar points; 9,797 words (8,890 with a Vietnamese meaning); 18 topics; 7 question
  types (mcq 71,133, true/false 23,539, find-the-mistake 4,093, matching 1,597, fill-in 1,094,
  dictation 996, word order 868).
- Duplicates 0.000%, near-duplicates 0.076%, invalid records 0; quality mean 0.846
  (p10 0.76, min 0.63); right answers spread over a/b/c/d (19,557 / 19,580 / 18,460 /
  17,629).

## Speed

The running Docker stack (PostgreSQL 16, 103,390 questions), measured through the web proxy
with `python3 scripts/bench_bank.py --sets 40` (160 sets, 1,716 answers):

| | p50 | p95 |
|---|---|---|
| `POST /bank/{skill}/sets` (10 questions) | 14–16 ms | 19–50 ms (reading and listening load passages too) |
| `POST /bank/answer` (check + attempt + mastery + history, one transaction) | 9–10 ms | 11–12 ms |
| `check_answer` (the rules alone) | 8 µs | |
| Import of the whole bank | 20 s at API start-up, once per new manifest | |

For comparison, an LLM-graded grammar answer takes 12–14 s. Under heavy CPU load (audio
synthesis running on the same machine) sets stayed under 161 ms p95 and answers under 105 ms.

The query that picks unseen questions runs in about 8 ms (`EXPLAIN ANALYZE`: an index scan on
`ix_bank_questions_pick` with an anti-join on the learner's history, no sort of the pool).
No question repeated: 0 of 1,716 served in 160 sets.

## Database

Migration `0003_question_bank` adds four tables and changes nothing existing: `bank_passages`,
`bank_questions`, `learner_question_stats` and `bank_imports`. See
[architecture.md](architecture.md#6-data-postgresql-sqlite-in-tests).
