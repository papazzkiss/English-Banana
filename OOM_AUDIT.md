# OOM audit: AI Monkey on Qwen3-30B-A3B Q4_K_M

Audit date: 2026-09-30, 09:30–09:45 (+07). Audit only: no code, configuration or process was changed,
restarted or killed. Every number below comes from command output or logs quoted in the
"Evidence" sections; estimates are marked as such.

## Summary

| | |
|---|---|
| Verdict | **An OOM has happened** (kernel OOM killer, 2026-09-30 09:21:57) and **the risk is high right now** |
| What ran out of memory | `llama-server` (Ollama's runner) while loading Qwen3-30B-A3B **on CPU only** |
| Root cause | Ollama sometimes starts before the discrete GPU (RX 6500M) has woken from runtime power-off, does not see it, and falls back to CPU. A CPU-only load disables mmap and needs about 18.3 GiB of anonymous memory on a 14.3 GiB machine |
| Trigger | The API's model warm-up when the containers start at boot, or the first AI request after that |
| State at audit time | This boot's Ollama was again in CPU-only mode (`total_vram="0 B"`): the next AI Monkey request would have repeated the OOM |
| State after the fixes | **Fixed** (see "Applied fixes"): Ollama waits for the GPU and refuses to run without it; the model runs in GPU mode; one model at a time; Ollama's cache capped at 9 GiB |
| Normal mode (GPU found) | No OOM in 8 h 44 min of use last night (peak 10.8 GiB for the Ollama service incl. page cache, swap peak 786 MiB). Memory per request is constant: 1 slot, fixed 8192-token KV cache |
| Banana English code | No leak, no repeated model loading, no unbounded history found. It is not the cause |

## Current configuration

| Item | Value | Source |
|---|---|---|
| Model tag | `qwen3:30b-a3b-q4_K_M` (general.name "Qwen3 30B A3B", hybrid thinking) | `.env`, `ollama show`, load log |
| Architecture | qwen3moe, 30.5B parameters, 48 blocks, 128 experts, 8 active, 32 heads, 4 KV heads, head dim 128 | `ollama show --verbose` |
| Quantization / file | Q4_K_M, 18.6 GB (blob `e9183b5c18a0…`) | `ollama show`, registry |
| Context sent by the app | `num_ctx` 8192 (`LLM_CONTEXT_LENGTH=8192`), model maximum 40960 | `.env`, `n_ctx_slot = 8192` in log |
| KV cache | f16 (`OLLAMA_KV_CACHE_TYPE` empty, `OLLAMA_FLASH_ATTENTION:false`), 768 MiB for 8192 tokens | llama.cpp memory breakdown |
| Parallel slots | 1 (`OLLAMA_NUM_PARALLEL:1`, `n_slots = 1`) | server config, load log |
| Max loaded models | 0 = Ollama's automatic limit (can hold more than one model) | server config |
| Queue | `OLLAMA_MAX_QUEUE:512` | server config |
| Keep-alive | app sends 30m (`LLM_KEEP_ALIVE`), server default 5m | `.env`, server config |
| Thinking | on for explanations, budget 1024 tokens (`LLM_THINK_BUDGET`) | `.env` |
| Offload in GPU mode | all 49 layers' dense weights + KV on the GPU (2960 MiB), MoE experts (15.4 GiB) in system RAM via mmap | load log 2026-09-30 01:36 and 09:24 |
| Offload in CPU mode | everything in RAM, **mmap disabled** | load log 09:21:07 |
| Ollama | 0.34.4, on the host (user systemd unit), `OLLAMA_HOST=0.0.0.0:11434` | `ollama --version`, unit file |
| API → Ollama | `http://host.docker.internal:11434`, one `httpx.Client` per process, `stream: false`, timeout 240 s | docker-compose.yml, code |

## Hardware resources

| Resource | Total | Free at audit time (model not loaded) |
|---|---|---|
| CPU | Ryzen 5 7535HS, 6 cores / 12 threads | idle (load 0.6) |
| RAM | 14.3 GiB (14670 MiB) | 8.6 GiB available (3.9 GiB free + reclaimable cache) |
| Swap | 4.0 GiB file (`/swap.img`), swappiness 60 | 4.0 GiB (unused after the reboot) |
| Discrete GPU | Radeon RX 6500M (Navi 24), 4.0 GiB VRAM, Vulkan, runtime power control `auto` (BOCO) | runtime status **suspended**; 16 MB VRAM used |
| Integrated GPU | Radeon 660M | ignored by Ollama ("dropping integrated GPU") |
| Disk | NVMe, 335 GB free | |

RAM already used before any model (by process, `ps` RSS):

| Consumer | RSS |
|---|---|
| VS Code | 3.4 GiB |
| Firefox (all processes) | about 1.7 GiB |
| qdrant (the other project `codebase-rag-assistant`) | 0.66 GiB |
| uvicorn processes (Banana API + the other project's API) | 0.66 GiB |
| gnome-shell, Xwayland, other desktop | about 0.6 GiB |
| Banana English containers (docker stats) | api 280 MiB, web 110 MiB, db 49 MiB, redis 14 MiB, funnel 82 MiB, tunnel 35 MiB |
| Ollama server (no model) | 73 MiB |

So about **6 GiB** is used before the model; the model has at most about 8.5 GiB of RAM and 4 GiB of VRAM.

## Actual runtime usage

- `ollama ps` at audit time: **empty**. The model is not loaded: the API's warm-up at boot
  (09:28:27) found Ollama not yet listening (`Connection refused`), and nothing has used the AI
  since.
- Last working session (previous night, GPU mode, 8 h 44 min): Ollama service
  `10.8G memory peak, 785.9M memory swap peak` (systemd accounting; this includes the page cache
  of the memory-mapped expert weights). No OOM.
- Loaded model in GPU mode (from `ollama ps` in the previous session): 19.6 GB model size,
  3.1 GB of it on the GPU, context 8192.
- Largest prompt seen by the slot last night: 2042 tokens (a deliberate speed test); ordinary
  AI Monkey prompts were 200–700 tokens.
- Live memory under load (single chat, consecutive, concurrent) was **not re-measured** in this
  audit on purpose: this boot's Ollama is in CPU-only mode, and any request would load the model
  on CPU and trigger the OOM again (see below).

## OOM evidence

1. **Kernel OOM kill, 2026-09-30 09:21:57** (`journalctl -b -1 -k`):
   ```
   gly-global-exec invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP) ...
   Free swap  = 84kB
   Total swap = 4194300kB
   oom-kill:constraint=CONSTRAINT_NONE,...,global_oom,task_memcg=/user.slice/.../ollama.service,task=llama-ser
   Out of memory: Killed process 16468 (llama-server) total-vm:19162616kB, anon-rss:10699472kB ...
   ```
   systemd: `ollama.service: Failed with result 'oom-kill'` … `10.2G memory peak, 3.1G memory swap peak`.
2. **The load that was killed was CPU-only, without mmap** (Ollama log, 09:19:40–09:21:07):
   ```
   dropping integrated GPU ... AMD Radeon 660M
   "inference compute" id=cpu library=cpu ... total="14.3 GiB" available="12.1 GiB"
   "vram-based default context" total_vram="0 B"
   "disabling mmap for llama-server load by default" model=.../sha256-e9183b5c18a0...
   memory breakdown [MiB]  Host 5295 = 4335 model + 768 context + 192 compute
                           CPU_REPACK 13419 = 13419 model
   projected to use 5295 MiB of host memory vs. 14670 MiB ... no changes needed
   ```
   The fit check counted 5295 MiB and missed the 13419 MiB `CPU_REPACK` buffer: about
   18.3 GiB was really needed.
3. **Who asked for the load**: the API container starting at boot (restart policy
   `unless-stopped`) warms the model up; at 02:21:57Z the API logged
   `llm_unavailable model=qwen3:30b-a3b-q4_K_M ... Server disconnected`, the moment of the kill.
4. **Why the GPU was missing**: at the same second the kernel was still waking the GPU:
   `09:19:40 amdgpu 0000:03:00.0: PSP is resuming...` (`Using BOCO for runtime pm`). Ollama's
   second start at 09:22:05 found it: `"inference compute" ... name=Vulkan1 description="AMD
   Radeon RX 6500M" ... total="4.0 GiB"`. This boot (09:28:35) missed it again:
   `inference compute id=cpu ... total_vram="0 B"`; `/sys/bus/pci/devices/0000:03:00.0/power/runtime_status` = `suspended`.
5. **Hard freeze after the second load (unconfirmed cause)**: at 09:24:32 a load started in GPU
   mode with mmap (`load_mode = mmap`, 49 layers, 2960 MiB VRAM); the journal of that boot ends
   at 09:24:44 with no shutdown, and the machine was started again at 09:28:11. No OOM line was
   written. Before this load Ollama logged `free="9.6 GiB" free_swap="3.1 GiB"` (about 0.9 GiB
   still in swap after the OOM). Cause **not proven** (see "Missing data").
6. Other checks, all clean: containers `OOMKilled=false`, `RestartCount=0`, exit 0; no
   `out of memory`, `CUDA`, `exit 137`, `allocation failed`, `MemoryError` or `Killed` in the API
   or web logs for 24 h; no kernel OOM in the three previous boots.

## Root cause

**Primary (proven):** a race at boot between the discrete GPU waking from runtime power-off
(BOCO) and Ollama's GPU discovery. When Ollama misses the GPU it runs CPU-only for its whole
lifetime, and a CPU-only load of this model:

- disables mmap ("disabling mmap for llama-server load by default"), so the weights become
  anonymous memory instead of reclaimable page cache;
- repacks the CPU weights (`CPU_REPACK` 13419 MiB) on top of the 5295 MiB host buffers;
- needs about 18.3 GiB on a machine with 14.3 GiB RAM, 6 GiB of it already used by desktop
  apps, and 4 GiB swap. The kernel killed it at 10.7 GB resident with swap exhausted.

Ollama's own memory check did not prevent it: it projected 5295 MiB and missed the repack buffer.

**Trigger (proven):** the API warms the model up as soon as its container starts, which at boot
is exactly when the GPU may not be discovered yet. Any first AI request does the same.

**Contributing (measured):** about 6 GiB of RAM is held by software unrelated to Banana English
(VS Code, Firefox, the other project's qdrant/API), which leaves little room even in GPU mode.

**Not a cause (checked in code):**

| Question | Finding |
|---|---|
| Model loaded several times? | No. One Ollama model; the app never asks for another (`LLM_FALLBACK_MODEL` empty); warm-up once per API start |
| Ollama client created several times? | No. One `OllamaProvider` / `httpx.Client` built once in `build_container`; one uvicorn worker (Dockerfile `CMD`, no `--workers`) |
| Concurrent requests growing memory? | No. `OLLAMA_NUM_PARALLEL=1`: one slot, one fixed KV cache; extra requests wait in Ollama's queue. API side: FastAPI thread pool + 2 job workers, each waiting request holds only its small request objects |
| Conversation kept too large? | No. The server is stateless for AI Monkey; the browser sends at most 60 messages of 1000 characters, and only the last 12 turns (`MAX_HISTORY=12`, sliding by 6) reach the model |
| Whole chat history sent every time? | No, at most 12 turns. Worst case measured with Qwen3's tokenizer: 12 Vietnamese turns at the character limits = 3706 prompt tokens; plus a 400-token answer and a 1024-token thinking budget = 5130 of 8192 |
| Redundant prompt/context? | No. System prompt 264 tokens; one short settings line per turn when needed |
| Streaming buffers not released? | No streaming on the API side (`stream: false`); each reply is read once and dropped |
| Memory leak? | None found: Whisper and Piper are lazy singletons behind a lock; no per-request caches in memory (verdict cache is Redis) |
| Concurrency/queue settings | Memory-safe; the limit is time, not memory (see "Safe configuration") |

## Risk level

| Scenario | GPU found (normal) | GPU missed (this boot) |
|---|---|---|
| 1 user chat | **Low**. Measured last night: no OOM, 13–37 s per reply | **OOM on the first request** (the model loads on CPU) |
| Many consecutive requests | **Low**. Same slot and KV; `keep_alive` 30m avoids reloads | OOM on the first one |
| Long request (long prompt) | **Low**. KV is allocated for 8192 tokens at load; a longer prompt does not add memory | OOM on load |
| Long conversation | **Low**. Capped at 12 turns (≤ 5130 tokens incl. thinking) | OOM on load |
| Several users at once | **Low for memory** (1 slot, queued). **Medium for timeouts**: with thinking, 3–4 queued explanations can exceed the 240 s timeout | OOM on load |
| A second model loaded (e.g. `ollama run qwen3:8b`, the benchmark profile) | **High**: `OLLAMA_MAX_LOADED_MODELS` is automatic, so Ollama may keep both; +6.7 GB would not fit | High |
| Reboot / Ollama restart | **High** until the discovery race is fixed: each start has a chance to miss the GPU | — |

Overall: **OOM has occurred; high risk now** (this boot is in CPU-only mode); **low risk in
normal GPU mode** for every AI Monkey usage pattern, as long as only one model is loaded.

## Memory breakdown (Qwen3-30B-A3B Q4_K_M, context 8192, 1 slot)

From llama.cpp's own memory breakdown in the Ollama logs:

**GPU mode (what production expects):**

| Part | Where | MiB |
|---|---|---|
| Dense weights (attention, norms, embeddings, router) of all 49 layers | VRAM | 1966 |
| KV cache, f16, 8192 tokens (48 layers × 4 KV heads × 128 × 2 × 2 bytes = 96 KiB/token) | VRAM | 768 |
| Compute buffer | VRAM | 225 |
| **VRAM total** | of 4064 free | **2960** (1104 free) |
| MoE expert weights | system RAM, memory-mapped file (page cache, reclaimable) | 15787 |
| Host compute buffer | RAM | 16 |

With about 8.5 GiB of RAM free, roughly half of the 15.4 GiB of experts stays in the page cache;
the rest is read from NVMe when a token needs it. Under pressure the kernel drops those pages
instead of killing anything, which is why GPU mode degrades speed rather than crashing.

**CPU-only mode (what caused the OOM):**

| Part | MiB |
|---|---|
| Host model buffer | 4335 |
| KV cache | 768 |
| Compute | 192 |
| CPU_REPACK (repacked weights, anonymous) | 13419 |
| **Total** | **18714 (18.3 GiB) of anonymous memory, not reclaimable** |

Available: 14.3 GiB RAM − about 6 GiB in use + 4 GiB swap ≈ 12 GiB. It cannot fit.

**Rest of the machine:** desktop and other apps about 6 GiB; Banana English containers about
0.6 GiB (the API grows by a few hundred MiB when Whisper and Piper are first used).

## Safe configuration

Thresholds for this machine (14.3 GiB RAM, 4 GiB VRAM), keeping the current model:

| Setting | Safe value | Why |
|---|---|---|
| GPU | Must be discovered (`inference compute ... RX 6500M` in the Ollama log) before the model loads | A CPU-only load needs 18.3 GiB |
| `num_ctx` (`LLM_CONTEXT_LENGTH`) | **8192** (current); 6144 would also fit AI Monkey's worst case (5130) and free 192 MiB VRAM | KV = 96 KiB/token: 16384 would take 1.5 GiB and exceed the 1.1 GiB of VRAM headroom |
| `OLLAMA_NUM_PARALLEL` | **1** (current) | Each extra slot adds another 768 MiB KV cache |
| `OLLAMA_MAX_LOADED_MODELS` | **1** (currently automatic) | A second model does not fit |
| Concurrent AI requests | Memory: unlimited (they queue). Latency: about 3 queued thinking requests fit in the 240 s timeout | Measured 22–70 s per thinking request |
| Free RAM before loading | at least 8 GiB available and swap mostly free | Leaves the page cache room for the experts |
| Swap | 4 GiB is a thin safety net; 8 GiB (or zram) would give more room | Swap was exhausted in the OOM |

## Recommended fixes

Not applied: this audit changed nothing. In order of importance:

1. **Right now:** before anyone uses the AI, restart Ollama once while the GPU is awake, then
   check the log for `inference compute ... "AMD Radeon RX 6500M"`:
   `systemctl --user restart ollama && journalctl --user -u ollama -n 20 | grep "inference compute"`.
   Until then, do not send AI requests (they would trigger the OOM).
2. **Fix the discovery race (host configuration, not code):** keep the dGPU powered while
   Ollama runs, e.g. a udev rule setting `power/control=on` for `0000:03:00.0`, or an
   `ExecStartPre=` in the Ollama user unit that wakes the GPU (for example `vulkaninfo --summary`)
   and waits until it is active. Then verify discovery on the next reboots.
3. **Never load this model on CPU only:** if Ollama reports `total_vram="0 B"`, refuse or delay
   the load (for example a check in the API's warm-up, or an `ExecStartPost=` health check that
   restarts Ollama when it comes up without the GPU). A CPU-only load of this model cannot fit.
4. **`OLLAMA_MAX_LOADED_MODELS=1`** in the Ollama unit, so a second model (the 8B ones are still
   installed, and the benchmark profile uses them) replaces instead of adding.
5. **Warm-up at boot:** delay the API's warm-up until Ollama reports the GPU (or turn
   `LLM_WARM_UP` off and let the first request load it once the machine is settled).
6. **Free RAM on the production machine:** VS Code (3.4 GiB), Firefox (1.7 GiB) and the other
   project's containers (qdrant 0.66 GiB) compete with the model's page cache.
7. **Optional:** larger swap (8 GiB) or zram as a safety net; `OLLAMA_FLASH_ATTENTION=1` with
   `OLLAMA_KV_CACHE_TYPE=q8_0` would halve the KV cache (768 → 384 MiB) if the Vulkan backend
   supports flash attention (not verified); `num_ctx` 6144 would save 192 MiB VRAM.
8. **Monitoring:** alert on `inference compute id=cpu` and on `Failed with result 'oom-kill'` in
   the Ollama journal.

## Applied fixes (2026-09-30, after the audit)

Host configuration only; no application code changed. Sources in `ollama/systemd/`, installed
with `sh ollama/systemd/install.sh` into the user unit (no root needed):

| Fix | What it does | Verified |
|---|---|---|
| `ExecStartPre=banana-ollama-gpu-wake.sh` | Opens the RX 6500M's render node, which resumes it at once, and waits until `runtime_status` is `active` before Ollama starts | 4 restarts, 3 of them with the GPU suspended: Ollama found `type=discrete` every time |
| `ExecStartPost=banana-ollama-gpu-check.sh` | Reads the new Ollama process's own log; without `type=discrete` it fails, so systemd stops Ollama before any model loads and starts it again (`Restart=on-failure`) | Passes on the real process, fails when no GPU line is found |
| `OLLAMA_MAX_LOADED_MODELS=1` | Never two models in memory | `server config` shows `OLLAMA_MAX_LOADED_MODELS:1` |
| `MemoryHigh=9G` on `ollama.service` | Soft cap. In GPU mode Ollama's memory is page cache of the mapped experts (anon 22 MiB, file 8 GiB measured); above the cap the kernel drops that cache instead of swapping the desktop out. Never kills Ollama | Thinking speed: 7G 6.5–7.6 tok/s, 8G 8.4–8.8, **9G 10.5–10.7** (same as uncapped) |

After the fix: the model loads in GPU mode in 21–27 s (`84%/16% CPU/GPU`, 2976 MiB VRAM, context
8192). Through the app: AI Monkey small talk 22 s, a Vietnamese explanation 35 s, a 15-message
conversation at the size limits 94 s; the question bank and RBAC unchanged; no OOM or allocation
error in the logs.

**Swap:** the first uncapped load pushed about 3 GiB of idle desktop memory (Firefox 1.45 GiB,
VS Code 1.38 GiB, containers 0.5 GiB) into swap, and it stays there until those apps touch it.
That is not an OOM risk: in GPU mode the memory that cannot be reclaimed is about 6 GiB (desktop +
containers + Ollama's 22 MiB), while RAM + swap is 18 GiB and most of Ollama's share is
reclaimable cache (MemAvailable 8.5–10.7 GiB during the tests). It only makes those apps slower
to come back.

**Still recommended (needs root, not done):** `vm.swappiness=10` (the kernel then drops the
model's file cache before swapping idle apps), a larger swap (8 GiB) or zram, and a udev rule
`power/control=on` for the dGPU as a second layer. Also: delay the API warm-up until Ollama is
ready (code change, not done), and keep heavy apps off the production machine.

## Missing data

- **Live memory under load in this boot** (single chat, bursts, concurrency): not measured,
  on purpose. Ollama is in CPU-only mode and the first request would repeat the OOM. The figures
  for GPU mode come from last night's logs and the loader's breakdown, not from a new run.
- **Cause of the hard freeze at 09:24:44:** the journal of that boot ends without any error.
  Possible explanations (memory thrashing right after the OOM, or a GPU driver hang during the
  load) cannot be told apart from the available logs.
- **Who requested the 09:24:32 load:** not the API warm-up (that ran at 09:21 and 09:28);
  probably a user request or a manual `ollama run`, but it was not logged before the freeze.
- **Anonymous RSS of `llama-server` in GPU mode:** only the service's cgroup peak (10.8 GiB incl.
  page cache) is recorded; the split between anonymous memory and page cache was not captured.
- **Whether a CPU-only load with mmap forced on would fit:** not tested (it would risk another OOM).

## Evidence commands

`ollama --version`, `ollama ps`, `ollama show --verbose qwen3:30b-a3b-q4_K_M`;
`journalctl --user -u ollama` (current and previous boots); `journalctl -b -1 -k`;
`journalctl --list-boots`; `free -m`, `swapon --show`, `/proc/meminfo`, `ps` by RSS;
`/sys/bus/pci/devices/0000:03:00.0/power/{runtime_status,control}`,
`/sys/class/drm/card*/device/mem_info_vram_used`; `docker stats`, `docker inspect`
(OOMKilled, RestartCount, Memory, ShmSize); `docker compose logs api|web`; code:
`application/services/monkey.py`, `infrastructure/ai/ollama_provider.py`, `config/container.py`,
`api/schemas/modules.py`, `Dockerfile`; Qwen3 tokenizer (`tokenizer.json`) for the prompt sizes.
