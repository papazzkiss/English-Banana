"""Loads versioned content from content/ and validates it at startup (fail fast)."""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from banana_english.domain.models import (
    CefrLevel,
    ContentReviewStatus,
    ConversationScenario,
    Difficulty,
    Exercise,
    ExerciseType,
    ListeningLesson,
    ListeningQuestion,
    Module,
    Skill,
    SpeakingPrompt,
    VocabularyItem,
)
from banana_english.domain.models.skills import (
    CONVERSATION_SKILL,
    LISTENING_SKILL,
    SPEAKING_FLUENCY_SKILL,
    SPEAKING_GRAMMAR_SKILL,
)
from banana_english.domain.services.vocabulary_exercises import (
    build_recall_exercise,
    item_id_from_exercise_id,
)


class ContentError(Exception):
    pass


# --- file schemas -------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewRecord(_Strict):
    status: ContentReviewStatus
    authored_by: str
    reviewed_by: str | None
    reviewed_at: str | None
    notes: str | None

    @model_validator(mode="after")
    def _approved_needs_reviewer(self) -> ReviewRecord:
        approved = self.status is ContentReviewStatus.APPROVED
        if approved and not (self.reviewed_by and self.reviewed_at):
            raise ValueError("approved content must record reviewed_by and reviewed_at")
        return self


class VocabularyItemRecord(_Strict):
    id: str
    word: str = Field(min_length=1)
    variants: list[str]
    part_of_speech: Literal["noun", "verb", "adjective", "adverb"]
    cefr_level: CefrLevel
    definition: str = Field(min_length=1)
    example: str | None
    provenance: dict[str, str | int]
    review_status: ContentReviewStatus


class LearnerDefinitionRecord(_Strict):
    definition: str = Field(min_length=1)
    example: str | None = None
    replaces: str = Field(min_length=1)  # the vocabulary.json definition this one rewrites


class LearnerDefinitionsFile(BaseModel):
    """Simple definitions written for beginners, applied on top of vocabulary.json."""

    schema_version: Literal[1]
    items: dict[str, LearnerDefinitionRecord]


def _learner_definitions(path: Path) -> dict[str, LearnerDefinitionRecord]:
    return _load(path, LearnerDefinitionsFile).items if path.exists() else {}


class VocabularyFile(BaseModel):
    schema_version: Literal[1]
    sources: list[dict]
    stats: dict
    items: list[VocabularyItemRecord] = Field(min_length=1)


class GrammarTopicRecord(_Strict):
    skill_id: str = Field(pattern=r"^grammar\.[a-z_]+$")
    name: str
    description: str


class GrammarExerciseRecord(_Strict):
    id: str = Field(pattern=r"^gr\.[a-z]+\.\d{3}$")
    skill_id: str
    cefr_level: CefrLevel
    exercise_type: Literal["fill_in_blank", "error_correction", "sentence_transformation"]
    difficulty: Difficulty
    instruction: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    accepted_answers: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    review: ReviewRecord


