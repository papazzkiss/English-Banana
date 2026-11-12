import type { ReactNode } from "react";
import type { Module } from "@/lib/types";
import {
  BookOpenIcon,
  ConversationIcon,
  GrammarIcon,
  ListeningIcon,
  SpeakingIcon,
  VocabIcon,
} from "@/components/ui/Icons";

/** Colour family of a module: used by icon tiles and badges so each module is recognisable. */
export type Tone = "accent" | "blue" | "green" | "orange" | "violet" | "neutral";

export interface ModuleInfo {
  id: Module;
  label: string;
  href: string;
  tone: Tone;
  /** One line under the module name on the Practice hub. */
  blurb: string;
  icon: (size?: number) => ReactNode;
}

/** The learning modules, in the order they appear everywhere in the app. */
export const MODULES: ModuleInfo[] = [
  {
    id: "vocabulary",
    label: "Vocabulary",
    href: "/practice/vocabulary",
    tone: "accent",
    blurb: "Flashcards that come back just before you would forget them.",
    icon: (s = 20) => <VocabIcon size={s} />,
  },
  {
    id: "grammar",
    label: "Grammar",
    href: "/practice/grammar",
    tone: "violet",
    blurb: "Short lessons with rules and examples, then graded exercises.",
    icon: (s = 20) => <GrammarIcon size={s} />,
  },
  {
    id: "listening",
    label: "Listening",
    href: "/practice/listening",
    tone: "blue",
    blurb: "Everyday audio clips with questions to check you understood.",
    icon: (s = 20) => <ListeningIcon size={s} />,
  },
  {
    id: "reading",
    label: "Reading",
    href: "/practice/reading",
    tone: "neutral",
    blurb: "Short texts from everyday life to Wikipedia, with questions checked instantly.",
    icon: (s = 20) => <BookOpenIcon size={s} />,
  },
  {
    id: "speaking",
    label: "Speaking",
    href: "/practice/speaking",
    tone: "orange",
    blurb: "Answer a prompt out loud and get feedback on grammar and fluency.",
    icon: (s = 20) => <SpeakingIcon size={s} />,
  },
  {
    id: "conversation",
    label: "Conversation",
    href: "/practice/conversation",
    tone: "green",
    blurb: "Role-play real situations and get a report on every turn.",
    icon: (s = 20) => <ConversationIcon size={s} />,
  },
];

export const MODULE: Record<Module, ModuleInfo> = Object.fromEntries(
  MODULES.map((m) => [m.id, m])
) as Record<Module, ModuleInfo>;

/** Mastery bands used in every place a 0–100 mastery is shown. */
export function masteryBand(value: number | null, threshold = 60) {
  if (value === null) return { label: "Not started", tone: "neutral" as Tone };
  if (value >= 80) return { label: "Mastered", tone: "green" as Tone };
  if (value >= threshold) return { label: "Getting there", tone: "blue" as Tone };
  return { label: "Needs practice", tone: "orange" as Tone };
}
