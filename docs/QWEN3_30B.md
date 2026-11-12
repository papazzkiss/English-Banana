# Qwen3-30B-A3B: the production LLM

Banana English runs **Qwen3-30B-A3B** through Ollama. It is a mixture-of-experts model: 30.5B
parameters in total, about 3.3B active per token, so it answers at the speed of a small model
with the knowledge of a large one. It is Qwen3's hybrid model: one model with a thinking mode
and a non-thinking mode, chosen per request.

## On this machine

Ryzen 5 7535HS (6 cores / 12 threads), 14 GB RAM, Radeon RX 6500M 4 GB (Ollama uses Vulkan).
The Q4_K_M file is 18.6 GB, more than RAM + VRAM: Ollama puts about 3 GB on the GPU and
memory-maps the rest, which the page cache keeps in RAM. Only about 3B parameters are active
per token, so this works: measured

| | |
|---|---|
| First load (from NVMe) | about 22 s; the API warms the model up when it starts |
| Prompt reading | about 80 tokens/s (a 2k-token prompt in about 25 s) |
| Reply speed | 10–14 tokens/s |
| Grammar grading (thinking, 1.3–2.4k characters of reasoning) | 36–70 s, in a background job |
| AI Tutor (thinking) | about 45 s |
| AI Monkey: small talk / an explanation (thinking) | about 13 s / 22–37 s |
| Role-play reply | 4–11 s |
| Grammar calibration (20 labelled answers, prompt v6) | MAE 8.15, bias +1.15, 20/20 correct/incorrect agreement (Qwen3-8B Q6_K: 15.7, +4.7, 16/20). The labels are AI-drafted, not yet teacher-verified |

`LLM_TIMEOUT_SECONDS=240` leaves room for the slowest case (a long prompt, a full reasoning
budget, then a non-thinking retry). With more RAM (32 GB) the whole model stays resident and
loads faster; nothing else needs to change.

## Get the model

```bash
scripts/setup_ollama_model.sh                          # ollama pull qwen3:30b-a3b-q4_K_M, then show
OLLAMA_BIN=~/.local/ollama/bin/ollama scripts/setup_ollama_model.sh   # user-local Ollama
scripts/setup_ollama_model.sh --docker                 # the compose `ollama` service
```

`qwen3:30b-a3b-q4_K_M` is the Ollama library tag of the original, hybrid Qwen3-30B-A3B
(Q4_K_M, 18.6 GB). It ships Qwen3's own chat template with the thinking switch (`/think`,
`/no_think`), so no Modelfile or alias is needed.

**Do not use the shorter tags `qwen3:30b-a3b` or `qwen3:30b`.** The Ollama library moved them to
Qwen3-30B-A3B-**Thinking-2507** (GGUF metadata `general.finetune: Thinking`,
`general.version: 2507`): a thinking-only variant whose template always opens `<think>`. With
`think: false` it still reasons, and the reasoning lands in the reply text, so learners would
see it. Its sibling `-instruct-2507` never thinks. Only the hybrid tag above does both, per
request. Check a tag with `ollama show --modelfile <tag>`: the hybrid template contains
`/no_think`.

## Configuration

Everything is configuration; no model name is written in the code.

| `.env` (compose) | API setting | Default | Meaning |
|---|---|---|---|
| `OLLAMA_MODEL` | `BANANA_OLLAMA_MODEL` | `qwen3:30b-a3b-q4_K_M` | The model tag |
| `OLLAMA_URL` | `BANANA_OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama on the host |
| `LLM_CONTEXT_LENGTH` | `BANANA_LLM_CONTEXT_LENGTH` | 8192 | Context window of every request |
| `LLM_TIMEOUT_SECONDS` | `BANANA_LLM_TIMEOUT_SECONDS` | see below | One reply; the web proxy waits 30 s more (rebuild `web` after a change) |
| `LLM_THINKING` | `BANANA_LLM_THINKING` | `true` | `false` = never think |
| `LLM_THINK_BUDGET` | `BANANA_LLM_THINK_BUDGET` | 1024 | Reasoning tokens on top of the answer's own budget |
| `LLM_KEEP_ALIVE` | `BANANA_LLM_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded |
| `LLM_WARM_UP` | `BANANA_LLM_WARM_UP` | `true` | Load the model when the API starts |
| `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS` | | empty | Empty = each task keeps its tuned value |
| `LLM_FALLBACK_MODEL` | | empty | No fallback: the production model never changes silently |

