"""Human review of AI-generated content: grammar exercises, listening lessons, speaking prompts,
conversation scenarios. Nothing AI-written is official until a teacher approves it.

    uv run python scripts/review_content.py --list
    uv run python scripts/review_content.py --reviewer "Jane Doe" [--kind grammar]

Per item: [a]pprove, [r]eject, [e]dit accepted answers (grammar / listening), [s]kip, [q]uit.
Every decision is saved immediately. Then run with BANANA_REQUIRE_REVIEWED_CONTENT=true.
Checklist: natural English; the accepted answers are complete (add missing correct variants —
it is cheaper and more reliable than asking the LLM); the CEFR level fits; the explanation or
transcript is correct.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "content"
KINDS = {
    "grammar": ("grammar/exercises.json", "exercises"),
    "listening": ("listening/lessons.json", "lessons"),
    "speaking": ("speaking/prompts.json", "prompts"),
    "conversation": ("conversation/scenarios.json", "scenarios"),
}


def show(kind: str, item: dict) -> None:
    print("\n" + "=" * 76)
    print(f"[{kind}] {item['id']}  {item.get('cefr_level', '')} {item.get('difficulty', '')}")
    if kind == "grammar":
        print(f"Instruction: {item['instruction']}\nPrompt:      {item['prompt']}")
        print(f"Answers:     {item['accepted_answers']}\nExplanation: {item['explanation']}")
    elif kind == "listening":
        print(f"Transcript:  {item['transcript']}")
        for i, q in enumerate(item["questions"]):
            print(f"  Q{i + 1} {q['question']}  -> {q['accepted_answers']}")
    elif kind == "speaking":
        print(f"Instruction: {item['instruction']}\nTargets:     {item['target_grammar']}")
    else:
        print(f"Situation:   {item['situation']}\nOpening:     {item['opening_line']}")
        print(f"Goals:       {item['goals']}\nTargets:     {item['target_skills']}")


def edit_answers(kind: str, item: dict) -> None:
    targets = [item] if kind == "grammar" else item.get("questions", [])
    for t in targets:
        raw = input(
            f"Accepted answers for {t.get('question', 'the exercise')} "
            f"(' | ' separated, empty = keep): "
        ).strip()
        if raw:
            t["accepted_answers"] = [a.strip() for a in raw.split("|") if a.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer")
    parser.add_argument("--kind", choices=list(KINDS))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    for kind, (rel, key) in KINDS.items():
        data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        print(f"{kind:13s}", dict(Counter(x["review"]["status"] for x in data[key])))
    if args.list:
        return
    if not args.reviewer:
        parser.error("--reviewer is required to review")

    for kind, (rel, key) in KINDS.items():
        if args.kind and kind != args.kind:
            continue
        path = ROOT / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data[key]:
            if item["review"]["status"] != "pending_review":
                continue
            show(kind, item)
            while True:
                choice = input("[a]pprove [r]eject [e]dit answers [s]kip [q]uit > ").strip().lower()
                if choice == "e" and kind in ("grammar", "listening"):
                    edit_answers(kind, item)
                    show(kind, item)
                    continue
                if choice in ("a", "r"):
                    item["review"].update(
                        status="approved" if choice == "a" else "rejected",
                        reviewed_by=args.reviewer,
                        reviewed_at=datetime.now(UTC).isoformat(timespec="seconds"),
                        notes=input("Notes (optional): ").strip() or None,
                    )
                    path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                if choice == "q":
                    return
                if choice in ("a", "r", "s"):
                    break


if __name__ == "__main__":
    main()
