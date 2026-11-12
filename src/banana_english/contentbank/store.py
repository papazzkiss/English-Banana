"""Reading and writing the bank files: content/bank/{passages,questions}/<skill>-NNN.jsonl.gz
plus manifest.json (counts and a hash per shard). Streamed: nothing holds the whole bank."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from banana_english.config.settings import PROJECT_ROOT
from banana_english.contentbank.schema import PassageRecord, QuestionRecord, parse_record

BANK_DIR = PROJECT_ROOT / "content" / "bank"
SHARD_SIZE = 5000


def _write_shards(folder: Path, skill: str, records: Iterable[dict]) -> list[dict]:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{skill}-*.jsonl.gz"):
        old.unlink()
    shards: list[dict] = []
    batch: list[str] = []

    def flush() -> None:
        if not batch:
            return
        path = folder / f"{skill}-{len(shards):03d}.jsonl.gz"
        payload = ("\n".join(batch) + "\n").encode()
        with gzip.GzipFile(path, "wb", mtime=0) as f:  # mtime=0: same content, same bytes
            f.write(payload)
        shards.append(
            {
                "file": str(path.relative_to(folder.parent)),
                "records": len(batch),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        batch.clear()

    for r in records:
        batch.append(json.dumps(r, ensure_ascii=False, sort_keys=True))
        if len(batch) >= SHARD_SIZE:
            flush()
    flush()
    return shards


def write_skill(
    skill: str,
    questions: Iterable[QuestionRecord],
    passages: Iterable[PassageRecord] = (),
    bank_dir: Path = BANK_DIR,
) -> dict:
    """Replace one skill's files and update the manifest."""
    q_shards = _write_shards(
        bank_dir / "questions", skill, (q.model_dump(mode="json") for q in questions)
    )
    p_shards = _write_shards(
        bank_dir / "passages", skill, (p.model_dump(mode="json") for p in passages)
    )
    manifest_path = bank_dir / "manifest.json"
    with _manifest_lock(bank_dir):
        return _update_manifest(manifest_path, skill, q_shards, p_shards)


@contextmanager
def _manifest_lock(bank_dir: Path):
    """Builds of different skills may run at the same time: one manifest update at a time."""
    import fcntl

    bank_dir.mkdir(parents=True, exist_ok=True)
    with (bank_dir / ".manifest.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _update_manifest(manifest_path: Path, skill: str, q_shards: list, p_shards: list) -> dict:
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("skills", {})
    manifest["skills"][skill] = {
        "questions": sum(s["records"] for s in q_shards),
        "passages": sum(s["records"] for s in p_shards),
        "shards": q_shards + p_shards,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    manifest["total_questions"] = sum(v["questions"] for v in manifest["skills"].values())
    manifest["hash"] = hashlib.sha256(
        json.dumps(
            {k: [s["sha256"] for s in v["shards"]] for k, v in sorted(manifest["skills"].items())},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest["skills"][skill]


def read_manifest(bank_dir: Path = BANK_DIR) -> dict:
    path = bank_dir / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {"skills": {}, "hash": ""}


def iter_records(bank_dir: Path = BANK_DIR) -> Iterator[QuestionRecord | PassageRecord]:
    """Every record of every shard in the manifest, validated. Passages come first per skill."""
    manifest = read_manifest(bank_dir)
    for skill in sorted(manifest["skills"]):
        shards = sorted(
            manifest["skills"][skill]["shards"], key=lambda s: not s["file"].startswith("passages")
        )
        for shard in shards:
            with gzip.open(bank_dir / shard["file"], "rt", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        yield parse_record(line)