Only an operator with access to the server's `.env` can change these. No API endpoint changes
the model, the prompts or the LLM settings; admins see them read-only on the admin dashboard.

## Thinking and non-thinking

Each request says whether it benefits from reasoning (`LLMRequest.think`):

| Task | Mode | Why |
|---|---|---|
| Grammar assessment (`grammar_assessment`) | thinking | Error analysis: find and quote each mistake, then the verdict |
| AI Tutor "why?" (`tutor_explain`) | thinking | A grounded explanation of the mistake |
| AI Monkey, when the learner asks for an explanation | thinking | Grammar and vocabulary explanations, Vietnamese support |
| AI Monkey small talk | non-thinking | A quick, natural reply |
| Listening answers (`listening_assessment`) | non-thinking | The answers exist; it only judges a paraphrase |
| Role-play partner (`conversation_reply`) | non-thinking | Fast turns in character |
| Question bank (100k questions) | no LLM | Answers are checked by rules; the model never sees the bank |

- Ollama returns the reasoning separately (`message.thinking`). The app logs its size and
  drops it: learners only ever see the final answer.
- A thinking request gets `LLM_THINK_BUDGET` extra tokens. If the reasoning uses them all before
  answering, the provider asks again in non-thinking mode (`llm_think_exhausted` in the log).
- Sampling follows Qwen's recommendation: thinking temperature >= 0.6, top_p 0.95; non-thinking
  top_p 0.8; top_k 20, min_p 0 in both. Each task keeps its own temperature otherwise.

## Context: what the model sees

- The system prompt of the task and only the data that task needs: the exercise and the
  learner's answer; the teacher-written rule for the tutor; the question and the transcript
  for listening; the scenario and the turns so far for role-play.
- AI Monkey: the last 12 turns (1000 characters each at most), not the whole history.
- Never the question bank: bank answers are checked by rules in the database, and database
  answers and teacher-written rules take precedence over the model (they are given to it as
  the ground truth to explain, not something to re-derive).
- Context window 8192 tokens, the same as before; it holds the longest AI Monkey history.

## Caching and logging

- Structured verdicts (grammar, listening, tutor) are cached in Redis by prompt version, model
  and input: the same answer gets the same verdict, instantly (`llm_cache_hit` in the log).
  Conversation replies and AI Monkey chat are never cached: they depend on the conversation.
- Every call logs one line (`llm_call`): task, prompt version, model, latency, input and output
  tokens, tokens/s, load, prompt-eval and generation time, thinking on/off and reasoning size,
  fallback, error. The `llm_calls` table keeps the same audit row. No secrets are logged.

## Host guard (install once per machine)

```bash
sh ollama/systemd/install.sh     # user systemd drop-in for ollama.service, no root needed
```

It wakes the discrete GPU before Ollama starts, refuses to run Ollama without it (systemd
restarts it), keeps one model loaded (`OLLAMA_MAX_LOADED_MODELS=1`) and caps Ollama's page
cache at 9 GiB (`MemoryHigh`). Without it, Ollama sometimes starts while the laptop's GPU is
still powered off, falls back to CPU, and a CPU-only load of this model needs about 18 GiB:
the kernel OOM-killed it once (see [OOM_AUDIT.md](../OOM_AUDIT.md)). Check after a reboot:
`journalctl --user -u ollama -b | grep -E "banana-gpu|inference compute"` must show
`type=discrete`.

## Troubleshooting

- `llm_unavailable ... not found`: the model is not pulled. Run the setup script.
- `did not answer within ...s`: the machine is busy or the model does not fit in memory.
  Check `ollama ps` (the split between GPU and CPU) and `free -h`.
- Model reloads on every request: the context length changed. The API sends
  `LLM_CONTEXT_LENGTH` with every request and when it warms the model up; keep them equal.
- Everything is slow after a restart: the first request loads 18 GB from disk. The API warms
  the model up when it starts (`llm_ready ... load_s=` in `docker compose logs api`).
