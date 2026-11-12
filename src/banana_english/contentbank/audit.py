"""Question-bank audit: what the pool holds and whether it is sound.

  python scripts/audit_content.py [--db] [--json report.json]

Counts (skill, level, topic, difficulty, type, point, status), duplicate and invalid rates,
missing fields, quality scores, answer-position bias, broken passage links and missing audio.
With --db, also compares the database tables with the bank files. Exit code 1 when something
is broken (invalid records, questions without their passage, missing audio).
"""

from __future__ import annotations

import gzip
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from banana_english.contentbank.build import near_duplicate_key
from banana_english.contentbank.schema import PassageRecord, QuestionRecord, parse_record
from banana_english.contentbank.store import BANK_DIR, read_manifest
from banana_english.domain.models.bank import SERVED_STATUSES, QuestionType
from banana_english.domain.services.answer_matching import normalize_answer

LEVELS = ("A1", "A2", "B1", "B2", "C1")


def _records(bank_dir: Path):
    manifest = read_manifest(bank_dir)
    invalid: list[str] = []
    for skill in sorted(manifest["skills"]):
        for shard in manifest["skills"][skill]["shards"]:
            with gzip.open(bank_dir / shard["file"], "rt", encoding="utf-8") as f:
                for n, line in enumerate(f, start=1):
                    if not line.strip():
                        continue
                    try:
                        yield parse_record(line)
                    except Exception as exc:  # noqa: BLE001 - counted as invalid
                        invalid.append(f"{shard['file']}:{n}: {str(exc)[:120]}")
    yield invalid


def audit(bank_dir: Path = BANK_DIR) -> dict:
    questions: list[QuestionRecord] = []
    passages: dict[str, PassageRecord] = {}
    invalid: list[str] = []
    for r in _records(bank_dir):
        if isinstance(r, list):
            invalid = r
        elif isinstance(r, PassageRecord):
            passages[r.id] = r
        else:
            questions.append(r)
    served = [q for q in questions if q.status in SERVED_STATUSES]
    report: dict = {
        "total_questions": len(questions),
        "served_questions": len(served),
        "passages": len(passages),
    }

    def counts(key) -> dict:
        return dict(sorted(Counter(key(q) for q in served).items()))

    report["by_skill"] = counts(lambda q: q.skill)
    report["by_level"] = {lvl: sum(1 for q in served if q.level.value == lvl) for lvl in LEVELS}
    report["by_skill_level"] = {
        skill: {
            lvl: sum(1 for q in served if q.skill == skill and q.level.value == lvl)
            for lvl in LEVELS
        }
        for skill in report["by_skill"]
    }
    report["by_difficulty"] = counts(lambda q: q.difficulty.value)
    report["by_type"] = counts(lambda q: q.qtype.value)
    report["by_topic"] = counts(lambda q: q.topic)
    report["by_point"] = {
        s: dict(Counter(q.point for q in served if q.skill == s).most_common())
        for s in report["by_skill"]
    }
    report["by_status"] = dict(Counter(q.status.value for q in questions))

    # duplicates: the same question twice in a skill: same passage, prompt, options (and
    # matching column) and answer. "What is the text mainly about?" about two different texts
    # is two questions. near: the same prompt with other names/numbers (questions without a
    # passage)
    def same_question(q: QuestionRecord) -> tuple:
        left = sorted(normalize_answer(x["text"]) for x in q.display.get("left") or ())
        return (
            q.skill,
            q.passage_id or "",
            normalize_answer(q.prompt),
            tuple(sorted(normalize_answer(o.text) for o in q.options)),
            tuple(left),
            json.dumps(q.answer, sort_keys=True) if not q.options else "",
        )

    exact = Counter(same_question(q) for q in served)

    def content(q: QuestionRecord) -> str:  # ordering / matching: the prompt is an instruction
        if q.qtype == "ordering":
            return " ".join(q.answer.get("order") or ())
        if q.qtype == "matching":
            return " | ".join(sorted(x["text"] for x in q.display.get("left") or ()))
        return q.prompt

    near = Counter(
        (q.skill, q.point, near_duplicate_key(content(q))) for q in served if q.passage_id is None
    )
    dup = sum(n - 1 for n in exact.values() if n > 1)
    near_dup = sum(n - 1 for n in near.values() if n > 1)
    report["duplicate_rate"] = round(dup / max(1, len(served)), 5)
    report["near_duplicate_rate"] = round(near_dup / max(1, len(served)), 5)

    # soundness
    problems: dict[str, list[str]] = defaultdict(list)
    for q in served:
        if q.qtype in (QuestionType.MCQ, QuestionType.ERROR_ID, QuestionType.TRUE_FALSE):
            texts = [normalize_answer(o.text) for o in q.options]
            if len(set(texts)) != len(texts):
                problems["duplicate options"].append(q.id)
        if q.passage_id and q.passage_id not in passages:
            problems["question without its passage"].append(q.id)
        if not q.explanation.strip():
            problems["no explanation"].append(q.id)
    per_passage = Counter(q.passage_id for q in served if q.passage_id)
    for pid, p in passages.items():
        if p.status not in SERVED_STATUSES:
            continue
        if per_passage.get(pid, 0) < 2:
            problems["passage with fewer than 2 questions"].append(pid)
        if p.skill == "listening":
            audio = bank_dir / "audio" / (p.audio or "")
            if not p.audio or not audio.is_file():
                problems["missing audio"].append(pid)
            elif not p.duration_s:
                problems["audio without duration"].append(pid)
    report["invalid_records"] = len(invalid)
    report["invalid_rate"] = round(len(invalid) / max(1, len(questions) + len(invalid)), 5)
    report["invalid_examples"] = invalid[:5]
    report["problems"] = {k: {"count": len(v), "examples": v[:5]} for k, v in problems.items()}
    report["missing_fields"] = {
        "explanation_vi": sum(1 for q in served if not q.explanation_vi.strip()),
        "topic": sum(1 for q in served if not q.topic),
    }
    quality = [q.quality for q in served]
    report["quality"] = {
        "mean": round(statistics.fmean(quality), 3) if quality else None,
        "p10": round(statistics.quantiles(quality, n=10)[0], 3) if len(quality) > 10 else None,
        "min": round(min(quality), 3) if quality else None,
    }
    positions = Counter(
        q.answer.get("option")
        for q in served
        if q.qtype in (QuestionType.MCQ, QuestionType.ERROR_ID)
    )
    report["answer_positions"] = dict(sorted(positions.items()))
    audio_files = list((bank_dir / "audio").rglob("*.ogg"))
    report["audio"] = {
        "files": len(audio_files),
        "megabytes": round(sum(f.stat().st_size for f in audio_files) / 1e6, 1),
        "hours": round(sum(p.duration_s or 0 for p in passages.values()) / 3600, 2),
    }
    report["broken"] = bool(invalid) or any(
        k in problems for k in ("question without its passage", "missing audio")
    )
    return report


