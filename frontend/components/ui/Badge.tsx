import type { ReactNode } from "react";
import type { Cefr, Difficulty, Module } from "@/lib/types";
import { MODULE, type Tone } from "@/lib/modules";

const LEVEL_NAMES: Record<Cefr, string> = {
  A1: "Beginner",
  A2: "Elementary",
  B1: "Intermediate",
  B2: "Upper-intermediate",
  C1: "Advanced",
  C2: "Proficient",
};

/** A small rounded label. `tone` picks one of the shared colour families. */
export function Tag({
  children,
  tone = "neutral",
  title,
  className = "",
}: {
  children: ReactNode;
  tone?: Tone | "good" | "warn" | "bad";
  title?: string;
  className?: string;
}) {
  return (
    <span className={`chip tone-${tone} ${className}`} title={title}>
      {children}
    </span>
  );
}

export function CefrBadge({ level, showLabel = false }: { level: Cefr; showLabel?: boolean }) {
  return (
    <Tag tone="accent" title={`CEFR ${level}: ${LEVEL_NAMES[level]}`} className="cefr">
      {level}
      {showLabel && <span className="chip-soft">{LEVEL_NAMES[level]}</span>}
    </Tag>
  );
}

export const levelName = (level: Cefr) => LEVEL_NAMES[level];

const DIFFICULTY: Record<Difficulty, { label: string; tone: "good" | "warn" | "bad" }> = {
  easy: { label: "Easy", tone: "good" },
  medium: { label: "Medium", tone: "warn" },
  hard: { label: "Hard", tone: "bad" },
};

export function DifficultyBadge({ difficulty }: { difficulty: Difficulty | null }) {
  if (!difficulty) return null;
  const d = DIFFICULTY[difficulty];
  return <Tag tone={d.tone}>{d.label}</Tag>;
}

export function ModuleBadge({ module }: { module: Module }) {
  const m = MODULE[module];
  return (
    <Tag tone={m.tone}>
      {m.icon(13)}
      {m.label}
    </Tag>
  );
}
