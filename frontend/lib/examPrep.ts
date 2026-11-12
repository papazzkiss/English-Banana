import type { Cefr, Module } from "@/lib/types";
import type { Tone } from "@/lib/modules";

/** Exam Prep: exam tracks that send the learner to STUDY4 for real mock tests.
 *
 * Only navigation links: nothing from STUDY4 is fetched, copied or stored. The descriptions
 * below are Banana English's own summaries of the public exam formats. STUDY4 is an independent
 * website, not a partner. */

export const STUDY4_ORIGIN = "https://study4.com";

/** STUDY4's library of full mock tests (the "want real exam papers?" card). */
export const STUDY4_TEST_LIBRARY = `${STUDY4_ORIGIN}/tests/`;

export type ExamTrackId = "ielts" | "toeic" | "basic";

export interface ExamTrack {
  id: ExamTrackId;
  name: string;
  subtitle: string;
  tone: Tone;
  blurb: string;
  /** Skills the exam (or course) covers, in the order the learner meets them. */
  skills: string[];
  /** Two or three short facts about the format, shown as a spec line. */
  facts: string[];
  /** Banana English modules that build the same skills, for practice before a mock test. */
  practiseHere: Module[];
  /** Where the "Practise on STUDY4" button goes (opens in a new tab). */
  url: string;
  /** What the STUDY4 page is, for the link's accessible name. */
  destination: string;
}

export const EXAM_TRACKS: ExamTrack[] = [
  {
    id: "ielts",
    name: "IELTS",
    subtitle: "Academic & General Training",
    tone: "blue",
    blurb:
      "The four-skill test for studying, working or settling abroad. Every skill gets a band from 0 to 9.",
    skills: ["Listening", "Reading", "Writing", "Speaking"],
    facts: ["4 skills", "About 2 h 45 min", "Band 0–9"],
    practiseHere: ["listening", "speaking", "conversation"],
    url: `${STUDY4_ORIGIN}/tests/ielts/`,
    destination: "IELTS mock tests on STUDY4",
  },
  {
    id: "toeic",
    name: "TOEIC",
    subtitle: "Listening & Reading",
    tone: "green",
    blurb:
      "English for the workplace, often required by employers and universities. Scored from 10 to 990.",
    skills: ["Listening", "Reading", "Vocabulary", "Grammar"],
    facts: ["200 questions", "2 hours", "Score 10–990"],
    practiseHere: ["listening", "vocabulary", "grammar"],
    url: `${STUDY4_ORIGIN}/tests/toeic/`,
    destination: "TOEIC mock tests on STUDY4",
  },
  {
    id: "basic",
    name: "Basic English",
    subtitle: "Foundations before an exam",
    tone: "orange",
    blurb:
      "Get the basics solid first: everyday words, core grammar and simple conversations, at your own pace.",
    skills: ["Vocabulary", "Grammar", "Listening", "Speaking"],
    facts: ["A1–A2", "Self-paced course"],
    practiseHere: ["vocabulary", "grammar", "conversation"],
    url: `${STUDY4_ORIGIN}/courses/online/general-english/`,
    destination: "the basic English course on STUDY4",
  },
];

/** Tracks that fit a learner's current level: foundations below B1, exams from B1 up. */
export function suggestedTracks(level: Cefr | null | undefined): ExamTrackId[] {
  if (!level) return [];
  return level === "A1" || level === "A2" ? ["basic"] : ["ielts", "toeic"];
}

/** Attributes for every link to STUDY4: a new tab, no access to this window, no referrer. */
export const EXTERNAL_LINK = { target: "_blank", rel: "noopener noreferrer" } as const;
