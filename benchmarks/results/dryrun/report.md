# Banana English LLM benchmark

- Run: 2026-09-28T04:21:16+00:00 → 2026-09-28T04:28:44+00:00 (7.5 min), suite **full**, dataset `bench_dataset_v1` (48 tests × 1 runs per model; before every run the model is reloaded and gets 1 warm-up calls)
- Host: AMD Ryzen 5 7535HS with Radeon Graphics, 12 logical CPUs, 14.3 GB RAM; Ollama 0.34.4; **CPU inference** (Ollama reports 0 GB in VRAM for every model)
- Same for every model: prompts bench_complex_question_v1, bench_vocabulary_v1, conversation_reply_v1, grammar_assessment_v6, monkey_chat_v1, tutor_explain_v2; production temperature and token limits per task; num_ctx 4096; seeds [43]; sampling top_k 20, top_p 0.95, min_p 0.0, repeat_penalty 1.0, presence_penalty 0.0; chat template of `qwen3:8b`; thinking off; same test order; each model alone in memory.

## Results

| Model | Quality | P50 | P95 | Tok/s | VRAM | Overall |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M | 91.6 | 9.13 s | 16.41 s | 8.6 | 0.0 GB (RAM 5.9 GB) | **92.4** |

Overall = 90% quality + 10% performance. Performance = 50% speed (fastest P50 ÷ this P50) + 50% throughput (tok/s ÷ fastest tok/s), relative to the models in this run. P50/P95 = end-to-end latency per request.

### Recommendation

**Qwen3-8B Q4_K_M** has the highest overall score (92.4: quality 91.6, performance 100.0).

### Latency, throughput and memory

| Model | TTFT P50 | TTFT P95 | Mean latency | Mean output tokens | Memory | Load | Errors | Invalid replies |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M | 2.52 s | 6.60 s | 8.99 s | 52.8 | 5.9 GB | 12.34 s | 0 | 0 |

### Quality by rubric dimension (0–100)

| Model | grammar | explanation | naturalness | instruction following | relevance | vocabulary | conversation | Quality by run |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Qwen3-8B Q4_K_M | 73.8 | 87.7 | 98.2 | 94.8 | 93.5 | 95.5 | 97.9 | 91.6 |

### Quality by category (mean test score, 0–100)

| Model | complex | conversation | grammar correction | grammar explanation | vocabulary | voice |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M | 95.2 | 95.0 | 80.5 | 92.9 | 97.7 | 92.4 |

### Models

| Model | Status | Ollama name | Source | Size | Template |
|---|---|---|---|---:|---|
| Qwen3-8B Q4_K_M | ok | `qwen3:8b` | cli | 5.2 GB | `ae370d884f10` |

## Method and limits

- Requests are captured from the production services (grammar assessment, tutor, conversation partner, AI Monkey), so the benchmark measures the prompts the app sends. Vocabulary cards and complex questions have no production prompt; they use the benchmark prompts in `tasks.py`.
- Quality is scored by deterministic checks (see `dataset.json`): valid output contract, correct verdict and correction against reviewed answers, required concepts, format and length limits, staying in role, no reasoning leak. They are reproducible but do not replace a teacher's judgement of nuance.
- Models imported from Hugging Face ship a different chat template (it ignores think=false) and other default parameters (presence_penalty 1.5). They are benchmarked through a local alias with the reference model's template and defaults (same weights, no copy), and every request sends the same sampling options, so only the weights differ between models.
- Grammar-correction labels come from the calibration set; they were drafted by an AI and are not yet teacher-verified.
- TTFT is measured on the client (request sent → first streamed token) and includes prompt processing; tok/s is Ollama's decode rate (output tokens ÷ decode time).
- Ollama caches the KV state of recent prompts. Each run therefore starts from a reloaded model (warm-up requests are not in the dataset), so no run is answered from an earlier run's cache; within a run, tests of the same task reuse their shared system prompt, as production requests do.
- Scores are relative to this hardware and this run; rerun after changing prompts, Ollama or hardware.
- Models loaded before the run (unloaded for fairness, reloaded on next use): none.
