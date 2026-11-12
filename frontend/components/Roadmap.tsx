"use client";

import Link from "next/link";
import { useState } from "react";
import type { RoadmapLevel, RoadmapResponse } from "@/lib/types";
import { CheckIcon } from "@/components/ui/Icons";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Tag, levelName } from "@/components/ui/Badge";

/** The level the learner is working on: the first one not complete yet. */
export function currentMilestone(road: RoadmapResponse): RoadmapLevel | undefined {
  return road.levels.find((l) => !l.complete) ?? road.levels.at(-1);
}

const weeks = (n: number) => (n <= 1 ? "about 1 week" : `about ${n} weeks`);

/** Weeks from now until `level` is complete: its own and every earlier level's remaining work. */
function weeksUntil(road: RoadmapResponse, level: RoadmapLevel): number {
  const upto = road.levels.slice(0, road.levels.indexOf(level) + 1);
  return Math.ceil(upto.reduce((t, l) => t + l.answers_left, 0) / (road.daily_goal * 7));
}

function levelShare(l: RoadmapLevel): number {
  const parts = l.skills.length + l.words_total;
  return parts ? (100 * (l.skills_mastered + l.words_started)) / parts : 100;
}

/** A1 → A2 → B1 → B2: where the learner stands, what each level needs and how long it takes. */
export function Roadmap({ road }: { road: RoadmapResponse }) {
  const current = currentMilestone(road);
  const [open, setOpen] = useState(current?.level);
  const shown = road.levels.find((l) => l.level === open) ?? current;
  const target = road.levels.find((l) => l.level === road.target_level) ?? road.levels.at(-1);

  return (
    <div className="stack tight">
      <ol className="roadmap" aria-label="Levels">
        {road.levels.map((l) => {
          const state = l.complete ? "done" : l === current ? "current" : "next";
          return (
            <li key={l.level}>
              <button type="button" className="roadmap-step" data-state={state}
                aria-pressed={l.level === shown?.level} onClick={() => setOpen(l.level)}>
                <span className="roadmap-level">
                  {l.complete ? <CheckIcon size={14} /> : null}
                  {l.level}
                </span>
                <span className="roadmap-name">{levelName(l.level)}</span>
                <ProgressBar value={levelShare(l)} label={`${l.level} progress`} size="sm"
                  tone={l.complete ? "good" : "accent"} />
                <span className="xsmall muted">
                  {l.complete
                    ? "Done"
                    : `${l.skills_mastered}/${l.skills.length} skills mastered · ${weeks(Math.max(1, l.weeks_left))} of work`}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {shown && <LevelDetail level={shown} masteredAt={road.mastered_at} />}

      <p className="xsmall muted" style={{ margin: 0 }}>
        {target && !target.complete && (
          <>
            <strong>{road.target_level}</strong> in {weeks(weeksUntil(road, target))} at{" "}
            {road.daily_goal} answers a day.{" "}
          </>
        )}
        A level is done when each of its skills reaches {road.mastered_at}/100 and you have started
        every word on its list. The estimate counts one answer per new word and about four good
        answers per skill; reviews come on top, so treat it as the shortest time.
      </p>
    </div>
  );
}

function LevelDetail({ level: l, masteredAt }: { level: RoadmapLevel; masteredAt: number }) {
  const groups = [
    { status: "in_progress", title: "Practising", tone: "orange" as const },
    { status: "not_started", title: "Not started", tone: "neutral" as const },
    { status: "mastered", title: "Mastered", tone: "good" as const },
  ];
  return (
    <div className="card tinted roadmap-detail">
      <div className="row-between" style={{ marginBottom: 10 }}>
        <strong>
          {l.level} · {levelName(l.level)}
        </strong>
        <span className="small muted">
          Words started {l.words_started.toLocaleString()} / {l.words_total.toLocaleString()} ·{" "}
          <Link href="/practice/vocabulary">Vocabulary</Link>
        </span>
      </div>
      {groups.map((g) => {
        const skills = l.skills.filter((s) => s.status === g.status);
        if (!skills.length) return null;
        return (
          <div key={g.status} className="roadmap-group">
            <span className="xsmall muted roadmap-group-title">{g.title}</span>
            <span className="chip-row">
              {skills.map((s) => (
                <Tag key={s.skill_id} tone={g.tone}
                  title={g.status === "not_started" ? undefined : `Mastery ${Math.round(s.effective_mastery)}/100 (mastered at ${masteredAt})`}>
                  {s.skill_name}
                  {g.status === "in_progress" && <span className="num"> {Math.round(s.effective_mastery)}</span>}
                </Tag>
              ))}
            </span>
          </div>
        );
      })}
    </div>
  );
}
