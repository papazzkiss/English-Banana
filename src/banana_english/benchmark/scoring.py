"""Unified rubric and scores.

Every test lists checks; each check belongs to one rubric dimension and has a weight. A check
is a deterministic, reproducible test of the reply (valid contract, right verdict, correction
matches a reviewed answer, required concept mentioned, length/format limits, stays in role...).

  dimension score  = weighted share of passed checks of that dimension, over all tests and runs
  quality          = mean of the dimension scores (0-100, every dimension counts the same)
  performance      = 50% speed (fastest P50 / this P50) + 50% throughput (tok/s / fastest tok/s)
  overall          = 90% quality + 10% performance
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from banana_english.benchmark.tasks import Parsed
from banana_english.domain.services.answer_matching import matches_any

DIMENSIONS = (
    "grammar",
    "explanation",
    "naturalness",
    "instruction_following",
    "relevance",
    "vocabulary",
    "conversation",
)
QUALITY_WEIGHT = 0.9
PERFORMANCE_WEIGHT = 0.1

_TIP = re.compile(r"\(\s*tip:[^)]*\)", re.I)
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿]")
_MARKDOWN = re.compile(r"(^|\n)\s*(#{1,6}\s|[-*•]\s|\d+\.\s)|\*\*|__|`", re.M)
_REASONING = re.compile(
    r"^\s*(<think>|okay,? (so|let me|the user)|let me (think|see)|hmm\b|we are (asked|to)|"
    r"the user (asked|wants|is))",
    re.I,
)
_WORD = re.compile(r"[A-Za-z']+")
_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|(?<!\w)'[^']*'(?!\w)")


@dataclass(frozen=True)
class CheckResult:
    type: str
    dimension: str
    weight: float
    passed: bool
    detail: str = ""


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if _WORD.search(p)]


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def _field(parsed: Parsed, name: str) -> str:
    if name == "text":
        return parsed.text
    if name == "raw":
        return parsed.raw
    if name == "spoken":  # what the voice would read: the reply without its "(Tip: ...)"
        return _TIP.sub("", parsed.text).strip()
    value = parsed.fields.get(name, "")
    return value if isinstance(value, str) else str(value)


def _has(text: str, term: str) -> bool:
    if term.startswith("re:"):
        return re.search(term[3:], text, re.I) is not None
    return term.lower() in text.lower()


def run_check(check: dict, parsed: Parsed) -> CheckResult:
    """Evaluate one check. A reply that broke its contract fails every check that needs a
    parsed field (the app could not have used it)."""
    kind = check["type"]
    dim = check["dim"]
    weight = float(check.get("weight", 1))

    def result(ok: bool, detail: str = "") -> CheckResult:
        return CheckResult(kind, dim, weight, bool(ok), detail)

    if kind == "contract":
        return result(parsed.contract_ok, parsed.contract_error or "")
    needs_fields = kind in ("verdict", "correction") or check.get("field") not in (
        None,
        "text",
        "raw",
        "spoken",
    )
    if needs_fields and not parsed.contract_ok:
        return result(False, "reply unusable (contract failed)")

    text = _field(parsed, check.get("field", "text"))
    if kind == "verdict":
        got = parsed.fields.get("is_correct")
        return result(got == check["expected"], f"is_correct={got}")
    if kind == "correction":
        corrected = parsed.fields.get("corrected_answer") or ""
        refs = check.get("references") or parsed.fields.get("references") or []
        return result(bool(corrected) and matches_any(corrected, refs), corrected[:80])
    if kind == "contains_any":
        return result(any(_has(text, t) for t in check["terms"]))
    if kind == "contains_all":  # every group needs at least one of its terms
        missing = [g for g in check["groups"] if not any(_has(text, t) for t in g)]
        return result(not missing, f"missing {missing}" if missing else "")
    if kind == "not_contains":
        found = [t for t in check["terms"] if _has(text, t)]
        return result(not found, f"found {found}" if found else "")
    if kind == "regex":
        return result(re.search(check["pattern"], text, re.I) is not None)
    if kind == "max_sentences":
        n = len(sentences(text))
        return result(0 < n <= check["max"], f"{n} sentences")
    if kind == "min_sentences":
        n = len(sentences(text))
        return result(n >= check["min"], f"{n} sentences")
    if kind == "max_words":
        n = len(words(text))
        return result(0 < n <= check["max"], f"{n} words")
    if kind == "has_question":
        return result("?" in text)
    if kind == "plain_speech":  # a voice reply: no emoji, markdown, lists or labels
        bad = _EMOJI.search(parsed.raw) or _MARKDOWN.search(parsed.raw)
        return result(not bad, bad.group(0) if bad else "")
    if kind == "no_reasoning_leak":
        return result(not _REASONING.search(parsed.raw) and "</think>" not in parsed.raw)
    if kind == "simple_words":  # readability: mean word length of the model's own words
        ws = words(_QUOTED.sub(" ", text))  # quoted phrases are the exercise's words
        mean = sum(map(len, ws)) / len(ws) if ws else 0.0
        return result(bool(ws) and mean <= check.get("max_mean_len", 6.0), f"mean {mean:.1f}")
    if kind == "not_repetitive":  # quoted phrases (the words being explained) do not count
        ws = [w.lower() for w in words(_QUOTED.sub(" ", text))]
        trigrams = list(zip(ws, ws[1:], ws[2:], strict=False))
        # degenerate loops score well below 0.5; parallel phrasing in normal prose stays > 0.8
        ok = not trigrams or len(set(trigrams)) / len(trigrams) >= 0.75
        return result(ok)
    if kind == "differs_from":
        return result(check["text"].lower().strip(" .") not in text.lower())
    raise ValueError(f"unknown check type: {kind}")


# --- aggregation ---------------------------------------------------------------------------


def dimension_scores(results: Iterable[CheckResult]) -> dict[str, float | None]:
    total = dict.fromkeys(DIMENSIONS, 0.0)
    passed = dict.fromkeys(DIMENSIONS, 0.0)
    for r in results:
        total[r.dimension] += r.weight
        passed[r.dimension] += r.weight if r.passed else 0.0
    return {d: (100 * passed[d] / total[d] if total[d] else None) for d in DIMENSIONS}


def quality_score(dims: dict[str, float | None]) -> float:
    values = [v for v in dims.values() if v is not None]
    return sum(values) / len(values) if values else 0.0


def weighted_pass(results: Sequence[CheckResult]) -> float:
    total = sum(r.weight for r in results)
    return 100 * sum(r.weight for r in results if r.passed) / total if total else 0.0


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile (the same method as numpy's default)."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def performance_scores(models: dict[str, tuple[float | None, float | None]]) -> dict[str, float]:
    """models: name -> (p50 latency s, tokens/s). Relative to the best model in the run."""
    p50s = [p for p, _ in models.values() if p]
    tpss = [t for _, t in models.values() if t]
    best_p50 = min(p50s) if p50s else None
    best_tps = max(tpss) if tpss else None
    scores = {}
    for name, (p50, tps) in models.items():
        speed = 100 * best_p50 / p50 if p50 and best_p50 else 0.0
        rate = 100 * tps / best_tps if tps and best_tps else 0.0
        scores[name] = 0.5 * speed + 0.5 * rate
    return scores


def overall_score(quality: float, performance: float) -> float:
    return QUALITY_WEIGHT * quality + PERFORMANCE_WEIGHT * performance


def paired_difference(a: dict[str, float], b: dict[str, float]) -> tuple[float, float, int]:
    """Mean per-test score difference a - b over the tests both have, with the half-width of
    its 95% confidence interval (normal approximation of the paired mean)."""
    common = sorted(set(a) & set(b))
    diffs = [a[t] - b[t] for t in common]
    n = len(diffs)
    if n < 2:
        return (diffs[0] if diffs else 0.0), math.inf, n
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    return mean, 1.96 * math.sqrt(var / n), n
