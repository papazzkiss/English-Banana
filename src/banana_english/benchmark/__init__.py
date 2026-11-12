"""LLM benchmark: compares Ollama models (e.g. Qwen3-8B quantisations) on Banana English's own
prompts, with the same parameters, dataset and scoring for every model.

    python -m banana_english.benchmark --suite quick      # 6 tests x 3 runs per model
    python -m banana_english.benchmark --suite full       # every test x 3 runs per model

It never changes the production model: models are addressed by name per request only.
"""
