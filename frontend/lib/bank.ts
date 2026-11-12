/** Question bank (grammar, vocabulary, reading, listening): types, API calls and the pure
 * helpers the practice screen uses. Sets are drawn from a large pool on every request, and
 * every answer is checked by rules on the server (no AI wait). */

import { api, post } from "@/lib/api";
import type { Cefr } from "@/lib/types";

export type BankSkill = "grammar" | "vocabulary" | "reading" | "listening";
export type QType = "mcq" | "true_false" | "error_id" | "fill_blank" | "dictation" | "ordering" | "matching";

export interface BankOption { id: string; text: string }

export interface BankQuestion {
  id: string;
  qtype: QType;
  level: Cefr;
  topic: string;
  point: string;
  difficulty: "easy" | "medium" | "hard";
  instruction: string;
  prompt: string;
  options: BankOption[];
  passage_id: string | null;
  pieces: string[] | null;
  left: BankOption[] | null;
}

export interface BankPassage {
  id: string;
  level: Cefr;
  topic: string;
  title: string;
  text: string | null;
  audio_url: string | null;
  duration_s: number | null;
  source: { id?: string; ref?: string; license?: string };
}

export interface BankSet {
  skill: BankSkill;
  questions: BankQuestion[];
  passages: BankPassage[];
  review_count: number;
}

export interface BankFacets {
  skill: BankSkill;
  total: number;
  levels: Record<string, number>;
  topics: Record<string, number>;
  points: Record<string, number>;
  qtypes: Record<string, number>;
  difficulties: Record<string, number>;
  point_names: Record<string, string>;
}

export interface BankSummary {
  skill: BankSkill;
  pool_size: number;
  questions_seen: number;
  correct_answers: number;
  wrong_answers: number;
  to_review: number;
}

export interface BankAnswer {
  attempt_id: string;
  question_id: string;
  correct: boolean;
  score: number;
  correct_answer: string;
  explanation: string;
  explanation_vi: string;
  detail: Record<string, unknown>;
  mastery: { skill_id: string; before: number; after: number; attempt_count: number };
}

export type AnswerValue = string | string[] | Record<string, string>;

export interface SetFilters {
  levels: Cefr[];
  points: string[];
  topics: string[];
  qtypes: QType[];
  count: number;
}

export const EMPTY_FILTERS: SetFilters = { levels: [], points: [], topics: [], qtypes: [], count: 10 };

export const bankApi = {
  facets: (skill: BankSkill) => api<BankFacets>(`/bank/${skill}/facets`),
  summary: (skill: BankSkill) => api<BankSummary>(`/bank/${skill}/summary`),
  newSet: (skill: BankSkill, f: SetFilters) => post<BankSet>(`/bank/${skill}/sets`, setBody(f)),
  answer: (questionId: string, answer: AnswerValue, responseTimeMs: number) =>
    post<BankAnswer>("/bank/answer", {
      question_id: questionId, answer, response_time_ms: Math.max(0, Math.round(responseTimeMs)),
    }),
  transcript: (passageId: string) =>
    api<{ passage_id: string; title: string; transcript: string }>(
      `/bank/passages/${encodeURIComponent(passageId)}/transcript`),
};

/** The request body: only the filters that are set (the server treats [] as "any"). */
export function setBody(f: SetFilters) {
  const body: Record<string, unknown> = { count: f.count };
  if (f.levels.length) body.levels = f.levels;
  if (f.points.length) body.points = f.points;
  if (f.topics.length) body.topics = f.topics;
  if (f.qtypes.length) body.qtypes = f.qtypes;
  return body;
}

/** A question-bank item id (gr.present_perfect.3f9a0c1b2d4e), not a lesson exercise id. */
export function isBankItem(itemId: string): boolean {
  return /^(gr|vo|rd|ls)\.[a-z_.]+\.[0-9a-f]{12}$/.test(itemId);
}

export const BANK_HREF: Record<BankSkill, string> = {
  grammar: "/practice/grammar?view=sets",
  vocabulary: "/practice/vocabulary?tab=quiz",
  reading: "/practice/reading",
  listening: "/practice/listening?view=sets",
};

/** "[She] [have gone] [to the] [market]." -> the four parts and the end punctuation. */
export function errorParts(prompt: string): { parts: string[]; end: string } | null {
  const parts = [...prompt.matchAll(/\[([^\]]+)\]/g)].map((m) => m[1]);
  if (parts.length < 2) return null;
  const end = prompt.slice(prompt.lastIndexOf("]") + 1).trim();
  return { parts, end };
}

export const QTYPE_LABEL: Record<QType, string> = {
  mcq: "Multiple choice",
  true_false: "True / False",
  error_id: "Find the mistake",
  fill_blank: "Fill in the blank",
  dictation: "Dictation",
  ordering: "Word order",
  matching: "Matching",
};

export const FOCUS_LABEL: Record<string, string> = {
  meaning: "Meaning", definition: "Definition", vietnamese: "Vietnamese meaning",
  synonym: "Synonyms", antonym: "Antonyms", word_form: "Word forms", context: "Words in context",
  collocation: "Collocations", matching: "Matching", main_idea: "Main idea", true_false: "True / False",
  detail: "Details", vocabulary_in_context: "Vocabulary in context", dictation: "Dictation",
  heard_sentence: "Which sentence did you hear?",
};

export const topicLabel = (t: string) => t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export function pointLabel(point: string, names: Record<string, string>): string {
  return names[point] ?? FOCUS_LABEL[point] ?? topicLabel(point);
}

/** Score of a finished set: correct answers and the average score (partial credit counts). */
export function setScore(results: BankAnswer[]): { correct: number; total: number; percent: number } {
  const total = results.length;
  const correct = results.filter((r) => r.correct).length;
  const percent = total ? Math.round(results.reduce((s, r) => s + r.score, 0) / total) : 0;
  return { correct, total, percent };
}
