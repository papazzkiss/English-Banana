// Mirrors docs/openapi.json (the FastAPI schemas are the source of truth).

export type Module = "vocabulary" | "grammar" | "listening" | "speaking" | "conversation" | "reading";
export type Difficulty = "easy" | "medium" | "hard";
export type Cefr = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";
export type Rating = "again" | "hard" | "good" | "easy";

export interface LearnerProfile {
  learner_id: string;
  display_name: string;
  current_level: Cefr;
  target_level: Cefr;
  native_language: string | null;
  created_at: string;
  total_attempts: number;
  correct_attempts: number;
  /** Decides which screens to show; the API enforces it on every request anyway. */
  role: Role;
}

export type Role = "admin" | "teacher" | "student";

export interface SkillMastery {
  skill_id: string;
  module: Module;
  skill_name: string;
  mastery: number;
  effective_mastery: number;
  confidence: number;
  attempt_count: number;
  correct_count: number;
  last_practiced_at: string | null;
  is_weak: boolean;
  /** CEFR level at which the skill is introduced. */
  entry_level: Cefr;
}

export interface MasteryResponse {
  learner_id: string;
  weakness_threshold: number;
  skills: SkillMastery[];
}

export interface RecentAttempt {
  attempt_id: string;
  module: Module;
  item_id: string;
  skill_id: string;
  answer: string;
  submitted_at: string;
  status: string;
  score: number | null;
  is_correct: boolean | null;
  mistake_count: number;
  /** Scores of every skill graded from this one answer (a spoken answer: grammar + fluency). */
  parts: { skill_id: string; score: number }[];
}

export interface WeakSkillsResponse {
  learner_id: string;
  weakness_threshold: number;
  skills: WeakSkill[];
}

export interface WeakSkill {
  skill_id: string;
  skill_name: string;
  module: Module;
  mastery: number;
  effective_mastery: number;
  attempt_count: number;
}

export interface MasteryPoint {
  at: string;
  skill_id: string;
  mastery: number;
  score: number;
  source: string;
}

export interface RoadmapLevel {
  level: Cefr;
  skills: { skill_id: string; skill_name: string; module: Module; effective_mastery: number;
            status: "mastered" | "in_progress" | "not_started" }[];
  skills_mastered: number;
  words_total: number;
  words_started: number;
  /** Estimate (lower bound) of answers still needed, and that many answers at the daily goal. */
  answers_left: number;
  weeks_left: number;
  complete: boolean;
}

export interface RoadmapResponse {
  current_level: Cefr;
  target_level: Cefr;
  daily_goal: number;
  mastered_at: number;
  levels: RoadmapLevel[];
}

export interface ActivityResponse {
  days: { date: string; attempts: number }[];
  active_days: number;
  current_streak: number;
}

export interface ActivityItem {
  module: Module;
  item_id: string;
  title: string;
  difficulty: Difficulty | null;
}

export interface Recommendation {
  priority: number;
  kind: "review" | "reinforcement" | "new_topic" | "practice";
  module: Module;
  skill_id: string;
  reason_code: string;
  reason: string;
  evidence: Record<string, unknown>;
  items: ActivityItem[];
}

export interface Mistake {
  category: string;
  explanation: string;
  fragment: string | null;
  correction: string | null;
}

export interface Assessment {
  score: number;
  is_correct: boolean;
  band: string;
  feedback: string;
  mistakes: Mistake[];
  corrected_answer: string | null;
  assessor: string;
  prompt_version: string | null;
  model: string | null;
}

export interface MasteryChange {
  skill_id: string;
  before: number;
  after: number;
  attempt_count: number;
}

export interface AttemptResponse {
  attempt_id: string;
  item_id: string;
  skill_id: string;
  submitted_at: string;
  assessment: Assessment;
  reference_answers: string[];
  explanation: string | null;
  mastery_changes: MasteryChange[];
  next_recommendation: Recommendation | null;
}

export interface Exercise {
  id: string;
  module: Module;
  skill_id: string;
  cefr_level: Cefr;
  difficulty: Difficulty;
  exercise_type: string;
  instruction: string;
  prompt: string;
  hint: string | null;
}

export interface CardState {
  repetitions: number;
  ease_factor: number;
  interval_days: number;
  due_date: string | null;
  lapses: number;
  review_count: number;
}

export interface DueCard {
  card_id: string;
  is_new: boolean;
  cefr_level: Cefr;
  front: Exercise;
  back: { word: string; variants: string[]; part_of_speech: string; definition: string;
          example: string | null };
  state: CardState | null;
}

export interface ReviewResponse {
  attempt_id: string;
  card_id: string;
  rating_applied: Rating;
  assessment: Assessment;
  state: CardState;
  mastery_changes: MasteryChange[];
  next_recommendation: Recommendation | null;
}

export interface GrammarTopic {
  skill_id: string;
  name: string;
  description: string;
  exercise_count: number;
}

export interface ListeningLesson {
  id: string;
  title: string;
  cefr_level: Cefr;
  difficulty: Difficulty;
  duration_seconds: number;
  audio_url: string;
  questions: { id: string; question: string }[];
}

export interface SpeakingPrompt {
  id: string;
  title: string;
  cefr_level: Cefr;
  difficulty: Difficulty;
  instruction: string;
  target_grammar: string | null;
  target_grammar_name: string | null;
  min_seconds: number;
  max_seconds: number;
}

export interface Scenario {
  id: string;
  title: string;
  cefr_level: Cefr;
  situation: string;
  learner_role: string;
  goals: string[];
  max_learner_turns: number;
}

export interface Conversation {
  id: string;
  scenario: Scenario;
  status: "active" | "finishing" | "finished";
  turns: { role: "assistant" | "learner"; text: string; at: string }[];
  learner_turns_left: number;
  summary: ConversationSummary | null;
}

export interface ConversationSummary {
  turns: { text: string; attempt_id: string; assessment: Assessment | null }[];
  average_score: number | null;
  error_counts: Record<string, number>;
  ungraded_turns: number;
  mastery_changes: MasteryChange[];
}

export interface Job<T = Record<string, unknown>> {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  result: T | null;
  error: string | null;
}

export interface SpeakingResult {
  attempt_id: string;
  transcript: string;
  duration_seconds: number;
  stt_model: string;
  grammar: Assessment;
  fluency: { words_per_minute: number; filler_count: number; long_pauses: number;
             score: number; word_count: number; assessment: Assessment };
  mastery_changes: MasteryChange[];
}
