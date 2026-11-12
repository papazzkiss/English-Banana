"""Timed Ollama client for the benchmark.

The request body comes from production (`chat_body`); the benchmark only turns streaming on and
adds the fixed options every model shares (context size, seed). TTFT is measured on the client
from sending the request to the first streamed content token; token counts and decode time come
from Ollama's final chunk.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from banana_english.domain.interfaces.llm import LLMRequest
from banana_english.infrastructure.ai.ollama_provider import chat_body


@dataclass(frozen=True)
class Generation:
    text: str
    ttft_s: float | None  # None if the model produced no content
    total_s: float
    output_tokens: int | None
    input_tokens: int | None
    eval_s: float | None  # decode time reported by Ollama
    prompt_eval_s: float | None
    load_s: float | None
    error: str | None = None

    @property
    def tokens_per_s(self) -> float | None:
        if self.output_tokens and self.eval_s:
            return self.output_tokens / self.eval_s
        return None


@dataclass(frozen=True)
class LoadedModel:
    name: str
    size_bytes: int
    vram_bytes: int


class OllamaBenchClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 600.0,
        keep_alive: str = "30m",
        transport: httpx.BaseTransport | None = None,  # tests pass a fake Ollama
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport
        )
        self.keep_alive = keep_alive

    # --- models ---------------------------------------------------------------------
    def version(self) -> str:
        return self._http.get("/api/version").json().get("version", "?")

    def installed(self) -> set[str]:
        return set(self.sizes())

    def sizes(self) -> dict[str, int]:
        """Installed model name -> size on disk in bytes."""
        models = self._http.get("/api/tags").json().get("models", [])
        return {m["name"]: m.get("size", 0) for m in models}

    def show(self, model: str) -> dict:
        r = self._http.post("/api/show", json={"model": model})
        r.raise_for_status()
        return r.json()

    def pull(self, model: str, log=print) -> bool:
        """Pull a model. Returns False (never raises) if the registry does not have it."""
        with self._http.stream("POST", "/api/pull", json={"model": model}, timeout=None) as r:
            last = ""
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if "error" in msg:
                    log(f"  pull {model}: {msg['error']}")
                    return False
                status = msg.get("status", "")
                if status != last and not status.startswith("pulling "):
                    log(f"  pull {model}: {status}")
                    last = status
        return model in self.installed() or f"{model}:latest" in self.installed()

    def parameters(self, model: str) -> dict:
        """A model's default parameters (the Modelfile PARAMETER lines) as a dict."""
        params: dict = {}
        for line in (self.show(model).get("parameters") or "").splitlines():
            key, _, raw = line.strip().partition(" ")
            raw = raw.strip()
            value = json.loads(raw) if raw.startswith('"') else float(raw)
            if key == "stop":
                params.setdefault("stop", []).append(value)
            else:
                params[key] = (
                    int(value) if isinstance(value, float) and value.is_integer() else value
                )
        return params

    def create_alias(self, name: str, source: str, template: str, parameters: dict) -> None:
        """A new local name for `source`'s weights with another template and parameters (no
        download, no copy of the weights)."""
        r = self._http.post(
            "/api/create",
            json={
                "model": name,
                "from": source,
                "template": template,
                "parameters": parameters,
                "stream": False,
            },
            timeout=None,
        )
        r.raise_for_status()

    def loaded(self) -> list[LoadedModel]:
        models = self._http.get("/api/ps").json().get("models", [])
        return [LoadedModel(m["name"], m.get("size", 0), m.get("size_vram", 0)) for m in models]

    def unload(self, model: str) -> None:
        self._http.post("/api/generate", json={"model": model, "keep_alive": 0})

    def unload_all(self) -> list[str]:
        names = [m.name for m in self.loaded()]
        for name in names:
            self.unload(name)
        return names

    # --- generation -----------------------------------------------------------------
    def generate(self, model: str, request: LLMRequest, options: dict) -> Generation:
        body = chat_body(model, request, self.keep_alive)
        body["stream"] = True
        body["options"] = {**body["options"], **options}
        parts: list[str] = []
        ttft: float | None = None
        final: dict = {}
        started = time.perf_counter()
        try:
            with self._http.stream("POST", "/api/chat", json=body) as r:
                if r.status_code != 200:
                    r.read()
                    raise httpx.HTTPStatusError(
                        f"{r.status_code}: {r.text[:200]}", request=r.request, response=r
                    )
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise RuntimeError(chunk["error"])
                    piece = (chunk.get("message") or {}).get("content") or ""
                    if piece:
                        if ttft is None:
                            ttft = time.perf_counter() - started
                        parts.append(piece)
                    if chunk.get("done"):
                        final = chunk
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            return Generation(
                "".join(parts),
                ttft,
                time.perf_counter() - started,
                None,
                None,
                None,
                None,
                None,
                error=str(exc)[:300],
            )
        total = time.perf_counter() - started
        ns = 1e9
        return Generation(
            text="".join(parts),
            ttft_s=ttft,
            total_s=total,
            output_tokens=final.get("eval_count"),
            input_tokens=final.get("prompt_eval_count"),
            eval_s=final["eval_duration"] / ns if final.get("eval_duration") else None,
            prompt_eval_s=final["prompt_eval_duration"] / ns
            if final.get("prompt_eval_duration")
            else None,
            load_s=final["load_duration"] / ns if final.get("load_duration") else None,
        )
