# Grammar assessment calibration

- Run: 2026-09-29T19:13:28+00:00 — provider `ollama:qwen3:30b-a3b-q4_K_M`, prompt `grammar_assessment_v6`, 1149.8 s total
- Labels verified by a human: **0/20** (the rest are AI-drafted rubric labels awaiting teacher review)
- Graded: 20/20 (failed after retry: 0)
- Mean absolute error vs labels: **8.15** points; bias (LLM − label): **+1.15**
- Within ±20 points: **18/20**; is_correct agreement: **20/20**
- Drift vs baseline (20 items): max 70.0 points; over ±10: ['cal.004', 'cal.009', 'cal.012', 'cal.016']

| id | answer | label | LLM | diff | note |
|---|---|---|---|---|---|
| cal.001 | Yesterday I saw that film. | 95 | 95 | +0 | valid reordering |
| cal.002 | I seen that film yesterday. | 25 | 25 | +0 | past participle instead of past simple |
| cal.003 | I did see that film yesterday. | 75 | 95 | +20 | grammatical but emphatic/awkward |
| cal.004 | He had finished his homework two hours ago. | 35 | 25 | -10 | past perfect with 'ago' and no reference point: wrong tense |
| cal.005 | I am learning English for five years. | 25 | 15 | -10 | present continuous instead of present perfect |
| cal.006 | I have been studying English for five years. | 92 | 95 | +3 | synonym 'study', same meaning |
| cal.007 | My sister is engineer. | 45 | 55 | +10 | missing article |
| cal.008 | Mount Everest is highest mountain in the world. | 50 | 55 | +5 | missing 'the' before superlative |
| cal.009 | Everest is the highest mountain in the world. | 90 | 95 | +5 | correct, 'Mount' dropped |
| cal.010 | I'll meet you at bus stop. | 50 | 55 | +5 | preposition fixed, article missing |
| cal.011 | We arrived at London late at night. | 50 | 55 | +5 | arrive at + city |
| cal.012 | We got to London late at night. | 85 | 95 | +10 | correct paraphrase avoiding 'arrive' |
| cal.013 | My brother is more taller than me. | 45 | 55 | +10 | double comparative |
| cal.014 | This book is more interesting then the film. | 55 | 55 | +0 | then/than confusion |
| cal.015 | Your car is more faster than my car. | 45 | 55 | +10 | double comparative |
| cal.016 | They are not playing football every Saturday. | 30 | 25 | -5 | continuous for a habit |
| cal.017 | When I see him, I will tell him. | 85 | 95 | +10 | correct; 'when' instead of 'if' |
| cal.018 | If she studied harder, she will pass the exam. | 35 | 25 | -10 | mixed second/first conditional |
| cal.019 | If I knew her number, I can call her. | 40 | 25 | -15 | present modal in second conditional |
| cal.020 | I knows the answer. | 45 | 25 | -20 | subject-verb agreement |
