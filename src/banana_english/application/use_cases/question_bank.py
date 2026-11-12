"""Question-bank practice: draw a fresh set from the pool, check answers instantly.

A set is never a fixed test: every call samples the pool again, so the same filters give a
different set each time. Per set:
  * about a quarter are questions the learner got wrong, due for another try (spaced review);
  * of the fresh part, up to 40% come from the learner's weak skills (when no topic is chosen);
  * the rest are unseen questions, sampled from a random point of an index;
  * when unseen questions run out, the ones seen longest ago fill the set.
Reading and listening sets are drawn by passage (a text or a recording with its questions).

Answers are checked by rules (domain.services.answer_check), then the attempt, mastery and the
learner's question history are written in one short transaction. No LLM on this path.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from banana_english.application.use_cases.common import (
    ConflictError,
    InvalidInputError,
    MasteryChange,
    NotFoundError,
    UowFactory,
    record_mastery,
    require_learner,
    require_permission,
)
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.models import (
    Assessment,
    Assessor,
    Attempt,
    AttemptStatus,
    Module,
    Principal,
)
from banana_english.domain.models.bank import (
    BANK_MODULES,
    SERVED_STATUSES,
    BankPassage,
    BankQuestion,
    BankStatus,
    CheckResult,
    QuestionFilter,
)
from banana_english.domain.services.access import Permission
from banana_english.domain.services.answer_check import InvalidAnswerError, check_answer
from banana_english.domain.services.mastery import WEAKNESS_THRESHOLD, effective_mastery

MIN_SET, MAX_SET = 1, 50
REVIEW_SHARE = 0.25
WEAK_SHARE = 0.4
REVIEW_AFTER = timedelta(hours=12)  # a wrong answer comes back after this long
RECENT = timedelta(hours=1)  # never repeat something seen this recently (unless nothing else)
PER_PASSAGE = 6
FACETS_TTL = timedelta(minutes=5)
PASSAGE_SKILLS = (Module.READING, Module.LISTENING)
REVIEW_STATUSES = (BankStatus.APPROVED, BankStatus.VALIDATED, BankStatus.DISABLED)
MAX_REVIEW_PAGE = 100


@dataclass(frozen=True)
class PracticeSet:
    questions: list[BankQuestion]
    passages: dict[str, BankPassage]
    review_count: int  # how many are review questions


@dataclass(frozen=True)
class BankAnswerOutcome:
    attempt_id: str
    question: BankQuestion
    result: CheckResult
    mastery: MasteryChange


class QuestionBankPractice:
    def __init__(
        self,
        uow_factory: UowFactory,
        clock: Clock,
        rng: random.Random | None = None,
        *,
        approved_only: bool = False,
    ):
        """approved_only: serve only person-checked questions (BANANA_REQUIRE_REVIEWED_CONTENT)."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._rng = rng or random.Random()
        self.statuses = (BankStatus.APPROVED,) if approved_only else SERVED_STATUSES
        self._facets: dict[Module, tuple[datetime, dict[str, dict[str, int]]]] = {}

    # --- sets ------------------------------------------------------------------------------
    def facets(self, skill: Module) -> dict[str, dict[str, int]]:
        """Counts per filter value. They change only when the bank is imported, so they are
        kept for FACETS_TTL (five GROUP BY queries over the whole pool otherwise)."""
        _require_bank_skill(skill)
        now = self._clock.now()
        hit = self._facets.get(skill)
        if hit is not None and now - hit[0] < FACETS_TTL:
            return hit[1]
        with self._uow_factory() as uow:
            facets = uow.bank.facets(skill, self.statuses)
        self._facets[skill] = (now, facets)
        return facets

    def build_set(self, learner_id: str, f: QuestionFilter, count: int) -> PracticeSet:
        _require_bank_skill(f.skill)
        count = max(MIN_SET, min(MAX_SET, count))
        f = replace(f, statuses=self.statuses)
        now = self._clock.now()
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            if f.skill in PASSAGE_SKILLS:
                return self._passage_set(uow, learner_id, f, count, now)
            return self._question_set(uow, learner_id, f, count, now)

    def _question_set(self, uow, learner_id: str, f: QuestionFilter, count: int, now: datetime):
        chosen: dict[str, BankQuestion] = {}

        def take(questions: list[BankQuestion], limit: int) -> None:
            for q in _diverse(questions):
                if len(chosen) >= limit:
                    return
                chosen.setdefault(q.id, q)

        review = uow.bank.pick_seen(
            f,
            learner_id,
            round(count * REVIEW_SHARE),
            seen_before=now - REVIEW_AFTER,
            wrong_only=True,
        )
        take(review, len(review))
        review_count = len(chosen)

        weak = (
            self._weak_skills(uow, learner_id, f.skill, now)
            if not (f.points or f.skill_ids)
            else ()
        )
        if weak:
            weak_n = round((count - len(chosen)) * WEAK_SHARE)
            weak_filter = replace(f, skill_ids=weak)
            take(
                uow.bank.pick_unseen(weak_filter, learner_id, weak_n * 3, self._rng.random()),
                len(chosen) + weak_n,
            )
        take(
            uow.bank.pick_unseen(f, learner_id, (count - len(chosen)) * 3, self._rng.random()),
            count,
        )
        if len(chosen) < count:  # the pool is used up: repeat the oldest ones
            take(
                uow.bank.pick_seen(
                    f, learner_id, count * 2, seen_before=now - RECENT, wrong_only=False
                ),
                count,
            )
        questions = list(chosen.values())
        self._rng.shuffle(questions)
        return PracticeSet(questions, {}, review_count)

    def _passage_set(self, uow, learner_id: str, f: QuestionFilter, count: int, now: datetime):
        questions: list[BankQuestion] = []
        passage_ids: list[str] = []

        def add_passages(candidates: list[BankQuestion], skip_seen: bool) -> None:
            ids = list(dict.fromkeys(q.passage_id for q in candidates if q.passage_id))
            seen = uow.question_stats.seen_passages(learner_id, ids) if skip_seen else set()
            for pid in ids:
                if len(questions) >= count or pid in passage_ids or pid in seen:
                    continue
                qs = _passage_order(uow.bank.passage_questions(pid, f))[:PER_PASSAGE]
                if qs:
                    passage_ids.append(pid)
                    questions.extend(qs)

        add_passages(uow.bank.pick_unseen(f, learner_id, count * 4, self._rng.random()), True)
        if len(questions) < count:
            review = uow.bank.pick_seen(
                f, learner_id, count * 2, seen_before=now - REVIEW_AFTER, wrong_only=True
            )
            add_passages(review, False)
        if len(questions) < count:
            add_passages(
                uow.bank.pick_seen(
                    f, learner_id, count * 4, seen_before=now - RECENT, wrong_only=False
                ),
                False,
            )
        passages = uow.bank.passages(passage_ids)
        return PracticeSet(questions, passages, 0)

    @staticmethod
    def _weak_skills(uow, learner_id: str, skill: Module, now: datetime) -> tuple[str, ...]:
        prefix = f"{skill.value}."
        return tuple(
            m.skill_id
            for m in uow.mastery.list(learner_id)
            if m.skill_id.startswith(prefix)
            and m.attempt_count >= 3
            and effective_mastery(m, now) < WEAKNESS_THRESHOLD
        )

    # --- answers ---------------------------------------------------------------------------
    def passage_transcript(self, learner_id: str, passage_id: str) -> BankPassage:
        """A listening transcript, shown after the learner answered one of its questions."""
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            passage = uow.bank.passages([passage_id]).get(passage_id)
            if passage is None:
                raise NotFoundError(f"passage {passage_id}")
            # the transcript holds the answers (dictation, "which sentence did you hear?")
            if passage_id not in uow.question_stats.seen_passages(learner_id, [passage_id]):
                raise ConflictError("answer a question about this recording first")
            return passage

    def answer(
        self, learner_id: str, question_id: str, answer: Any, response_time_ms: int | None = None
    ) -> BankAnswerOutcome:
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            question = uow.bank.get(question_id)
            # a draft or disabled question (or, in reviewed-only mode, an unreviewed one) is
            # never served, so it cannot be answered either: that would reveal its answer
            if question is None or question.status not in self.statuses:
                raise NotFoundError(f"question {question_id}")
            try:
                result = check_answer(question, answer)
            except InvalidAnswerError as exc:
                raise InvalidInputError(str(exc)) from exc
            now = self._clock.now()
            previous = uow.question_stats.get(learner_id, question_id)
            attempt_id = _new_id()
            assessment = Assessment(
                score=result.score,
                is_correct=result.correct,
                feedback=question.explanation,
                assessor=Assessor.DETERMINISTIC,
                corrected_answer=None if result.correct else result.correct_answer,
            )
            uow.attempts.add(
                Attempt(
                    attempt_id,
                    learner_id,
                    question.skill,
                    question.id,
                    question.skill_id,
                    _as_text(answer),
                    now,
                    AttemptStatus.ASSESSED,
                    response_time_ms,
                    assessment,
                    {"source": "bank", "qtype": question.qtype.value, "point": question.point},
                )
            )
            change = record_mastery(
                uow,
                learner_id,
                question.skill_id,
                score=result.score,
                is_correct=result.correct,
                at=now,
                attempt_id=attempt_id,
                repeat=bool(previous and previous.correct),
            )
            uow.question_stats.record(learner_id, question, result.correct, now)
            uow.commit()
        return BankAnswerOutcome(attempt_id, question, result, change)

    # --- review (teachers and admins) -----------------------------------------------------
    def review_page(
        self,
        actor: Principal,
        f: QuestionFilter,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[tuple[BankQuestion, str | None, datetime | None]], int]:
        """Questions of any status, with answers, for a reviewer."""
        require_permission(actor, Permission.REVIEW_CONTENT)
        _require_bank_skill(f.skill)
        with self._uow_factory() as uow:
            return uow.bank.review_page(f, query, min(limit, MAX_REVIEW_PAGE), max(offset, 0))

    def set_status(
        self, actor: Principal, question_id: str, status: BankStatus
    ) -> tuple[BankQuestion, str, datetime]:
        """A reviewer's decision: approve, send back to validated, or disable a question. It
        is kept across bank imports while the question's content does not change."""
        require_permission(actor, Permission.REVIEW_CONTENT)
        if status not in REVIEW_STATUSES:
            raise InvalidInputError(f"status must be one of {[s.value for s in REVIEW_STATUSES]}")
        now = self._clock.now()
        with self._uow_factory() as uow:
            if not uow.bank.set_status(question_id, status, actor.user_id, now):
                raise NotFoundError(f"question {question_id}")
            uow.commit()
            question = uow.bank.get(question_id)
        self._facets.clear()  # the counts per filter changed
        return question, actor.user_id, now

    def summary(self, learner_id: str, skill: Module) -> dict[str, int]:
        _require_bank_skill(skill)
        with self._uow_factory() as uow:
            require_learner(uow, learner_id)
            stats = uow.question_stats.summary(learner_id, skill)
            stats["pool_size"] = uow.bank.count(skill, self.statuses)
            return stats


def _require_bank_skill(skill: Module) -> None:
    if skill not in BANK_MODULES:
        raise NotFoundError(f"no question bank for {skill.value}")


def _diverse(questions: list[BankQuestion]) -> list[BankQuestion]:
    """Round-robin over grammar points / focuses, so a set is not ten questions on one rule."""
    by_point: dict[str, list[BankQuestion]] = {}
    for q in questions:
        by_point.setdefault(q.point, []).append(q)
    out: list[BankQuestion] = []
    while by_point:
        for point in list(by_point):
            out.append(by_point[point].pop(0))
            if not by_point[point]:
                del by_point[point]
    return out


_PASSAGE_FIRST = {"main_idea": 0, "title": 0, "gist": 0}


def _passage_order(questions: list[BankQuestion]) -> list[BankQuestion]:
    return sorted(questions, key=lambda q: (_PASSAGE_FIRST.get(q.point, 1), q.id))


def _as_text(answer: Any) -> str:
    if isinstance(answer, str):
        return answer[:1000]
    import json

    return json.dumps(answer, ensure_ascii=False)[:1000]


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())
