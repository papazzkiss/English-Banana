"use client";

import Link from "next/link";
import { useState } from "react";
import { MODULE_HREF, post, skillLabel } from "@/lib/api";
import { MODULE } from "@/lib/modules";
import type { Assessment, MasteryChange, Recommendation } from "@/lib/types";
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckIcon,
  LightbulbIcon,
  SparklesIcon,
  TrendingUpIcon,
} from "./ui/Icons";
import { IconTile, Spinner } from "./ui/Panel";
import { Tag } from "./ui/Badge";

const BAND_LABEL: Record<string, string> = {
  excellent: "Excellent",
  good: "Good",
  minor_error: "Small mistake",
  major_error: "Needs work",
};

/** The graded answer: verdict, score, what was wrong, the corrected answer and the rule. */
export function AssessmentView({
  assessment,
  attemptId,
  referenceAnswers,
  explanation,
}: {
  assessment: Assessment;
  attemptId?: string;
  referenceAnswers?: string[];
  explanation?: string | null;
}) {
  const ok = assessment.is_correct;
  const verdict = assessment.score >= 90 ? "Excellent!" : ok ? "Correct" : "Not quite";
  const corrected = assessment.corrected_answer;
  const showCorrected = corrected && !assessment.feedback.includes(corrected);
  const reference = referenceAnswers?.[0];
  const showReference =
    reference && !ok && reference !== corrected && !assessment.feedback.includes(reference);

  return (
    <div className={`assessment ${ok ? "good" : "bad"}`} role="status">
      <div className="assessment-head">
        <span className="verdict">
          <span className="verdict-icon" aria-hidden>
            {ok ? <CheckIcon size={16} /> : <AlertCircleIcon size={16} />}
          </span>
          {verdict}
        </span>
        <Tag tone={ok ? "good" : "bad"} className="score-pill" title={`Graded by ${assessment.assessor.replace("_", " ")}`}>
          {Math.round(assessment.score)}/100 · {BAND_LABEL[assessment.band] ?? assessment.band}
        </Tag>
      </div>

      <p className="assessment-feedback">{assessment.feedback}</p>

      {assessment.mistakes.length > 0 && (
        <div className="assessment-section">
          <h4>What to fix</h4>
          {assessment.mistakes.map((m, i) => (
            <div key={i} className="mistake">
              <div className="mistake-line">
                <Tag>{m.category.replace(/_/g, " ")}</Tag>
                {m.fragment && <span className="strike">{m.fragment}</span>}
                {m.correction && (
                  <>
                    <ArrowRightIcon size={14} className="muted" />
                    <span className="fix">{m.correction}</span>
                  </>
                )}
              </div>
              <div className="small secondary">{m.explanation}</div>
              {attemptId && <TutorButton attemptId={attemptId} index={i} />}
            </div>
          ))}
        </div>
      )}

      {(showCorrected || showReference || explanation) && (
        <div className="assessment-section">
          {showCorrected && (
            <div className="answer-line">
              <span className="muted small">Better answer</span>
              <strong>{corrected}</strong>
            </div>
          )}
          {showReference && (
            <div className="answer-line">
              <span className="muted small">Model answer</span>
              <span>{reference}</span>
            </div>
          )}
          {explanation && (
            <div className="answer-line">
              <LightbulbIcon size={15} className="muted" />
              <span>
                <strong>Rule: </strong>
                {explanation}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** "Why is this wrong?": asks the AI tutor to explain one mistake, on demand. */
export function TutorButton({ attemptId, index }: { attemptId: string; index: number }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [text, setText] = useState<{ explanation: string; example: string } | null>(null);
  const [error, setError] = useState("");

  async function ask() {
    setState("loading");
    try {
      setText(await post("/tutor/explain", { attempt_id: attemptId, mistake_index: index }));
      setState("done");
    } catch (e) {
      setError((e as Error).message);
      setState("error");
    }
  }

  if (state === "done" && text) {
    return (
      <div className="tutor">
        <strong className="row" style={{ gap: 6, marginBottom: 4 }}>
          <LightbulbIcon size={15} /> Tutor
        </strong>
        <p style={{ margin: "0 0 6px" }}>{text.explanation}</p>
        <p className="small secondary" style={{ margin: 0 }}>
          Example: <em>{text.example}</em>
        </p>
      </div>
    );
  }

  return (
    <div className="row mt-8">
      <button type="button" className="btn small ghost" onClick={ask} disabled={state === "loading"}>
        {state === "loading" ? <Spinner size={13} /> : <LightbulbIcon size={14} />}
        {state === "loading" ? "Asking the tutor…" : "Why is this wrong?"}
      </button>
      {state === "error" && (
        <span className="small" style={{ color: "var(--critical-text)" }}>
          {error}
        </span>
      )}
    </div>
  );
}

/** How the answer moved each skill's mastery. */
export function MasteryChanges({ changes }: { changes: MasteryChange[] }) {
  if (!changes || changes.length === 0) return null;
  return (
    <div className="mastery-changes" aria-label="Mastery changes">
      {changes.map((c) => {
        const up = c.after >= c.before;
        const diff = c.after - c.before;
        return (
          <Tag key={c.skill_id} tone={up ? "good" : "bad"} title={c.skill_id}>
            <TrendingUpIcon size={13} style={up ? undefined : { transform: "scaleY(-1)" }} />
            {skillLabel(c.skill_id)} {c.before.toFixed(0)} → {c.after.toFixed(0)}
            <span className="num">({up ? "+" : ""}{diff.toFixed(1)})</span>
          </Tag>
        );
      })}
    </div>
  );
}

export const KIND_LABEL: Record<Recommendation["kind"], string> = {
  reinforcement: "Weak skill",
  review: "Review due",
  new_topic: "New topic",
  practice: "Keep fresh",
};

export const KIND_TONE: Record<Recommendation["kind"], "bad" | "warn" | "blue" | "good"> = {
  reinforcement: "bad",
  review: "warn",
  new_topic: "blue",
  practice: "good",
};

/** Where a recommendation leads: the review queue for vocabulary, else its first item. */
export function recommendationHref(rec: Recommendation): string {
  const first = rec.items[0];
  if (rec.module === "vocabulary" || !first) return MODULE[rec.module].href;
  return MODULE_HREF[first.module](first.item_id);
}

/** Skill id -> display name (from /learner/mastery); falls back to a label built from the id. */
export type SkillNames = Record<string, string>;
const nameOf = (id: string, names?: SkillNames) => names?.[id] ?? skillLabel(id);

export function recommendationTitle(rec: Recommendation, names?: SkillNames): string {
  if (rec.module === "vocabulary") {
    // word_count: what the vocabulary session will show (items is only a preview).
    const n = typeof rec.evidence.word_count === "number" ? rec.evidence.word_count : rec.items.length;
    const words = `${n} word${n === 1 ? "" : "s"}`;
    return rec.kind === "review"
      ? `Review ${words} due today`
      : rec.kind === "new_topic"
      ? `${nameOf(rec.skill_id, names)}: ${n} new word${n === 1 ? "" : "s"}`
      : `${nameOf(rec.skill_id, names)}: ${words} to practise`;
  }
  return rec.items[0]?.title ?? nameOf(rec.skill_id, names);
}

/** One recommendation as a compact, clickable row. */
export function RecommendationRow({ rec, names }: { rec: Recommendation; names?: SkillNames }) {
  const m = MODULE[rec.module];
  return (
    <Link href={recommendationHref(rec)} className="list-row">
      <IconTile icon={m.icon(18)} tone={m.tone} />
      <span className="row-main">
        <span className="row-title">{recommendationTitle(rec, names)}</span>
        <span className="row-sub">
          {rec.module === "vocabulary" ? m.label : `${m.label} · ${nameOf(rec.skill_id, names)}`}
        </span>
      </span>
      <span className="row-end">
        <Tag tone={KIND_TONE[rec.kind]}>{KIND_LABEL[rec.kind]}</Tag>
        <ArrowRightIcon size={16} className="muted" />
      </span>
    </Link>
  );
}

/** After an answer: the adaptive next step. */
export function NextUp({ rec }: { rec: Recommendation | null }) {
  if (!rec) return null;
  return (
    <div className="callout accent mt-16">
      <span className="callout-icon">
        <SparklesIcon size={18} />
      </span>
      <div className="callout-body">
        <strong className="callout-title">Up next: {recommendationTitle(rec)}</strong>
        <span className="small secondary">{rec.reason}</span>
      </div>
      <div className="callout-action">
        <Link className="btn small" href={recommendationHref(rec)}>
          Continue <ArrowRightIcon size={15} />
        </Link>
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <AlertCircleIcon size={19} />
      <span style={{ flex: 1 }}>{error}</span>
      {onRetry && (
        <button type="button" className="btn small ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
