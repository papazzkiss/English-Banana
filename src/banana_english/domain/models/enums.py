from __future__ import annotations

from enum import StrEnum


class CefrLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

    @property
    def rank(self) -> int:
        return list(CefrLevel).index(self)

    def next(self) -> CefrLevel | None:
        levels = list(CefrLevel)
        return levels[self.rank + 1] if self.rank + 1 < len(levels) else None


class Role(StrEnum):
    """What an account may do. Stored on the user; never taken from a request."""

    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class Module(StrEnum):
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"
    LISTENING = "listening"
    SPEAKING = "speaking"
    CONVERSATION = "conversation"
    READING = "reading"  # question bank only (passages + questions)


class ExerciseType(StrEnum):
    VOCABULARY_RECALL = "vocabulary_recall"
    FILL_IN_BLANK = "fill_in_blank"
    ERROR_CORRECTION = "error_correction"
    SENTENCE_TRANSFORMATION = "sentence_transformation"
    LISTENING_QUESTION = "listening_question"
    SPEAKING_PROMPT = "speaking_prompt"
    CONVERSATION_TURN = "conversation_turn"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ContentReviewStatus(StrEnum):
    AUTO_MAPPED = "auto_mapped"  # machine-joined from real sources, not yet human-checked
    PENDING_REVIEW = "pending_review"  # AI-generated candidate
    APPROVED = "approved"  # human-reviewed, official content
    REJECTED = "rejected"


class AttemptStatus(StrEnum):
    ASSESSED = "assessed"
    ASSESSMENT_FAILED = "assessment_failed"


class Assessor(StrEnum):
    DETERMINISTIC = "deterministic"  # rules: vocabulary, fluency, empty answers
    REFERENCE_MATCH = "reference_match"  # equals a reviewed reference answer
    LLM = "llm"
    SELF_RATED = "self_rated"  # SM-2 flashcard rating by the learner


class MistakeCategory(StrEnum):
    # vocabulary
    SPELLING = "spelling"
    WRONG_WORD = "wrong_word"
    NO_ANSWER = "no_answer"
    # grammar
    VERB_TENSE = "verb_tense"
    VERB_FORM = "verb_form"
    SUBJECT_VERB_AGREEMENT = "subject_verb_agreement"
    ARTICLE = "article"
    PREPOSITION = "preposition"
    COMPARATIVE_FORM = "comparative_form"
    CONDITIONAL_STRUCTURE = "conditional_structure"
    WORD_ORDER = "word_order"
    WORD_CHOICE = "word_choice"
    INCOMPLETE_ANSWER = "incomplete_answer"
    # listening / speaking
    COMPREHENSION = "comprehension"
    FLUENCY = "fluency"
    OTHER = "other"


GRAMMAR_MISTAKE_CATEGORIES: frozenset[MistakeCategory] = frozenset(
    {
        MistakeCategory.VERB_TENSE,
        MistakeCategory.VERB_FORM,
        MistakeCategory.SUBJECT_VERB_AGREEMENT,
        MistakeCategory.ARTICLE,
        MistakeCategory.PREPOSITION,
        MistakeCategory.COMPARATIVE_FORM,
        MistakeCategory.CONDITIONAL_STRUCTURE,
        MistakeCategory.WORD_ORDER,
        MistakeCategory.WORD_CHOICE,
        MistakeCategory.SPELLING,
        MistakeCategory.INCOMPLETE_ANSWER,
        MistakeCategory.OTHER,
    }
)


class SrsRating(StrEnum):
    """Anki-style buttons; mapped to SM-2 quality 1/3/4/5."""

    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"

    @property
    def quality(self) -> int:
        return {"again": 1, "hard": 3, "good": 4, "easy": 5}[self.value]


class RecommendationKind(StrEnum):
    REVIEW = "review"  # spaced-repetition cards are due
    REINFORCEMENT = "reinforcement"  # weak skill (mastery < WEAKNESS_THRESHOLD)
    NEW_TOPIC = "new_topic"  # cold start / default mix: a skill not practised yet
    PRACTICE = "practice"  # default mix: keep a non-weak skill fresh


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    FINISHING = "finishing"
    FINISHED = "finished"
