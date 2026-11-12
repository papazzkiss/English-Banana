"""Turn a VocabularyItem into a deterministic recall exercise."""

from __future__ import annotations

import re

from banana_english.domain.models import Exercise, ExerciseType, Module, VocabularyItem

EXERCISE_PREFIX = "vocab."
BLANK = "_____"


def exercise_id_for(item_id: str) -> str:
    return f"{EXERCISE_PREFIX}{item_id}"


def item_id_from_exercise_id(exercise_id: str) -> str | None:
    return (
        exercise_id.removeprefix(EXERCISE_PREFIX)
        if exercise_id.startswith(EXERCISE_PREFIX)
        else None
    )


def _blank_out(sentence: str, forms: tuple[str, ...]) -> str:
    for form in sorted(forms, key=len, reverse=True):
        sentence = re.sub(
            rf"(?<![\w-]){re.escape(form)}(?![\w-])", BLANK, sentence, flags=re.IGNORECASE
        )
    return sentence


def build_recall_exercise(item: VocabularyItem) -> Exercise:
    forms = (item.word, *item.variants)
    lines = [item.definition]  # the part of speech is shown separately on the card
    if item.example:
        lines.append(f"Example: {_blank_out(item.example, forms)}")
    word_count = len(item.word.split())
    hint = (
        f"Starts with '{item.word[0]}', {len(item.word)} letters"
        if word_count == 1
        else f"Starts with '{item.word[0]}', {word_count} words"
    )
    return Exercise(
        id=exercise_id_for(item.id),
        module=Module.VOCABULARY,
        skill_id=item.skill_id,
        cefr_level=item.cefr_level,
        exercise_type=ExerciseType.VOCABULARY_RECALL,
        instruction="Type the English word that matches the definition.",
        prompt="\n".join(lines),
        accepted_answers=forms,
        review_status=item.review_status,
        hint=hint,
        item_id=item.id,
    )
