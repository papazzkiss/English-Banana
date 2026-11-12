"""Composition root: the only module that wires concrete implementations to interfaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from banana_english.application.services.conversation import ConversationPartner
from banana_english.application.services.grammar_assessment import LLMGrammarAssessmentEngine
from banana_english.application.services.listening_assessment import ListeningAssessmentEngine
from banana_english.application.services.monkey import MonkeyChat
from banana_english.application.services.recommendation_engine import (
    RuleBasedRecommendationEngine,
)
from banana_english.application.services.speaking_assessment import SpeakingAssessor
from banana_english.application.services.structured_llm import StructuredLLM
from banana_english.application.services.tutor import Tutor
from banana_english.application.use_cases.admin import UserAdministration
from banana_english.application.use_cases.attempts import (
    AttemptRecorder,
    SubmitGrammarAttempt,
    SubmitListeningAttempt,
)
from banana_english.application.use_cases.auth import Auth
from banana_english.application.use_cases.conversation import ConversationPractice
from banana_english.application.use_cases.jobs import BackgroundAttempts, JobStore
from banana_english.application.use_cases.learner import LearnerQueries
from banana_english.application.use_cases.monkey import (
    MonkeyConversation,
    MonkeyTranscriber,
    MonkeyVoice,
)
from banana_english.application.use_cases.question_bank import QuestionBankPractice
from banana_english.application.use_cases.recommendations import GetRecommendations
from banana_english.application.use_cases.speaking import SpeakingPractice
from banana_english.application.use_cases.teacher import TeacherScope
from banana_english.application.use_cases.tutor import ExplainMistake
from banana_english.application.use_cases.vocabulary import VocabularyReview
from banana_english.config.settings import Settings
from banana_english.domain.interfaces.infra import Cache, Clock, JobRunner, SystemClock
from banana_english.domain.interfaces.llm import LLMProvider
from banana_english.domain.interfaces.stt import STTProvider
from banana_english.domain.interfaces.tts import TTSProvider
from banana_english.infrastructure.ai.factory import (
    build_llm_provider,
    build_stt_provider,
    build_tts_provider,
)
from banana_english.infrastructure.ai.instrumented import InstrumentedLLMProvider
from banana_english.infrastructure.cache.caches import MemoryCache, RedisCache
from banana_english.infrastructure.content.json_content_repository import JsonContentRepository
from banana_english.infrastructure.database.repositories import (
    SqlLLMCallLog,
    SqlUnitOfWork,
    create_db_engine,
)
from banana_english.infrastructure.jobs.runners import ThreadPoolJobRunner
from banana_english.infrastructure.stt.instrumented import InstrumentedSTTProvider
from banana_english.infrastructure.tts.instrumented import InstrumentedTTSProvider


@dataclass
class Container:
    settings: Settings
    content: JsonContentRepository
    llm: LLMProvider
    stt: STTProvider
    tts: TTSProvider
    cache: Cache
    runner: JobRunner
    llm_calls: SqlLLMCallLog
    grammar_engine: LLMGrammarAssessmentEngine
    auth: Auth
    learner: LearnerQueries
    recommendations: GetRecommendations
    vocabulary: VocabularyReview
    grammar: SubmitGrammarAttempt
    listening: SubmitListeningAttempt
    speaking: SpeakingPractice
    conversation: ConversationPractice
    tutor: ExplainMistake
    jobs: JobStore
    background: BackgroundAttempts
    monkey: MonkeyConversation
    monkey_ears: MonkeyTranscriber
    monkey_voice: MonkeyVoice
    bank: QuestionBankPractice
    admin: UserAdministration
    teacher: TeacherScope
    uow_factory: Callable[[], SqlUnitOfWork]  # server-side tools (manage CLI, tests)


def build_container(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    stt: STTProvider | None = None,
    tts: TTSProvider | None = None,
    clock: Clock | None = None,
    content: JsonContentRepository | None = None,
    runner: JobRunner | None = None,
    cache: Cache | None = None,
) -> Container:
    settings = settings or Settings()
    clock = clock or SystemClock()
    content = content or JsonContentRepository(
        settings.content_dir, require_reviewed=settings.require_reviewed_content
    )
    session_factory = sessionmaker(create_db_engine(settings.database_url), expire_on_commit=False)
    llm_calls = SqlLLMCallLog(session_factory)
    llm = InstrumentedLLMProvider(
        llm or build_llm_provider(settings), llm_calls, settings.llm_cost_per_1k_tokens
    )
    stt = InstrumentedSTTProvider(stt or build_stt_provider(settings))
    tts = InstrumentedTTSProvider(tts or build_tts_provider(settings))
    cache = cache or (RedisCache(settings.redis_url) if settings.redis_url else MemoryCache())
    runner = runner or ThreadPoolJobRunner(settings.job_workers)

    def uow_factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    structured = StructuredLLM(llm, cache, settings.llm_max_retries)
    grammar_engine = LLMGrammarAssessmentEngine(structured)
    recommendations = GetRecommendations(
        uow_factory, RuleBasedRecommendationEngine(content), clock, settings.daily_new_cards
    )
    recorder = AttemptRecorder(uow_factory, clock, recommendations)
    jobs = JobStore(uow_factory, clock)
    return Container(
        settings=settings,
        content=content,
        llm=llm,
        stt=stt,
        tts=tts,
        cache=cache,
        runner=runner,
        llm_calls=llm_calls,
        grammar_engine=grammar_engine,
        auth=Auth(uow_factory, clock, settings.session_days),
        learner=LearnerQueries(uow_factory, content, clock),
        recommendations=recommendations,
        vocabulary=VocabularyReview(
            uow_factory, content, clock, recommendations, settings.daily_new_cards
        ),
        grammar=SubmitGrammarAttempt(recorder, content, grammar_engine),
        listening=SubmitListeningAttempt(recorder, content, ListeningAssessmentEngine(structured)),
        speaking=SpeakingPractice(
            uow_factory,
            content,
            SpeakingAssessor(stt, grammar_engine),
            jobs,
            runner,
            clock,
            recommendations,
            settings.upload_dir,
            settings.max_upload_mb * 1024 * 1024,
        ),
        conversation=ConversationPractice(
            uow_factory,
            content,
            ConversationPartner(llm, settings.llm_max_retries),
            grammar_engine,
            jobs,
            runner,
            clock,
        ),
        tutor=ExplainMistake(uow_factory, Tutor(structured), content),
        jobs=jobs,
        background=BackgroundAttempts(jobs, runner),
        monkey=MonkeyConversation(uow_factory, MonkeyChat(llm, settings.llm_max_retries)),
        monkey_voice=MonkeyVoice(tts),
        bank=QuestionBankPractice(
            uow_factory, clock, approved_only=settings.require_reviewed_content
        ),
        monkey_ears=MonkeyTranscriber(
            stt, settings.upload_dir, settings.max_upload_mb * 1024 * 1024
        ),
        admin=UserAdministration(uow_factory, clock),
        teacher=TeacherScope(uow_factory),
        uow_factory=uow_factory,
    )
