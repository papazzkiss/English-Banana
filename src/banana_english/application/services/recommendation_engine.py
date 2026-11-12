"""Rule-based recommendation (Phase 5) — the baseline any future ML recommender must beat.

1. Weak skills first: up to 3 skills with effective mastery < 60, weakest first.
   Material difficulty: easy if mastery < 40, otherwise medium. Material at or below the
   learner's level first (above it only when nothing else is left), then unseen items, then
   items answered wrongly (oldest first); never the item attempted last (anti-gaming).
2. Due SM-2 vocabulary cards.
3. Default mix to fill up to n (and the whole list for a new learner — cold start):
   new topics the learner has not started (at or below their level, one per module),
   then "keep fresh" practice for the least recently practised non-weak skills
   (hard items above 80).
Deterministic: the same context always yields the same list.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from banana_english.domain.interfaces.recommendation import (
    ItemHistory,
    RecommendationContext,
    RecommendationEngine,
)
from banana_english.domain.interfaces.repositories import ContentRepository
from banana_english.domain.models import (
    ActivityItem,
    Difficulty,
    Module,
    Recommendation,
    RecommendationKind,
    Skill,
    SkillMastery,
)
from banana_english.domain.services.mastery import (
    EASY_BELOW,
    WEAKNESS_THRESHOLD,
    effective_mastery,
)
from banana_english.domain.services.weakness import find_weak_skills

MODULE_ORDER = [
    Module.VOCABULARY,
    Module.GRAMMAR,
    Module.LISTENING,
    Module.SPEAKING,
    Module.CONVERSATION,
]
HARD_ABOVE = 80.0
_DIFF_RANK = {Difficulty.EASY: 0, Difficulty.MEDIUM: 1, Difficulty.HARD: 2}
_REASON_CODE = {
    RecommendationKind.REINFORCEMENT: "weak_skill",
    RecommendationKind.NEW_TOPIC: "new_topic",
    RecommendationKind.PRACTICE: "keep_practising",
}


def target_difficulty(mastery: float) -> Difficulty:
    if mastery < EASY_BELOW:
        return Difficulty.EASY
    if mastery <= HARD_ABOVE:
        return Difficulty.MEDIUM
    return Difficulty.HARD


class RuleBasedRecommendationEngine(RecommendationEngine):
    def __init__(
        self,
        content: ContentRepository,
        *,
        grammar_batch: int = 2,
        vocabulary_batch: int = 8,
        weak_limit: int = 3,
    ) -> None:
        self._content = content
        self._grammar_batch = grammar_batch
        self._vocabulary_batch = vocabulary_batch
        self._weak_limit = weak_limit

    def next_exercises(self, context: RecommendationContext, n: int = 5) -> list[Recommendation]:
        recs: list[Recommendation] = []
        used: set[str] = set()

        def add(rec: Recommendation | None) -> None:
            if rec and rec.items and rec.skill_id not in used and len(recs) < n:
                used.add(rec.skill_id)
                recs.append(_with_priority(rec, len(recs) + 1))

        for weak in find_weak_skills(context.masteries.values(), context.now, self._weak_limit):
            skill = self._content.get_skill(weak.mastery.skill_id)
            if skill:
                add(
                    self._build(
                        RecommendationKind.REINFORCEMENT,
                        skill,
                        weak.mastery,
                        weak.effective,
                        context,
                    )
                )
        add(self._review(context))
        for skill in self._new_topics(context):
            add(self._build(RecommendationKind.NEW_TOPIC, skill, None, None, context))
        for skill, mastery, eff in self._practice_candidates(context):
            add(self._build(RecommendationKind.PRACTICE, skill, mastery, eff, context))
        return recs

    # --- candidates -----------------------------------------------------------------

    def _new_topics(self, context: RecommendationContext) -> list[Skill]:
        level = context.profile.current_level
        per_module: dict[Module, list[Skill]] = {}
        for skill in self._content.list_skills():
            if skill.id in context.masteries:
                continue
            eligible = (
                skill.entry_level is level
                if skill.module is Module.VOCABULARY
                else skill.entry_level.rank <= level.rank
            )
            if eligible and self._has_activities(skill):
                per_module.setdefault(skill.module, []).append(skill)
        ordered = []
        for module in MODULE_ORDER:  # one new topic per module, easiest first
            skills = sorted(per_module.get(module, []), key=lambda s: (s.entry_level.rank, s.id))
            if skills:
                ordered.append(skills[0])
        return ordered

    def _has_activities(self, skill: Skill) -> bool:
        """Only skills this engine can build activities for (question-bank skills without
        lessons or exercises are practised from the bank's own sets)."""
        if skill.module is Module.GRAMMAR:
            return bool(self._content.list_exercises(skill.id))
        if skill.module is Module.VOCABULARY:
            return bool(self._content.list_vocabulary(skill.id))
        return skill.module in MODULE_ORDER

    def _practice_candidates(
        self, context: RecommendationContext
    ) -> list[tuple[Skill, SkillMastery, float]]:
        rows = []
        for m in context.masteries.values():
            eff = effective_mastery(m, context.now)
            skill = self._content.get_skill(m.skill_id)
            if skill and m.attempt_count > 0 and eff >= WEAKNESS_THRESHOLD:
                rows.append((skill, m, eff))
        # "Keep fresh" = least recently practised first (then lowest mastery), so the default
        # mix rotates across skills instead of drilling the same lowest one every time.
        rows.sort(key=lambda r: (r[1].last_practiced_at or context.now, r[2], r[0].id))
        return rows

    # --- builders -------------------------------------------------------------------

    def _review(self, context: RecommendationContext) -> Recommendation | None:
        ids = context.due_card_ids[: self._vocabulary_batch]
        if not ids:
            return None
        return Recommendation(
            kind=RecommendationKind.REVIEW,
            module=Module.VOCABULARY,
            skill_id="vocabulary.review",
            items=tuple(self._card_item(i) for i in ids),
            priority=0,
            reason_code="srs_cards_due",
            reason=f"{len(context.due_card_ids)} vocabulary card(s) are due for review today.",
            evidence={
                "due_count": len(context.due_card_ids),
                "word_count": len(context.due_card_ids),
            },
        )

    def _build(
        self,
        kind: RecommendationKind,
        skill: Skill,
        mastery: SkillMastery | None,
        effective: float | None,
        context: RecommendationContext,
    ) -> Recommendation | None:
        difficulty = (
            Difficulty.EASY
            if kind is RecommendationKind.NEW_TOPIC
            else target_difficulty(effective if effective is not None else 50.0)
        )
        items = self._items(skill, difficulty, kind, context)
        if not items:
            return None
        word_count = len(items) if skill.module is Module.VOCABULARY else None
        if word_count is not None:
            items = items[: self._vocabulary_batch]
        mistakes = _top_mistakes(skill.id, context)
        evidence: dict[str, Any] = {
            "skill_id": skill.id,
            "mastery": round(mastery.mastery, 1) if mastery else None,
            "effective_mastery": round(effective, 1) if effective is not None else None,
            "attempt_count": mastery.attempt_count if mastery else 0,
            "difficulty": difficulty.value,
            "weakness_threshold": WEAKNESS_THRESHOLD,
            "top_mistakes": mistakes,
        }
        if word_count is not None:
            # Words the vocabulary session will actually show (items is only a preview), so
            # the dashboard and the Practice page give the same number.
            evidence["word_count"] = word_count
        return Recommendation(
            kind=kind,
            module=skill.module,
            skill_id=skill.id,
            items=tuple(items),
            priority=0,
            reason_code=_REASON_CODE[kind],
            reason=_reason(kind, skill, effective, mistakes, len(items), difficulty),
            evidence=evidence,
        )

    def _items(
        self,
        skill: Skill,
        difficulty: Difficulty,
        kind: RecommendationKind,
        context: RecommendationContext,
    ) -> list[ActivityItem]:
        h = context.item_history
        level_rank = context.profile.current_level.rank
        if skill.module is Module.GRAMMAR:
            chosen = _choose(
                self._content.list_exercises(skill.id),
                lambda e: e.id,
                lambda e: e.difficulty,
                difficulty,
                h,
                self._grammar_batch,
            )
            return [ActivityItem(Module.GRAMMAR, e.id, e.prompt, e.difficulty) for e in chosen]

        if skill.module is Module.VOCABULARY:
            items = self._content.list_vocabulary(skill.id)
            # Only words today's vocabulary session will show: wrongly answered cards that are
            # due, then new cards (the count on the dashboard must match the session).
            due = set(context.due_card_ids)
            failed = sorted(
                (i for i in items if i.id in due and i.id in h and not h[i.id].last_correct),
                key=lambda i: h[i.id].last_attempted_at,
            )
            unseen = [i for i in items if i.id not in h][: context.new_cards_available]
            picked = (failed if kind is RecommendationKind.REINFORCEMENT else []) + unseen
            return [self._card_item(i.id) for i in picked]

        if skill.module is Module.LISTENING:
            lessons = self._content.list_listening()
            lesson_hist = {}
            for lesson in lessons:
                merged = _merge([h[q.id] for q in lesson.questions if q.id in h])
                if merged:
                    lesson_hist[lesson.id] = merged
            chosen = _choose(
                lessons,
                lambda ls: ls.id,
                lambda ls: ls.difficulty,
                difficulty,
                lesson_hist,
                1,
                above_level=lambda ls: ls.cefr_level.rank - level_rank,
            )
            return [ActivityItem(Module.LISTENING, x.id, x.title, x.difficulty) for x in chosen]

        if skill.module is Module.SPEAKING:
            prompts = [
                p for p in self._content.list_speaking() if p.cefr_level.rank <= level_rank + 1
            ]
            chosen = _choose(
                prompts,
                lambda p: p.id,
                lambda p: p.difficulty,
                difficulty,
                h,
                1,
                above_level=lambda p: p.cefr_level.rank - level_rank,
            )
            return [ActivityItem(Module.SPEAKING, p.id, p.title, p.difficulty) for p in chosen]

        if skill.module is Module.CONVERSATION:
            scenarios = [
                s for s in self._content.list_scenarios() if s.cefr_level.rank <= level_rank + 1
            ]
            diff_of = {
                s.id: _relative_difficulty(s.cefr_level.rank - level_rank) for s in scenarios
            }
            chosen = _choose(
                scenarios,
                lambda s: s.id,
                lambda s: diff_of[s.id],
                difficulty,
                h,
                1,
                above_level=lambda s: s.cefr_level.rank - level_rank,
            )
            return [ActivityItem(Module.CONVERSATION, s.id, s.title, diff_of[s.id]) for s in chosen]
        return []

    def _card_item(self, item_id: str) -> ActivityItem:
        item = self._content.get_vocabulary_item(item_id)
        title = f"{item.part_of_speech}: {item.definition[:70]}" if item else item_id
        return ActivityItem(Module.VOCABULARY, item_id, title)


# --- helpers ------------------------------------------------------------------------------


def _relative_difficulty(delta: int) -> Difficulty:
    if delta < 0:
        return Difficulty.EASY
    return Difficulty.MEDIUM if delta == 0 else Difficulty.HARD


def _merge(histories: list[ItemHistory]) -> ItemHistory | None:
    if not histories:
        return None
    latest = max(histories, key=lambda x: x.last_attempted_at)
    return ItemHistory(
        attempts=sum(x.attempts for x in histories),
        last_correct=all(x.last_correct for x in histories),
        last_attempted_at=latest.last_attempted_at,
        ever_correct=any(x.ever_correct for x in histories),
    )


def _choose(
    items: Sequence,
    key: Callable,
    diff: Callable,
    target: Difficulty,
    history: dict[str, ItemHistory],
    limit: int,
    above_level: Callable | None = None,
) -> list:
    """Material at or below the learner's level first (`above_level` = CEFR steps above it),
    then target difficulty; within it unseen, then failed, then least recently practised.
    The most recently attempted item is excluded unless nothing else is left."""
    if not items:
        return []
    last_seen = max(
        (history[key(i)].last_attempted_at for i in items if key(i) in history), default=None
    )

    def rank(i):
        hist = history.get(key(i))
        status = 0 if hist is None else (1 if not hist.last_correct else 2)
        recency = hist.last_attempted_at.timestamp() if hist else 0.0
        over = max(0, above_level(i)) if above_level else 0
        return (over, abs(_DIFF_RANK[diff(i)] - _DIFF_RANK[target]), status, recency, key(i))

    ordered = sorted(items, key=rank)
    fresh = [
        i
        for i in ordered
        if not (key(i) in history and history[key(i)].last_attempted_at == last_seen)
    ]
    return (fresh or ordered)[:limit]


def _top_mistakes(skill_id: str, context: RecommendationContext, n: int = 3) -> list[str]:
    counts = context.mistake_counts.get(skill_id, {})
    return [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


# Plain-language meaning of each mistake tag, with an example, for the learner-facing reason.
_MISTAKE_HINT = {
    "incomplete_answer": "the answer left out part of the task (e.g. the task asks for your "
    "name, home town and routine, and the answer only says hello)",
    "verb_tense": "the wrong tense (e.g. “Yesterday I go” instead of “Yesterday I went”)",
    "verb_form": "the wrong verb form (e.g. “She can swims” instead of “She can swim”)",
    "subject_verb_agreement": "the verb does not match the subject (e.g. “He don't” instead "
    "of “He doesn't”)",
    "article": "a missing or wrong a/an/the (e.g. “I am engineer” instead of “I am an engineer”)",
    "preposition": "the wrong preposition (e.g. “at Monday” instead of “on Monday”)",
    "comparative_form": "a wrong comparison (e.g. “more taller” instead of “taller”)",
    "conditional_structure": "a wrong if-sentence (e.g. “If I will see him” instead of “If I "
    "see him”)",
    "word_order": "words in the wrong order (e.g. “I like very much it” instead of “I like it "
    "very much”)",
    "word_choice": "a word that does not fit (e.g. “make a photo” instead of “take a photo”)",
    "spelling": "spelling (e.g. “recieve” instead of “receive”)",
    "wrong_word": "a different word from the one the card asks for",
    "no_answer": "cards left without an answer",
    "comprehension": "the answer missed the key information in the recording",
    "fluency": "speech that is too slow or too short, with long pauses or many “um”s",
}

_NEXT_STEP = {
    Module.GRAMMAR: "Do {n} {difficulty} exercise{s} on it",
    Module.VOCABULARY: "Review {n} word{s}",
    Module.LISTENING: "Listen to one recording and answer its questions",
    Module.SPEAKING: "Answer one speaking prompt out loud",
    Module.CONVERSATION: "Do one role-play",
}


def mistake_hint(tag: str) -> str:
    """'verb tense: the wrong tense (e.g. …)' — the tag's name plus what it means."""
    label = tag.replace("_", " ")
    hint = _MISTAKE_HINT.get(tag)
    return f"{label}: {hint}" if hint else label


def _reason(
    kind: RecommendationKind,
    skill: Skill,
    effective: float | None,
    mistakes: list[str],
    n_items: int = 1,
    difficulty: Difficulty = Difficulty.MEDIUM,
) -> str:
    if kind is RecommendationKind.NEW_TOPIC:
        return f"You haven't started {skill.name} yet."
    if kind is RecommendationKind.REINFORCEMENT:
        step = _NEXT_STEP.get(skill.module, "Practise it").format(
            n=n_items, s="" if n_items == 1 else "s", difficulty=difficulty.value
        )
        detail = f" Most frequent issue — {mistake_hint(mistakes[0])}." if mistakes else ""
        return (
            f"{skill.name} is at {effective:.0f}/100, below {WEAKNESS_THRESHOLD:.0f}, so it "
            f"needs work.{detail} {step} to bring it up."
        )
    return f"{skill.name} is at {effective:.0f}/100. Keep it fresh."


def _with_priority(rec: Recommendation, priority: int) -> Recommendation:
    return Recommendation(
        rec.kind,
        rec.module,
        rec.skill_id,
        rec.items,
        priority,
        rec.reason_code,
        rec.reason,
        rec.evidence,
    )
