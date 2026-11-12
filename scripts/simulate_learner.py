"""Simulate a learner practising for N days (Phase 4 / Phase 10 evidence).

The simulated learner always does what GET /recommendation/next suggests, answers with a
probability of being right that depends on a hidden "true ability" per skill, and learns a
little every time it practises. Past tense starts weak on purpose, so the recommender should
keep returning to it until it improves — visible on the dashboard's mastery curves.

Runs in-process against the configured database with a simulated clock. Grading uses the
heuristic mock LLM (thousands of calls would take hours on a CPU model); attempts are
therefore recorded with model "heuristic-mock-v2", so simulated data is always identifiable.

    uv run python scripts/simulate_learner.py --days 14 --email demo@banana.local
    docker compose exec api python scripts/simulate_learner.py --days 14
"""

from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime, timedelta

from banana_english.config.container import build_container
from banana_english.config.settings import Settings
from banana_english.domain.interfaces.infra import Clock
from banana_english.domain.models import CefrLevel, Module, SrsRating
from banana_english.infrastructure.ai.mock_llm import HeuristicMockLLMProvider
from banana_english.infrastructure.jobs.runners import InlineJobRunner
from banana_english.infrastructure.stt.mock_stt import MockSTTProvider


class SimClock(Clock):
    def __init__(self, start: datetime) -> None:
        self.t = start

    def now(self) -> datetime:
        return self.t


START_ABILITY = {
    "grammar.past_simple_present_perfect": 0.2,
    "grammar.articles": 0.55,
    "grammar.prepositions_time_place": 0.6,
    "grammar.present_simple_continuous": 0.75,
    "grammar.comparatives_superlatives": 0.7,
    "listening.comprehension": 0.65,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--name", default="Demo Learner")
    parser.add_argument("--level", default="A2")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--email", default="demo@banana.local")
    parser.add_argument("--password", default="banana-demo")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    clock = SimClock(
        datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
        - timedelta(days=args.days)
    )
    c = build_container(
        Settings(),
        llm=HeuristicMockLLMProvider(),
        stt=MockSTTProvider(),
        clock=clock,
        runner=InlineJobRunner(),
    )
    signed_in = c.auth.register(
        args.email, args.password, args.name, CefrLevel(args.level), CefrLevel.B2, "vi"
    )
    lid = signed_in.overview.user.id
    ability = dict(START_ABILITY)

    def practise(skill: str) -> bool:
        p = ability.get(skill, 0.7)
        ok = rng.random() < p
        ability[skill] = min(0.95, p + (0.04 if ok else 0.06))  # we learn most from mistakes
        return ok

    for _day in range(args.days):
        if rng.random() < 0.15:  # a missed day now and then
            clock.t += timedelta(days=1)
            continue
        for _ in range(rng.randint(6, 10)):
            clock.t += timedelta(minutes=rng.randint(1, 6))
            recs, _ = c.recommendations.execute(lid, 5)
            if not recs:
                break
            rec = recs[0] if rng.random() < 0.8 else rng.choice(recs)
            item = rec.items[0]
            if rec.module is Module.VOCABULARY:
                for card in rec.items[:5]:
                    ok = practise(rec.skill_id)
                    rating = rng.choice([SrsRating.GOOD, SrsRating.EASY]) if ok else SrsRating.AGAIN
                    c.vocabulary.review(lid, card.item_id, rating)
            elif rec.module is Module.GRAMMAR:
                ex = c.content.get_exercise(item.item_id)
                answer = ex.accepted_answers[0] if practise(ex.skill_id) else "I no sure"
                c.grammar.execute(lid, ex.id, answer)
            elif rec.module is Module.LISTENING:
                lesson = c.content.get_listening(item.item_id)
                for q in lesson.questions:
                    ok = practise("listening.comprehension")
                    c.listening.execute(lid, q.id, q.accepted_answers[0] if ok else "I don't know")
            elif rec.module is Module.SPEAKING:
                import tempfile
                from pathlib import Path

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(b"RIFF-simulated")
                Path(f.name + ".txt").write_text(
                    "Last weekend I went to the beach with my friends and we swam in the sea."
                )
                c.speaking.submit(lid, item.item_id, Path(f.name).read_bytes(), "a.wav")
            elif rec.module is Module.CONVERSATION:
                conv = c.conversation.start(lid, item.item_id)
                for line in ["Hello, I would like a coffee, please.", "How much is it?"]:
                    conv = c.conversation.send(lid, conv.id, line)
                c.conversation.finish(lid, conv.id)
        clock.t = (clock.t + timedelta(days=1)).replace(hour=8, minute=0)

    views = {v.skill.id: v for v in c.learner.mastery(lid)}
    print(f"learner_id={lid}  sign in with: {args.email} / {args.password}")
    for sid, v in sorted(views.items()):
        if v.mastery.attempt_count:
            print(
                f"  {sid:40s} mastery={v.mastery.mastery:5.1f} attempts={v.mastery.attempt_count}"
            )


if __name__ == "__main__":
    main()
