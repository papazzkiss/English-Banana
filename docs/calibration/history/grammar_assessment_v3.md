# Grammar assessment calibration

- Run: 2026-09-27T09:36:47+00:00 — provider `ollama:qwen3:8b`, prompt `grammar_assessment_v3`, 513.2 s total
- Labels verified by a human: **0/20** (the rest are AI-drafted rubric labels awaiting teacher review)
- Graded: 5/20 (failed after retry: 15)
- Mean absolute error vs labels: **25.0** points; bias (LLM − label): **+25.0**
- Within ±20 points: **1/5**; is_correct agreement: **5/5**
- Drift vs baseline (4 items): max 20.0 points; over ±10: ['cal.005', 'cal.016', 'cal.018']

| id | answer | label | LLM | diff | note |
|---|---|---|---|---|---|
| cal.001 | Yesterday I saw that film. | 95 | — | — | valid reordering |
| cal.002 | I seen that film yesterday. | 25 | — | — | past participle instead of past simple |
| cal.003 | I did see that film yesterday. | 75 | — | — | grammatical but emphatic/awkward |
| cal.004 | He had finished his homework two hours ago. | 35 | — | — | past perfect with 'ago' and no reference point: wrong tense |
| cal.005 | I am learning English for five years. | 25 | 60 | +35 | present continuous instead of present perfect |
| cal.006 | I have been studying English for five years. | 92 | — | — | synonym 'study', same meaning |
| cal.007 | My sister is engineer. | 45 | — | — | missing article |
| cal.008 | Mount Everest is highest mountain in the world. | 50 | — | — | missing 'the' before superlative |
| cal.009 | Everest is the highest mountain in the world. | 90 | — | — | correct, 'Mount' dropped |
| cal.010 | I'll meet you at bus stop. | 50 | — | — | preposition fixed, article missing |
| cal.011 | We arrived at London late at night. | 50 | — | — | arrive at + city |
| cal.012 | We got to London late at night. | 85 | — | — | correct paraphrase avoiding 'arrive' |
| cal.013 | My brother is more taller than me. | 45 | — | — | double comparative |
| cal.014 | This book is more interesting then the film. | 55 | — | — | then/than confusion |
| cal.015 | Your car is more faster than my car. | 45 | 60 | +15 | double comparative |
| cal.016 | They are not playing football every Saturday. | 30 | 60 | +30 | continuous for a habit |
| cal.017 | When I see him, I will tell him. | 85 | — | — | correct; 'when' instead of 'if' |
| cal.018 | If she studied harder, she will pass the exam. | 35 | 60 | +25 | mixed second/first conditional |
| cal.019 | If I knew her number, I can call her. | 40 | 60 | +20 | present modal in second conditional |
| cal.020 | I knows the answer. | 45 | — | — | subject-verb agreement |