class GrammarFile(BaseModel):
    schema_version: Literal[1]
    review_policy: str
    difficulty_policy: str
    topics: list[GrammarTopicRecord] = Field(min_length=1)
    exercises: list[GrammarExerciseRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> GrammarFile:
        ids = [e.id for e in self.exercises]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate grammar exercise ids")
        unknown = {e.skill_id for e in self.exercises} - {t.skill_id for t in self.topics}
        if unknown:
            raise ValueError(f"exercises reference unknown topics: {sorted(unknown)}")
        return self


class ListeningQuestionRecord(_Strict):
    id: str
    question: str = Field(min_length=1)
    accepted_answers: list[str] = Field(min_length=1)


class ListeningLessonRecord(_Strict):
    id: str = Field(pattern=r"^ls\.[a-z]+\.\d{3}$")
    title: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    transcript: str = Field(min_length=20)
    audio_file: str = Field(pattern=r"^[A-Za-z0-9._-]+\.(wav|ogg|mp3)$")
    questions: list[ListeningQuestionRecord] = Field(min_length=1, max_length=5)
    review: ReviewRecord


class ListeningFile(BaseModel):
    schema_version: Literal[1]
    review_policy: str
    voice: str
    lessons: list[ListeningLessonRecord] = Field(min_length=1)


class SpeakingPromptRecord(_Strict):
    id: str = Field(pattern=r"^sp\.[a-z]+\.\d{3}$")
    title: str
    cefr_level: CefrLevel
    difficulty: Difficulty
    instruction: str
    target_grammar: str | None
    min_seconds: int = Field(ge=5)
    max_seconds: int = Field(le=180)
    review: ReviewRecord


class SpeakingFile(BaseModel):
    schema_version: Literal[1]
    review_policy: str
    prompts: list[SpeakingPromptRecord] = Field(min_length=1)


class ScenarioRecord(_Strict):
    id: str = Field(pattern=r"^cv\.[a-z]+\.\d{3}$")
    title: str
    cefr_level: CefrLevel
    assistant_role: str
    learner_role: str
    situation: str
    opening_line: str
    goals: list[str] = Field(min_length=1)
    target_skills: list[str]
    max_learner_turns: int = Field(ge=2, le=10)
    review: ReviewRecord


class ConversationFile(BaseModel):
    schema_version: Literal[1]
    review_policy: str
    scenarios: list[ScenarioRecord] = Field(min_length=1)


class BankSkillRecord(_Strict):
    id: str
    module: Module
    name: str
    description: str
    entry_level: CefrLevel


class BankPointRecord(_Strict):
    skill_id: str
    name: str
    name_vi: str
    level: CefrLevel


class BankSkillsFile(BaseModel):
    """content/bank/skills.json: the question bank's taxonomy (optional)."""

    schema_version: Literal[1]
    note: str = ""
    skills: list[BankSkillRecord]
    grammar_points: dict[str, BankPointRecord]


def _load(path: Path, model: type[BaseModel]):
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ContentError(f"invalid content in {path}: {exc}") from exc


def _wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / w.getframerate(), 2)
    except (OSError, wave.Error) as exc:
        raise ContentError(f"unreadable audio {path}: {exc}") from exc


# --- repository ---------------------------------------------------------------------