def db_counts() -> dict:
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from banana_english.config.settings import Settings
    from banana_english.infrastructure.database.repositories import create_db_engine
    from banana_english.infrastructure.database.tables import (
        BankImportRow,
        BankPassageRow,
        BankQuestionRow,
    )

    engine = create_db_engine(Settings().database_url)
    with Session(engine) as s:
        by = s.execute(
            select(BankQuestionRow.skill, BankQuestionRow.status, func.count()).group_by(
                BankQuestionRow.skill, BankQuestionRow.status
            )
        ).all()
        last = s.scalars(select(BankImportRow).order_by(BankImportRow.id.desc()).limit(1)).first()
        return {
            "questions": {f"{k}/{st}": n for k, st, n in by},
            "passages": s.scalar(select(func.count()).select_from(BankPassageRow)),
            "last_import": {"manifest_hash": last.manifest_hash, "at": last.imported_at.isoformat()}
            if last
            else None,
            "manifest_hash": read_manifest().get("hash"),
        }


def _print(report: dict) -> None:
    print(
        f"Total questions: {report['total_questions']:,} (served {report['served_questions']:,}),"
        f" passages {report['passages']:,}"
    )
    print("By skill:", ", ".join(f"{k} {v:,}" for k, v in report["by_skill"].items()))
    print("By level:", ", ".join(f"{k} {v:,}" for k, v in report["by_level"].items()))
    for skill, levels in report["by_skill_level"].items():
        print(f"  {skill:10}", "  ".join(f"{k} {v:>6,}" for k, v in levels.items()))
    print("By difficulty:", report["by_difficulty"])
    print("By type:", report["by_type"])
    print("By topic:", report["by_topic"])
    print("By status:", report["by_status"])
    print(
        f"Duplicate rate: {report['duplicate_rate']:.3%}   near-duplicate rate: "
        f"{report['near_duplicate_rate']:.3%}"
    )
    print(f"Invalid records: {report['invalid_records']} ({report['invalid_rate']:.3%})")
    print("Problems:", {k: v["count"] for k, v in report["problems"].items()} or "none")
    print("Missing fields:", report["missing_fields"])
    print("Quality:", report["quality"], " answer positions:", report["answer_positions"])
    print("Audio:", report["audio"])
    if "db" in report:
        print("Database:", report["db"])
    print("RESULT:", "BROKEN" if report["broken"] else "OK")


def run_audit(
    check_db: bool = False, json_path: str | None = None, bank_dir: Path = BANK_DIR
) -> int:
    report = audit(bank_dir)
    if check_db:
        report["db"] = db_counts()
    _print(report)
    if json_path:
        Path(json_path).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["broken"] else 0
