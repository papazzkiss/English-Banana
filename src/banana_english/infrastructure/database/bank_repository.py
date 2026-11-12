"""SQL access to the question bank and to each learner's question history.

Every query goes through an index: the filter columns plus the random key `rand` for sampling,
(learner_id, question_id) for history. Nothing loads the whole bank.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from banana_english.domain.models import CefrLevel, Difficulty, Module
from banana_english.domain.models.bank import (
    SERVED_STATUSES,
    BankOption,
    BankPassage,
    BankQuestion,
    BankStatus,
    QuestionFilter,
    QuestionStat,
    QuestionType,
)
from banana_english.infrastructure.database.tables import (
    BankImportRow,
    BankPassageRow,
    BankQuestionRow,
    LearnerQuestionStatRow,
)


def question_from_row(row: BankQuestionRow) -> BankQuestion:
    d: dict[str, Any] = row.data
    return BankQuestion(
        id=row.id,
        skill=Module(row.skill),
        skill_id=row.skill_id,
        level=CefrLevel(row.level),
        topic=row.topic,
        point=row.point,
        difficulty=Difficulty(row.difficulty),
        qtype=QuestionType(row.qtype),
        prompt=d["prompt"],
        instruction=d.get("instruction", ""),
        answer=d["answer"],
        explanation=d.get("explanation", ""),
        explanation_vi=d.get("explanation_vi", ""),
        options=tuple(BankOption(o["id"], o["text"]) for o in d.get("options") or ()),
        passage_id=row.passage_id,
        tags=tuple(d.get("tags") or ()),
        quality=row.quality,
        status=BankStatus(row.status),
        display=d.get("display") or {},
    )


def passage_from_row(row: BankPassageRow) -> BankPassage:
    return BankPassage(
        id=row.id,
        skill=Module(row.skill),
        level=CefrLevel(row.level),
        topic=row.topic,
        title=row.title,
        text=row.text,
        audio=row.audio,
        duration_s=row.duration_s,
        source=row.source or {},
    )


def _filtered(query, f: QuestionFilter):
    q = BankQuestionRow
    query = query.where(q.skill == f.skill.value, q.status.in_([x.value for x in f.statuses]))
    if f.levels:
        query = query.where(q.level.in_([x.value for x in f.levels]))
    if f.topics:
        query = query.where(q.topic.in_(f.topics))
    if f.points:
        query = query.where(q.point.in_(f.points))
    if f.qtypes:
        query = query.where(q.qtype.in_([x.value for x in f.qtypes]))
    if f.difficulties:
        query = query.where(q.difficulty.in_([x.value for x in f.difficulties]))
    if f.skill_ids:
        query = query.where(q.skill_id.in_(f.skill_ids))
    return query


def _ordered_parts(f: QuestionFilter) -> Iterator[QuestionFilter]:
    """The filter split into one status (and one level) each. With equality on those, a query
    reads its index in `rand` order and stops after `limit` rows; with IN lists the database
    would have to sort every matching row first."""
    for status in f.statuses:
        for level in f.levels or (None,):
            yield replace(f, statuses=(status,), levels=(level,) if level else ())


class SqlQuestionBank:
    def __init__(self, session: Session) -> None:
        self._s = session

    # --- reads ---------------------------------------------------------------------------
    def get(self, question_id: str) -> BankQuestion | None:
        row = self._s.get(BankQuestionRow, question_id)
        return question_from_row(row) if row is not None else None

    def get_many(self, ids: Sequence[str]) -> list[BankQuestion]:
        if not ids:
            return []
        rows = self._s.scalars(select(BankQuestionRow).where(BankQuestionRow.id.in_(ids)))
        by_id = {r.id: question_from_row(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def passages(self, ids: Iterable[str]) -> dict[str, BankPassage]:
        ids = list(dict.fromkeys(ids))
        if not ids:
            return {}
        rows = self._s.scalars(select(BankPassageRow).where(BankPassageRow.id.in_(ids)))
        return {r.id: passage_from_row(r) for r in rows}

    def passage_questions(self, passage_id: str, f: QuestionFilter) -> list[BankQuestion]:
        query = _filtered(select(BankQuestionRow), f).where(
            BankQuestionRow.passage_id == passage_id
        )
        return [question_from_row(r) for r in self._s.scalars(query.order_by(BankQuestionRow.id))]

    # --- sampling ------------------------------------------------------------------------
    def pick_unseen(
        self, f: QuestionFilter, learner_id: str, limit: int, pivot: float
    ) -> list[BankQuestion]:
        """Questions the learner has never seen, starting at a random point of the index."""
        seen = exists().where(
            LearnerQuestionStatRow.learner_id == learner_id,
            LearnerQuestionStatRow.question_id == BankQuestionRow.id,
        )
        rand = BankQuestionRow.rand
        after: list[BankQuestionRow] = []
        before: list[BankQuestionRow] = []
        for part in _ordered_parts(f):
            base = _filtered(select(BankQuestionRow), part).where(~seen)
            got = list(self._s.scalars(base.where(rand >= pivot).order_by(rand).limit(limit)))
            after += got
            if len(got) < limit:  # wrap around the random key
                before += self._s.scalars(base.where(rand < pivot).order_by(rand).limit(limit))
        rows = sorted(after, key=lambda r: r.rand)[:limit]
        rows += sorted(before, key=lambda r: r.rand)[: limit - len(rows)]
        return [question_from_row(r) for r in rows]

    def pick_seen(
        self,
        f: QuestionFilter,
        learner_id: str,
        limit: int,
        *,
        seen_before: datetime,
        wrong_only: bool,
    ) -> list[BankQuestion]:
        """Questions seen before `seen_before`: the wrong ones first (review), else the ones
        seen longest ago."""
        s = LearnerQuestionStatRow
        query = _filtered(
            select(BankQuestionRow).join(
                s, and_(s.question_id == BankQuestionRow.id, s.learner_id == learner_id)
            ),
            f,
        ).where(s.last_seen < seen_before)
        if wrong_only:
            query = query.where(s.last_correct.is_(False))
            order = (s.wrong.desc(), s.last_seen)
        else:
            order = (s.last_seen,)
        return [question_from_row(r) for r in self._s.scalars(query.order_by(*order).limit(limit))]

    # --- facets (for the set builder's filters) -------------------------------------------
    def facets(
        self, skill: Module, statuses: Sequence[BankStatus] = SERVED_STATUSES
    ) -> dict[str, dict[str, int]]:
        q = BankQuestionRow
        served = [x.value for x in statuses]
        out: dict[str, dict[str, int]] = {}
        for name, column in (
            ("levels", q.level),
            ("topics", q.topic),
            ("points", q.point),
            ("qtypes", q.qtype),
            ("difficulties", q.difficulty),
        ):
            rows = self._s.execute(
                select(column, func.count())
                .where(q.skill == skill.value, q.status.in_(served))
                .group_by(column)
            )
            out[name] = {str(k): int(n) for k, n in rows}
        return out

    def count(
        self, skill: Module | None = None, statuses: Sequence[BankStatus] = SERVED_STATUSES
    ) -> int:
        query = (
            select(func.count())
            .select_from(BankQuestionRow)
            .where(BankQuestionRow.status.in_([x.value for x in statuses]))
        )
        if skill is not None:
            query = query.where(BankQuestionRow.skill == skill.value)
        return int(self._s.scalar(query) or 0)

    # --- review (teachers and admins) -------------------------------------------------------
    def review_page(
        self, f: QuestionFilter, query: str = "", limit: int = 50, offset: int = 0
    ) -> tuple[list[tuple[BankQuestion, str | None, datetime | None]], int]:
        """Questions with their answers for review, in id order: (question, reviewer, when)."""
        q = _filtered(select(BankQuestionRow), f)
        if query.strip():
            q = q.where(BankQuestionRow.id.like(f"%{query.strip()}%"))
        total = int(self._s.scalar(select(func.count()).select_from(q.subquery())) or 0)
        rows = self._s.scalars(q.order_by(BankQuestionRow.id).limit(limit).offset(offset))
        return [(question_from_row(r), r.reviewed_by, r.reviewed_at) for r in rows], total

    def set_status(self, question_id: str, status: BankStatus, by: str, at: datetime) -> bool:
        row = self._s.get(BankQuestionRow, question_id)
        if row is None:
            return False
        row.status, row.reviewed_by, row.reviewed_at = status.value, by, at
        return True

    def status_counts(self) -> dict[str, dict[str, int]]:
        """Questions per skill and status (admin dashboard)."""
        out: dict[str, dict[str, int]] = {}
        rows = self._s.execute(
            select(BankQuestionRow.skill, BankQuestionRow.status, func.count()).group_by(
                BankQuestionRow.skill, BankQuestionRow.status
            )
        )
        for skill, status, n in rows:
            out.setdefault(skill, {})[status] = int(n)
        return out

    def last_import(self) -> dict[str, Any] | None:
        row = self._s.scalar(select(BankImportRow).order_by(BankImportRow.id.desc()).limit(1))
        if row is None:
            return None
        return {
            "manifest_hash": row.manifest_hash,
            "questions": row.questions,
            "passages": row.passages,
            "imported_at": row.imported_at,
        }


class SqlQuestionStats:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, learner_id: str, question_id: str) -> QuestionStat | None:
        row = self._s.get(LearnerQuestionStatRow, (learner_id, question_id))
        if row is None:
            return None
        return QuestionStat(
            row.learner_id,
            row.question_id,
            row.attempts,
            row.correct,
            row.wrong,
            row.last_seen,
            row.last_correct,
        )

    def record(self, learner_id: str, question: BankQuestion, correct: bool, at: datetime) -> None:
        row = self._s.get(LearnerQuestionStatRow, (learner_id, question.id))
        if row is None:
            row = LearnerQuestionStatRow(
                learner_id=learner_id,
                question_id=question.id,
                skill=question.skill.value,
                passage_id=question.passage_id,
                attempts=0,
                correct=0,
                wrong=0,
                last_seen=at,
                last_correct=correct,
            )
            self._s.add(row)
        row.attempts += 1
        row.correct += int(correct)
        row.wrong += int(not correct)
        row.last_seen = at
        row.last_correct = correct

    def seen_passages(self, learner_id: str, passage_ids: Sequence[str]) -> set[str]:
        if not passage_ids:
            return set()
        s = LearnerQuestionStatRow
        rows = self._s.scalars(
            select(s.passage_id)
            .where(s.learner_id == learner_id, s.passage_id.in_(passage_ids))
            .distinct()
        )
        return {r for r in rows if r}

    def summary(self, learner_id: str, skill: Module) -> dict[str, int]:
        s = LearnerQuestionStatRow
        row = self._s.execute(
            select(
                func.count(),
                func.coalesce(func.sum(s.correct), 0),
                func.coalesce(func.sum(s.wrong), 0),
                func.count().filter(or_(s.last_correct.is_(False))),
            ).where(s.learner_id == learner_id, s.skill == skill.value)
        ).one()
        return {
            "questions_seen": int(row[0]),
            "correct_answers": int(row[1]),
            "wrong_answers": int(row[2]),
            "to_review": int(row[3]),
        }