class JsonContentRepository:
    """In-memory, read-only ContentRepository backed by the JSON files in content/."""

    def __init__(self, content_dir: Path, *, require_reviewed: bool = False) -> None:
        self.content_dir = content_dir
        self.audio_dir = content_dir / "listening/audio"
        servable = {ContentReviewStatus.APPROVED}
        if not require_reviewed:
            servable.add(ContentReviewStatus.PENDING_REVIEW)
        self.review_counts: dict[str, dict[str, int]] = {}

        def track(kind: str, statuses: list[ContentReviewStatus]) -> None:
            self.review_counts[kind] = {
                s.value: statuses.count(s) for s in ContentReviewStatus if statuses.count(s)
            }

        vocab = _load(content_dir / "vocabulary/vocabulary.json", VocabularyFile)
        grammar = _load(content_dir / "grammar/exercises.json", GrammarFile)
        listening = _load(content_dir / "listening/lessons.json", ListeningFile)
        speaking = _load(content_dir / "speaking/prompts.json", SpeakingFile)
        conversation = _load(content_dir / "conversation/scenarios.json", ConversationFile)

        # vocabulary; a learner definition applies only to the sense it was written for
        simple = _learner_definitions(content_dir / "vocabulary/learner_definitions.json")

        def item(r: VocabularyItemRecord) -> VocabularyItem:
            d = simple.get(r.id)
            if d is not None and d.replaces != r.definition:
                d = None
            return VocabularyItem(
                r.id,
                r.word,
                tuple(r.variants),
                r.part_of_speech,
                r.cefr_level,
                d.definition if d else r.definition,
                (d.example or r.example) if d else r.example,
                r.review_status,
            )

        self._vocab: dict[str, VocabularyItem] = {
            r.id: item(r)
            for r in vocab.items
            if r.review_status is not ContentReviewStatus.REJECTED
        }
        self._vocab_by_skill: dict[str, list[VocabularyItem]] = {}

        # Presentation order for new cards: items with a usable example first, then a stable
        # pseudo-random order (alphabetical order would start every learner on "a.m.", "about").
        def order(i: VocabularyItem) -> tuple[bool, str]:
            return i.example is None, hashlib.sha1(i.id.encode()).hexdigest()

        for item in sorted(self._vocab.values(), key=order):
            self._vocab_by_skill.setdefault(item.skill_id, []).append(item)

        # grammar
        track("grammar", [e.review.status for e in grammar.exercises])
        self._exercises: dict[str, Exercise] = {
            r.id: Exercise(
                id=r.id,
                module=Module.GRAMMAR,
                skill_id=r.skill_id,
                cefr_level=r.cefr_level,
                exercise_type=ExerciseType(r.exercise_type),
                instruction=r.instruction,
                prompt=r.prompt,
                accepted_answers=tuple(r.accepted_answers),
                review_status=r.review.status,
                difficulty=r.difficulty,
                explanation=r.explanation,
            )
            for r in grammar.exercises
            if r.review.status in servable
        }
        self._exercises_by_skill: dict[str, list[Exercise]] = {}
        for ex in sorted(self._exercises.values(), key=lambda e: (e.cefr_level.rank, e.id)):
            self._exercises_by_skill.setdefault(ex.skill_id, []).append(ex)

        # listening
        track("listening", [x.review.status for x in listening.lessons])
        self._listening: dict[str, ListeningLesson] = {}
        for r in listening.lessons:
            if r.review.status not in servable:
                continue
            audio = self.audio_dir / r.audio_file
            if not audio.exists():
                raise ContentError(f"missing audio for {r.id}: {audio}")
            self._listening[r.id] = ListeningLesson(
                id=r.id,
                title=r.title,
                cefr_level=r.cefr_level,
                difficulty=r.difficulty,
                transcript=r.transcript,
                audio_file=r.audio_file,
                duration_seconds=_wav_seconds(audio) if audio.suffix == ".wav" else 0.0,
                questions=tuple(
                    ListeningQuestion(q.id, q.question, tuple(q.accepted_answers))
                    for q in r.questions
                ),
                review_status=r.review.status,
            )
        self._questions = {
            q.id: (lesson, q) for lesson in self._listening.values() for q in lesson.questions
        }

        # speaking
        track("speaking", [x.review.status for x in speaking.prompts])
        self._speaking = {
            r.id: SpeakingPrompt(
                r.id,
                r.title,
                r.cefr_level,
                r.difficulty,
                r.instruction,
                r.target_grammar,
                r.min_seconds,
                r.max_seconds,
                r.review.status,
            )
            for r in speaking.prompts
            if r.review.status in servable
        }

        # conversation
        track("conversation", [x.review.status for x in conversation.scenarios])
        self._scenarios = {
            r.id: ConversationScenario(
                r.id,
                r.title,
                r.cefr_level,
                r.assistant_role,
                r.learner_role,
                r.situation,
                r.opening_line,
                tuple(r.goals),
                tuple(r.target_skills),
                r.max_learner_turns,
                r.review.status,
            )
            for r in conversation.scenarios
            if r.review.status in servable
        }

        self._skills = self._build_skills(grammar)

        # question bank taxonomy: its skills join the content skills (existing ones win)
        bank_file = content_dir / "bank/skills.json"
        self.bank_points: dict[str, BankPointRecord] = {}
        if bank_file.exists() and not require_reviewed:  # bank items are machine-validated
            bank = _load(bank_file, BankSkillsFile)
            self.bank_points = dict(bank.grammar_points)
            for r in bank.skills:
                self._skills.setdefault(
                    r.id, Skill(r.id, r.module, r.name, r.description, r.entry_level)
                )

    def _build_skills(self, grammar: GrammarFile) -> dict[str, Skill]:
        skills: dict[str, Skill] = {}
        for skill_id, items in sorted(self._vocab_by_skill.items()):
            level = items[0].cefr_level
            skills[skill_id] = Skill(
                skill_id,
                Module.VOCABULARY,
                f"Vocabulary {level.value}",
                f"CEFR {level.value} words (CEFR-J Wordlist)",
                level,
            )
        for topic in grammar.topics:
            exercises = self._exercises_by_skill.get(topic.skill_id)
            if exercises:
                skills[topic.skill_id] = Skill(
                    topic.skill_id,
                    Module.GRAMMAR,
                    topic.name,
                    topic.description,
                    exercises[0].cefr_level,
                )
        if self._listening:
            skills[LISTENING_SKILL] = Skill(
                LISTENING_SKILL,
                Module.LISTENING,
                "Listening comprehension",
                "Understanding short recordings",
                min((x.cefr_level for x in self._listening.values()), key=lambda c: c.rank),
            )
        if self._speaking:
            entry = min((x.cefr_level for x in self._speaking.values()), key=lambda c: c.rank)
            skills[SPEAKING_GRAMMAR_SKILL] = Skill(
                SPEAKING_GRAMMAR_SKILL,
                Module.SPEAKING,
                "Spoken grammar",
                "Grammar accuracy in spoken answers (graded from the transcript)",
                entry,
            )
            skills[SPEAKING_FLUENCY_SKILL] = Skill(
                SPEAKING_FLUENCY_SKILL,
                Module.SPEAKING,
                "Speaking fluency",
                "Speech rate, fillers and pauses",
                entry,
            )
        if self._scenarios:
            skills[CONVERSATION_SKILL] = Skill(
                CONVERSATION_SKILL,
                Module.CONVERSATION,
                "Conversation",
                "Grammar accuracy while role-playing everyday situations",
                min((x.cefr_level for x in self._scenarios.values()), key=lambda c: c.rank),
            )
        return skills

    # ContentRepository protocol ---------------------------------------------------

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def get_exercise(self, exercise_id: str) -> Exercise | None:
        item_id = item_id_from_exercise_id(exercise_id)
        if item_id is not None:
            item = self._vocab.get(item_id)
            return build_recall_exercise(item) if item else None
        return self._exercises.get(exercise_id)

    def list_exercises(self, skill_id: str) -> list[Exercise]:
        return list(self._exercises_by_skill.get(skill_id, []))

    def list_all_exercises(self) -> list[Exercise]:
        return list(self._exercises.values())

    def get_vocabulary_item(self, item_id: str) -> VocabularyItem | None:
        return self._vocab.get(item_id)

    def list_vocabulary(self, skill_id: str) -> list[VocabularyItem]:
        return list(self._vocab_by_skill.get(skill_id, []))

    def list_listening(self) -> list[ListeningLesson]:
        return sorted(self._listening.values(), key=lambda x: (x.cefr_level.rank, x.id))

    def get_listening(self, lesson_id: str) -> ListeningLesson | None:
        return self._listening.get(lesson_id)

    def get_listening_question(
        self, question_id: str
    ) -> tuple[ListeningLesson, ListeningQuestion] | None:
        return self._questions.get(question_id)

    def list_speaking(self) -> list[SpeakingPrompt]:
        return sorted(self._speaking.values(), key=lambda x: (x.cefr_level.rank, x.id))

    def get_speaking(self, prompt_id: str) -> SpeakingPrompt | None:
        return self._speaking.get(prompt_id)

    def list_scenarios(self) -> list[ConversationScenario]:
        return sorted(self._scenarios.values(), key=lambda x: (x.cefr_level.rank, x.id))

    def get_scenario(self, scenario_id: str) -> ConversationScenario | None:
        return self._scenarios.get(scenario_id)
