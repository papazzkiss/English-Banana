# Banana English LLM benchmark

- Run: 2026-09-28T04:15:12+00:00 → 2026-09-28T04:19:00+00:00 (3.8 min), suite **quick**, dataset `bench_dataset_v1` (6 tests × 1 runs per model; before every run the model is reloaded and gets 1 warm-up calls)
- Host: AMD Ryzen 5 7535HS with Radeon Graphics, 12 logical CPUs, 14.3 GB RAM; Ollama 0.34.4; **CPU inference** (Ollama reports 0 GB in VRAM for every model)
- Same for every model: prompts bench_complex_question_v1, bench_vocabulary_v1, conversation_reply_v1, grammar_assessment_v6, monkey_chat_v1, tutor_explain_v2; production temperature and token limits per task; num_ctx 4096; seeds [43]; sampling top_k 20, top_p 0.95, min_p 0.0, repeat_penalty 1.0, presence_penalty 0.0; chat template of `qwen3:8b`; thinking off; same test order; each model alone in memory.

## Results

| Model | Quality | P50 | P95 | Tok/s | VRAM | Overall |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M | 94.8 | 11.63 s | 22.76 s | 8.6 | 0.0 GB (RAM 5.9 GB) | **95.3** |
| Qwen3-8B Q5_K_M | 93.7 | 16.44 s | 39.85 s | 7.9 | 0.0 GB (RAM 6.6 GB) | **92.5** |

Overall = 90% quality + 10% performance. Performance = 50% speed (fastest P50 ÷ this P50) + 50% throughput (tok/s ÷ fastest tok/s), relative to the models in this run. P50/P95 = end-to-end latency per request.

### Recommendation

**Qwen3-8B Q4_K_M** has the highest overall score (95.3: quality 94.8, performance 100.0). Its quality lead over Qwen3-8B Q5_K_M (+1.1) is larger than the run-to-run spread (0.0 points).

### Latency, throughput and memory

| Model | TTFT P50 | TTFT P95 | Mean latency | Mean output tokens | Memory | Load | Errors | Invalid replies |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M | 6.41 s | 14.06 s | 13.00 s | 52.5 | 5.9 GB | 12.33 s | 0 | 0 |
| Qwen3-8B Q5_K_M | 11.93 s | 25.91 s | 20.34 s | 60.7 | 6.6 GB | 5.56 s | 0 | 0 |

### Quality by rubric dimension (0–100)

| Model | grammar | explanation | naturalness | instruction following | relevance | vocabulary | conversation | Quality by run |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Qwen3-8B Q4_K_M | 83.3 | 80.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 94.8 |
| Qwen3-8B Q5_K_M | 83.3 | 100.0 | 100.0 | 100.0 | 100.0 | 72.7 | 100.0 | 93.7 |

### Quality by category (mean test score, 0–100)

| Model | complex | conversation | grammar correction | grammar explanation | vocabulary | voice |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M | 100.0 | 100.0 | 71.4 | 100.0 | 100.0 | 100.0 |
| Qwen3-8B Q5_K_M | 100.0 | 100.0 | 85.7 | 100.0 | 81.2 | 100.0 |

### Models

| Model | Status | Ollama name | Source | Size | Template |
|---|---|---|---|---:|---|
| Qwen3-8B Q4_K_M | ok | `qwen3:8b` | cli | 5.2 GB | `ae370d884f10` |
| Qwen3-8B Q5_K_M | ok — weights of hf.co/Qwen/Qwen3-8B-GGUF:Q5_K_M, template + defaults of qwen3:8b | `bench/qwen3-8b-gguf-q5_k_m:aligned` | cli | 5.8 GB | `ae370d884f10` |

## Method and limits

- Requests are captured from the production services (grammar assessment, tutor, conversation partner, AI Monkey), so the benchmark measures the prompts the app sends. Vocabulary cards and complex questions have no production prompt; they use the benchmark prompts in `tasks.py`.
- Quality is scored by deterministic checks (see `dataset.json`): valid output contract, correct verdict and correction against reviewed answers, required concepts, format and length limits, staying in role, no reasoning leak. They are reproducible but do not replace a teacher's judgement of nuance.
- Models imported from Hugging Face ship a different chat template (it ignores think=false) and other default parameters (presence_penalty 1.5). They are benchmarked through a local alias with the reference model's template and defaults (same weights, no copy), and every request sends the same sampling options, so only the weights differ between models.
- Grammar-correction labels come from the calibration set; they were drafted by an AI and are not yet teacher-verified.
- TTFT is measured on the client (request sent → first streamed token) and includes prompt processing; tok/s is Ollama's decode rate (output tokens ÷ decode time).
- Ollama caches the KV state of recent prompts. Each run therefore starts from a reloaded model (warm-up requests are not in the dataset), so no run is answered from an earlier run's cache; within a run, tests of the same task reuse their shared system prompt, as production requests do.
- Scores are relative to this hardware and this run; rerun after changing prompts, Ollama or hardware.
- Models loaded before the run (unloaded for fairness, reloaded on next use): none.
