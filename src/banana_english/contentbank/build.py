"""Assemble generator output into bank records: stable ids, shuffled options, quality score,
near-duplicate removal and balanced selection (quotas per point x level)."""

from __future__ import annotations

import hashlib
import heapq
import random
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from banana_english.contentbank.lexicon import LEVELS
from banana_english.contentbank.schema import (
    BLANK,
    OptionRecord,
    QuestionRecord,
    SourceRef,
)
from banana_english.domain.models.bank import BankStatus, QuestionType

VALIDATED_AT = 0.6  # quality below this -> draft (kept for audit, never served)
_NORM = re.compile(r"[^a-z0-9_ ]+")


def stable_id(prefix: str, *parts: str, n: int = 12) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:n]
    return f"{prefix}.{digest}"


def near_duplicate_key(text: str) -> str:
    """Lower-case, names and numbers replaced: 'Tom is a teacher.' == 'Mary is a teacher.'"""
    text = re.sub(r"\b[A-Z][a-z]+\b", "X", text)
    text = re.sub(r"\d+", "0", text)
    return _NORM.sub(" ", text.lower()).strip()


def choice_question(
    *,
    qid: str,
    skill: str,
    skill_id: str,
    level: str,
    topic: str,
    point: str,
    difficulty: str,
    qtype: str,
    prompt: str,
    instruction: str,
    right: str,
    wrong: list[str],
    explanation: str,
    explanation_vi: str,
    source: SourceRef,
    quality: float,
    passage_id: str | None = None,
    tags: Iterable[str] = (),
) -> QuestionRecord | None:
    """An MCQ / true-false / error-id record with shuffled options. None if the options clash."""
    texts = [right, *[w for w in wrong if w]]
    if prompt.startswith(BLANK):
        texts = [t[:1].upper() + t[1:] for t in texts]
    seen: set[str] = set()
    unique = []
    for t in texts:
        k = t.strip().lower()
        if k and k not in seen:
            seen.add(k)
            unique.append(t.strip())
    if len(unique) < 2 or unique[0] != texts[0].strip():
        return None
    order = list(range(len(unique)))
    if qtype != QuestionType.TRUE_FALSE.value:
        random.Random(qid).shuffle(order)
    ids = "abcdefgh"
    options = [OptionRecord(id=ids[i], text=unique[j]) for i, j in enumerate(order)]
    answer_id = ids[order.index(0)]
    return QuestionRecord(
        id=qid,
        skill=skill,
        skill_id=skill_id,
        level=level,
        topic=topic,
        point=point,
        difficulty=difficulty,
        qtype=qtype,
        instruction=instruction,
        prompt=prompt,
        options=options,
        answer={"option": answer_id},
        explanation=explanation,
        explanation_vi=explanation_vi,
        passage_id=passage_id,
        tags=list(tags)[:12],
        source=source,
        status=_status(quality),
        quality=round(quality, 3),
    )


def _status(quality: float) -> BankStatus:
    return BankStatus.VALIDATED if quality >= VALIDATED_AT else BankStatus.DRAFT


def status_for(quality: float) -> BankStatus:
    return _status(quality)


@dataclass(order=True)
class _Ranked:
    score: float
    seq: int
    record: QuestionRecord = field(compare=False)


class Selector:
    """Keeps the best `cap` records per bucket in memory (a min-heap), so a pass over millions of
    candidates stays small. Ties are broken at random (seeded) to spread over the corpus."""

    def __init__(self, cap_per_bucket: int, seed: int = 11) -> None:
        self._cap = cap_per_bucket
        self._heaps: dict[tuple, list[_Ranked]] = defaultdict(list)
        self._rng = random.Random(seed)
        self._seq = 0
        self.seen_keys: set[str] = set()
        self.offered = 0
        self.duplicates = 0

    def offer(self, bucket: tuple, dedupe_key: str, record: QuestionRecord) -> None:
        self.offered += 1
        if dedupe_key in self.seen_keys:
            self.duplicates += 1
            return
        self.seen_keys.add(dedupe_key)
        self._seq += 1
        item = _Ranked(record.quality + self._rng.random() * 0.05, self._seq, record)
        heap = self._heaps[bucket]
        if len(heap) < self._cap:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)

    def buckets(self) -> dict[tuple, list[QuestionRecord]]:
        return {b: [r.record for r in sorted(h, reverse=True)] for b, h in self._heaps.items()}


LEVEL_SHARE = {"A1": 18, "A2": 24, "B1": 24, "B2": 19, "C1": 15}
# A point introduced at A1 is practised mostly at A1-A2; a B2 point only at B2-C1.
SHARE_FROM = {
    "A1": {"A1": 30, "A2": 26, "B1": 20, "B2": 14, "C1": 10},
    "A2": {"A2": 30, "B1": 28, "B2": 24, "C1": 18},
    "B1": {"B1": 36, "B2": 34, "C1": 30},
    "B2": {"B2": 50, "C1": 50},
    "C1": {"C1": 100},
}


def allocate(available: dict[str, int], weights: dict[str, int], total: int) -> dict[str, int]:
    """Split `total` by weight, each capped by what is available; what one key cannot fill
    goes to the others (by weight)."""
    quotas = dict.fromkeys(weights, 0)
    open_keys = {k for k in weights if available.get(k, 0) > 0}
    left = total
    while left > 0 and open_keys:
        weight_sum = sum(weights[k] for k in open_keys)
        round_total = left
        for k in sorted(open_keys):
            share = max(1, round(round_total * weights[k] / weight_sum))
            add = min(share, available[k] - quotas[k], left)
            quotas[k] += add
            left -= add
        open_keys = {k for k in open_keys if quotas[k] < available[k]}
    return quotas


def take_balanced(
    buckets: dict[tuple, list[QuestionRecord]],
    quotas: dict[str, int],
    level_share: dict[str, int] = LEVEL_SHARE,
    point_levels: dict[str, str] | None = None,
) -> list[QuestionRecord]:
    """Per point, split its quota over levels (LEVEL_SHARE, capped by availability), and within
    a level interleave the question types (best first)."""
    by_point: dict[str, dict[str, list[list[QuestionRecord]]]] = defaultdict(dict)
    for (point, level, _qtype), records in buckets.items():
        by_point[point].setdefault(level, []).append(list(records))
    chosen: list[QuestionRecord] = []
    for point, quota in quotas.items():
        levels = by_point.get(point, {})
        available = {lvl: sum(len(x) for x in lists) for lvl, lists in levels.items()}
        share = SHARE_FROM[point_levels[point]] if point_levels else level_share
        per_level = allocate(available, share, quota)
        for lvl in LEVELS:
            if lvl in levels:
                chosen.extend(_interleave(levels[lvl])[: per_level.get(lvl, 0)])
    return chosen


def _interleave(lists: list[list[QuestionRecord]]) -> list[QuestionRecord]:
    out: list[QuestionRecord] = []
    while any(lists):
        for lst in lists:
            if lst:
                out.append(lst.pop(0))
    return out
