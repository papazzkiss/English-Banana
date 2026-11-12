"""Load content/bank into the database. Idempotent and incremental:

* new records are inserted, changed ones (different content hash, status or quality)
  updated, unchanged ones skipped;
* questions no longer in the bank are marked disabled (not deleted: learners' history and
  attempts keep pointing at them);
* batches of 2,000 rows; memory holds only ids and hashes.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from banana_english.contentbank.schema import PassageRecord, QuestionRecord
from banana_english.contentbank.store import BANK_DIR, iter_records, read_manifest
from banana_english.domain.models.bank import BankStatus
from banana_english.infrastructure.database.tables import (
    BankImportRow,
    BankPassageRow,
    BankQuestionRow,
)

BATCH = 2000


def _question_row(q: QuestionRecord, rand: float) -> dict:
    return {
        "id": q.id,
        "skill": q.skill,
        "skill_id": q.skill_id,
        "level": q.level.value,
        "topic": q.topic,
        "point": q.point,
        "qtype": q.qtype.value,
        "difficulty": q.difficulty.value,
        "passage_id": q.passage_id,
        "status": q.status.value,
        "quality": q.quality,
        "rand": rand,
        "content_hash": q.content_hash,
        "data": {
            "prompt": q.prompt,
            "instruction": q.instruction,
            "options": [o.model_dump() for o in q.options],
            "answer": q.answer,
            "explanation": q.explanation,
            "explanation_vi": q.explanation_vi,
            "display": q.display,
            "tags": q.tags,
            "source": q.source.model_dump(),
        },
    }


def _passage_row(p: PassageRecord) -> dict:
    return {
        "id": p.id,
        "skill": p.skill,
        "level": p.level.value,
        "topic": p.topic,
        "title": p.title[:200],
        "text": p.text,
        "audio": p.audio,
        "duration_s": p.duration_s,
        "status": p.status.value,
        "quality": p.quality,
        "source": p.source.model_dump(),
    }


def import_bank(
    session_factory: sessionmaker[Session],
    bank_dir: Path = BANK_DIR,
    log: Callable[[str], None] = print,
    seed: int | None = None,
) -> dict[str, int]:
    rng = random.Random(seed)
    manifest = read_manifest(bank_dir)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "disabled": 0, "passages": 0}
    with session_factory() as s:
        existing = {
            i: (h, st, ql)
            for i, h, st, ql in s.execute(
                select(
                    BankQuestionRow.id,
                    BankQuestionRow.content_hash,
                    BankQuestionRow.status,
                    BankQuestionRow.quality,
                )
            )
        }
        reviewed = set(
            s.scalars(select(BankQuestionRow.id).where(BankQuestionRow.reviewed_at.is_not(None)))
        )
        known_passages = set(s.scalars(select(BankPassageRow.id)))
        seen: set[str] = set()
        inserts: list[dict] = []
        updates: list[dict] = []

        def flush() -> None:
            if inserts:
                s.execute(BankQuestionRow.__table__.insert(), inserts)
                counts["inserted"] += len(inserts)
                inserts.clear()
            for row in updates:
                row.pop("rand")  # keep the random key: sets stay spread over the pool
                s.execute(
                    update(BankQuestionRow).where(BankQuestionRow.id == row["id"]).values(**row)
                )
            counts["updated"] += len(updates)
            updates.clear()
            s.commit()

        for record in iter_records(bank_dir):
            if isinstance(record, PassageRecord):
                row = _passage_row(record)
                if record.id in known_passages:
                    s.execute(
                        update(BankPassageRow).where(BankPassageRow.id == record.id).values(**row)
                    )
                else:
                    s.execute(BankPassageRow.__table__.insert(), [row])
                    known_passages.add(record.id)
                counts["passages"] += 1
                continue
            seen.add(record.id)
            old = existing.get(record.id)
            row = _question_row(record, rng.random())
            if record.id in reviewed and old is not None and old[0] == row["content_hash"]:
                # a person approved or disabled this exact question: their decision stands
                row["status"] = old[1]
            elif record.id in reviewed:
                # the content changed after the review: it needs a new one
                row["reviewed_by"], row["reviewed_at"] = None, None
            if old is None:
                inserts.append(row)
            elif old != (row["content_hash"], row["status"], row["quality"]) or (
                "reviewed_by" in row
            ):
                updates.append(row)
            else:
                counts["unchanged"] += 1
            if len(inserts) + len(updates) >= BATCH:
                flush()
                log(f"  {counts['inserted'] + counts['updated'] + counts['unchanged']:,} questions")
        flush()

        disabled = BankStatus.DISABLED.value
        gone = [i for i, (_, st, _) in existing.items() if i not in seen and st != disabled]
        for start in range(0, len(gone), BATCH):
            s.execute(
                update(BankQuestionRow)
                .where(BankQuestionRow.id.in_(gone[start : start + BATCH]))
                .values(status=disabled)
            )
        counts["disabled"] = len(gone)
        s.add(
            BankImportRow(
                manifest_hash=manifest.get("hash", ""),
                questions=len(seen),
                passages=counts["passages"],
                imported_at=datetime.now(UTC),
            )
        )
        s.commit()
    log(f"import done: {counts}")
    return counts


def import_if_changed(
    session_factory: sessionmaker[Session],
    bank_dir: Path = BANK_DIR,
    log: Callable[[str], None] = print,
) -> dict[str, int] | None:
    """Import only when the bank files differ from the last import (API start-up)."""
    manifest_hash = read_manifest(bank_dir).get("hash")
    if not manifest_hash:
        return None
    with session_factory() as s:
        last = s.scalars(select(BankImportRow).order_by(BankImportRow.id.desc()).limit(1)).first()
    if last is not None and last.manifest_hash == manifest_hash:
        return None
    return import_bank(session_factory, bank_dir, log)
