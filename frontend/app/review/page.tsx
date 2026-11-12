"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ErrorBox } from "@/components/Feedback";
import { RoleGate } from "@/components/RoleGate";
import { CefrBadge, Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Segmented } from "@/components/ui/Segmented";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { answerText, reviewApi, type ReviewPage, type ReviewQuestion, type ReviewStatus } from "@/lib/admin";
import type { BankSkill } from "@/lib/bank";
import type { Cefr } from "@/lib/types";

const SKILLS: BankSkill[] = ["grammar", "vocabulary", "reading", "listening"];
const LEVELS: Cefr[] = ["A1", "A2", "B1", "B2", "C1"];
const STATUSES: ReviewStatus[] = ["validated", "approved", "draft", "disabled"];
const PAGE = 20;
const TONE: Record<ReviewStatus, "good" | "warn" | "bad" | "neutral"> = {
  approved: "good", validated: "neutral", draft: "warn", disabled: "bad",
};

export default function ReviewRoute() {
  return (
    <RoleGate area="review">
      <Suspense>
        <Review />
      </Suspense>
    </RoleGate>
  );
}

function Review() {
  const params = useSearchParams();
  const [skill, setSkill] = useState<BankSkill>((params.get("skill") as BankSkill) || "grammar");
  const [status, setStatus] = useState<ReviewStatus | "">("validated");
  const [level, setLevel] = useState<Cefr | "">("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPage(await reviewApi.page(skill, { status, level, q, limit: PAGE, offset }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [skill, status, level, q, offset]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  async function decide(question: ReviewQuestion, next: Exclude<ReviewStatus, "draft">) {
    try {
      const updated = await reviewApi.setStatus(question.id, next);
      setPage((p) => p && { ...p, questions: p.questions.map((x) => (x.id === updated.id ? updated : x)) });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const reset = () => setOffset(0);
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Content"
        title="Question bank review"
        description="Check questions and their answers. Approved questions are the only ones served when the server runs in reviewed-only mode; disabled ones are never served. A decision is kept when the bank is re-imported, until the question itself changes."
      />
      <ErrorBox error={error} onRetry={load} />
      <Panel>
        <Segmented
          label="Skill"
          value={skill}
          onChange={(s) => { setSkill(s); reset(); }}
          options={SKILLS.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))}
        />
        <div className="staff-toolbar mt-8">
          <div className="field">
            <label htmlFor="rv-status">Status</label>
            <select id="rv-status" value={status} onChange={(e) => { setStatus(e.target.value as ReviewStatus | ""); reset(); }}>
              <option value="">Any</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="rv-level">Level</label>
            <select id="rv-level" value={level} onChange={(e) => { setLevel(e.target.value as Cefr | ""); reset(); }}>
              <option value="">Any</option>
              {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div className="field grow">
            <label htmlFor="rv-q">Question id</label>
            <input id="rv-q" type="search" placeholder="e.g. present_perfect" value={q}
              onChange={(e) => { setQ(e.target.value); reset(); }} />
          </div>
        </div>
        {page && <p className="small muted">{page.total.toLocaleString()} questions</p>}
      </Panel>

      {!page ? (
        !error && <SkeletonCard lines={6} />
      ) : (
        <div>
          {page.questions.map((question) => (
            <ReviewCard key={question.id} q={question} onDecide={decide} />
          ))}
          {!page.questions.length && <p className="muted">No questions match.</p>}
          {page.total > PAGE && (
            <div className="pager">
              <span className="small muted">{offset + 1}–{Math.min(offset + PAGE, page.total)} of {page.total.toLocaleString()}</span>
              <div className="btn-row">
                <button type="button" className="btn small ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <button type="button" className="btn small ghost" disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReviewCard({ q, onDecide }: {
  q: ReviewQuestion;
  onDecide: (q: ReviewQuestion, next: Exclude<ReviewStatus, "draft">) => void;
}) {
  const right = typeof q.answer.option === "string" ? q.answer.option : null;
  return (
    <section className="card review-card" aria-label={q.id}>
      <div className="review-meta">
        <CefrBadge level={q.level} />
        <Tag>{q.point.replace(/_/g, " ")}</Tag>
        <Tag>{q.qtype.replace(/_/g, " ")}</Tag>
        <Tag tone={TONE[q.status]}>{q.status}</Tag>
        <span className="small muted">quality {q.quality.toFixed(2)}</span>
      </div>
      <div>
        <p className="small muted" style={{ margin: 0 }}>{q.instruction}</p>
        <p className="strong" style={{ margin: "4px 0 0" }}>{q.prompt}</p>
      </div>
      {q.options.length > 0 && (
        <ol className="review-options" type="a">
          {q.options.map((o) => <li key={o.id} className={o.id === right ? "right" : undefined}>{o.text}</li>)}
        </ol>
      )}
      <div className="review-answer"><span className="muted">Answer: </span><strong>{answerText(q)}</strong></div>
      <div className="small">
        <div>{q.explanation}</div>
        {q.explanation_vi && <div className="muted">{q.explanation_vi}</div>}
      </div>
      <div className="review-foot">
        <span className="mono">
          {q.id}
          {q.reviewed_at && ` · reviewed ${new Date(q.reviewed_at).toLocaleDateString()}`}
        </span>
        <div className="btn-row">
          {q.status !== "approved" && (
            <button type="button" className="btn small accent" onClick={() => onDecide(q, "approved")}>Approve</button>
          )}
          {q.status !== "disabled" && (
            <button type="button" className="btn small ghost" onClick={() => onDecide(q, "disabled")}>Disable</button>
          )}
          {(q.status === "approved" || q.status === "disabled") && (
            <button type="button" className="btn small subtle" onClick={() => onDecide(q, "validated")}>Undo</button>
          )}
        </div>
      </div>
    </section>
  );
}
