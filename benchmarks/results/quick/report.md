# Banana English LLM benchmark

- Run: 2026-09-28T05:23:05+00:00 → 2026-09-28T05:47:51+00:00 (24.8 min), suite **quick**, dataset `bench_dataset_v1` (6 tests × 3 runs per model; before every run the model is reloaded and gets 2 warm-up calls)
- Host: AMD Ryzen 5 7535HS with Radeon Graphics, 12 logical CPUs, 14.3 GB RAM; Ollama 0.34.4; **CPU inference** (Ollama reports 0 GB in VRAM for every model)
- Same for every model: prompts bench_complex_question_v1, bench_vocabulary_v1, conversation_reply_v1, grammar_assessment_v6, monkey_chat_v1, tutor_explain_v2; production temperature and token limits per task; num_ctx 4096; seeds [43, 44, 45]; sampling top_k 20, top_p 0.95, min_p 0.0, repeat_penalty 1.0, presence_penalty 0.0; chat template of `qwen3:8b`; thinking off; same test order; each model alone in memory.

## Results

| Model | Quality | P50 | P95 | Tok/s | VRAM | Overall |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q6_K | 100.0 | 14.85 s | 42.19 s | 6.9 | 0.0 GB (RAM 7.4 GB) | **97.9** |
| Qwen3-8B Q8_0 | 96.1 | 16.24 s | 40.19 s | 5.4 | 0.0 GB (RAM 9.6 GB) | **93.2** |
| Qwen3-8B Q4_K_M | 92.3 | 11.71 s | 25.00 s | 8.7 | 0.0 GB (RAM 5.9 GB) | **93.1** |
| Qwen3-8B Q5_K_M | 93.7 | 16.10 s | 45.33 s | 8.1 | 0.0 GB (RAM 6.6 GB) | **92.6** |

Overall = 90% quality + 10% performance. Performance = 50% speed (fastest P50 ÷ this P50) + 50% throughput (tok/s ÷ fastest tok/s), relative to the models in this run. P50/P95 = end-to-end latency per request.

### Recommendation

**Qwen3-8B Q6_K** has the highest overall score (97.9: quality 100.0, performance 79.0). Its quality lead over Qwen3-8B Q8_0 (+3.9) is within the run-to-run spread (7.4 points), so the quality difference is not significant; speed and memory decide between them.

### Latency, throughput and memory

| Model | TTFT P50 | TTFT P95 | Mean latency | Mean output tokens | Memory | Load | Errors | Invalid replies |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q6_K | 9.95 s | 25.26 s | 19.08 s | 58.9 | 7.4 GB | 8.85 s | 0 | 0 |
| Qwen3-8B Q8_0 | 7.37 s | 18.74 s | 18.96 s | 59.9 | 9.6 GB | 8.07 s | 0 | 0 |
| Qwen3-8B Q4_K_M | 6.32 s | 15.75 s | 13.08 s | 55.5 | 5.9 GB | 12.34 s | 0 | 0 |
| Qwen3-8B Q5_K_M | 11.69 s | 29.59 s | 19.97 s | 61.1 | 6.6 GB | 7.32 s | 0 | 0 |

### Quality by rubric dimension (0–100)

| Model | grammar | explanation | naturalness | instruction following | relevance | vocabulary | conversation | Quality by run |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Qwen3-8B Q6_K | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0, 100.0, 100.0 |
| Qwen3-8B Q8_0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 72.7 | 100.0 | 96.1, 96.1, 96.1 |
| Qwen3-8B Q4_K_M | 77.8 | 70.0 | 100.0 | 98.4 | 100.0 | 100.0 | 100.0 | 94.8, 87.4, 94.8 |
| Qwen3-8B Q5_K_M | 83.3 | 100.0 | 100.0 | 100.0 | 100.0 | 72.7 | 100.0 | 93.7, 93.7, 93.7 |

### Quality by category (mean test score, 0–100)

| Model | complex | conversation | grammar correction | grammar explanation | vocabulary | voice |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q6_K | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Qwen3-8B Q8_0 | 100.0 | 100.0 | 100.0 | 100.0 | 81.2 | 100.0 |
| Qwen3-8B Q4_K_M | 100.0 | 100.0 | 71.4 | 86.7 | 100.0 | 100.0 |
| Qwen3-8B Q5_K_M | 100.0 | 100.0 | 85.7 | 100.0 | 81.2 | 100.0 |

### Models

| Model | Status | Ollama name | Source | Size | Template |
|---|---|---|---|---:|---|
| Qwen3-8B Q4_K_M | ok | `qwen3:8b` | ollama library | 5.2 GB | `ae370d884f10` |
| Qwen3-8B Q5_K_M | ok — weights of hf.co/Qwen/Qwen3-8B-GGUF:Q5_K_M, template + defaults of qwen3:8b | `bench/qwen3-8b-gguf-q5_k_m:aligned` | huggingface Qwen/Qwen3-8B-GGUF | 5.8 GB | `ae370d884f10` |
| Qwen3-8B Q6_K | ok — weights of hf.co/Qwen/Qwen3-8B-GGUF:Q6_K, template + defaults of qwen3:8b | `bench/qwen3-8b-gguf-q6_k:aligned` | huggingface Qwen/Qwen3-8B-GGUF | 6.7 GB | `ae370d884f10` |
| Qwen3-8B Q8_0 | ok | `qwen3:8b-q8_0` | ollama library | 8.8 GB | `ae370d884f10` |

## Method and limits

- Requests are captured from the production services (grammar assessment, tutor, conversation partner, AI Monkey), so the benchmark measures the prompts the app sends. Vocabulary cards and complex questions have no production prompt; they use the benchmark prompts in `tasks.py`.
- Quality is scored by deterministic checks (see `dataset.json`): valid output contract, correct verdict and correction against reviewed answers, required concepts, format and length limits, staying in role, no reasoning leak. They are reproducible but do not replace a teacher's judgement of nuance.
- Models imported from Hugging Face ship a different chat template (it ignores think=false) and other default parameters (presence_penalty 1.5). They are benchmarked through a local alias with the reference model's template and defaults (same weights, no copy), and every request sends the same sampling options, so only the weights differ between models.
- Grammar-correction labels come from the calibration set; they were drafted by an AI and are not yet teacher-verified.
- TTFT is measured on the client (request sent → first streamed token) and includes prompt processing; tok/s is Ollama's decode rate (output tokens ÷ decode time).
- Ollama caches the KV state of recent prompts. Each run therefore starts from a reloaded model (warm-up requests are not in the dataset), so no run is answered from an earlier run's cache; within a run, tests of the same task reuse their shared system prompt, as production requests do.
- Scores are relative to this hardware and this run; rerun after changing prompts, Ollama or hardware.
- Models loaded before the run (unloaded for fairness, reloaded on next use): none.
