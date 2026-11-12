"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, post, waitForJob } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { AssessmentView, ErrorBox, MasteryChanges } from "@/components/Feedback";
import type { Conversation, ConversationSummary, Job } from "@/lib/types";
import { ArrowRightIcon, CheckIcon, SendIcon, TargetIcon } from "@/components/ui/Icons";
import { CefrBadge, Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Callout, Panel, Spinner, Stat } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { LoadingScreen } from "@/components/ui/Skeleton";

export default function ConversationPage() {
  useLearner();
  const { id } = useParams<{ id: string }>();
  const [conv, setConv] = useState<Conversation | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"send" | "finish" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const windowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Conversation>(`/conversations/${encodeURIComponent(id)}`)
      .then(setConv)
      .catch((e) => setError((e as Error).message));
  }, [id]);

  // Keep the newest message in view inside the chat window (not the whole page).
  useEffect(() => {
    const el = windowRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [conv?.turns.length, busy]);

  // A summary that is still being written: check again every few seconds.
  useEffect(() => {
    if (conv?.status !== "finishing" || conv.summary || busy) return;
    const t = setTimeout(() => {
      api<Conversation>(`/conversations/${encodeURIComponent(id)}`).then(setConv).catch(() => undefined);
    }, 4000);
    return () => clearTimeout(t);
  }, [conv, busy, id]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy("send");
    setError(null);
    try {
      setConv(await post<Conversation>(`/conversations/${encodeURIComponent(id)}/messages`, { text }));
      setText("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
      inputRef.current?.focus();
    }
  }

  async function finish() {
    setBusy("finish");
    setError(null);
    try {
      const job = await post<Job<ConversationSummary>>(`/conversations/${encodeURIComponent(id)}/finish`);
      const done = await waitForJob<ConversationSummary>(job.job_id);
      if (done.status === "failed") throw new Error(done.error ?? "The conversation could not be graded.");
      setConv(await api<Conversation>(`/conversations/${encodeURIComponent(id)}`));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!conv) return error ? <ErrorBox error={error} /> : <LoadingScreen label="Loading conversation" />;

  const s = conv.summary;
  const active = conv.status === "active";
  const learnerTurns = conv.turns.filter((t) => t.role === "learner").length;
  const max = conv.scenario.max_learner_turns;
  const canSend = active && conv.learner_turns_left > 0;

  return (
    <>
      <PageHeader
        back={{ href: "/practice/conversation", label: "All scenarios" }}
        eyebrow="Conversation"
        title={conv.scenario.title}
        meta={
          <>
            <CefrBadge level={conv.scenario.cefr_level} />
            <Tag tone={active ? "blue" : "good"}>{active ? `${conv.learner_turns_left} turns left` : "Finished"}</Tag>
          </>
        }
      />

      <div className="narrow stack">
        <details className="callout accent" open={learnerTurns === 0}>
          <summary style={{ cursor: "pointer", fontWeight: 650, listStyle: "none" }} className="row">
            <TargetIcon size={17} /> You are {conv.scenario.learner_role} · {conv.scenario.goals.length} goals
          </summary>
          <ul className="small mt-8" style={{ paddingLeft: 22 }}>
            {conv.scenario.goals.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </details>

        <section className="card" aria-label="Conversation">
          {active && (
            <ProgressBar value={(100 * learnerTurns) / max} label="Turns used" size="sm" tone="green" showValue
              valueText={`Turn ${learnerTurns} of ${max}`} />
          )}
          <div ref={windowRef} className="chat-window mt-12" aria-live="polite">
            <div className="chat">
              {conv.turns.map((t, i) => (
                <div key={i} className={`bubble ${t.role}`}>
                  <span className="bubble-who">{t.role === "assistant" ? "Partner" : "You"}</span>
                  {t.text}
                </div>
              ))}
              {busy === "send" && (
                <div className="bubble assistant typing" aria-label="Your partner is typing">
                  <span /><span /><span />
                </div>
              )}
            </div>
          </div>

          <ErrorBox error={error} />

          {canSend && (
            <form className="composer mt-12" onSubmit={send}>
              <label htmlFor="reply" className="sr-only">Your reply</label>
              <input ref={inputRef} id="reply" type="text" value={text} maxLength={300} autoFocus autoComplete="off"
                onChange={(e) => setText(e.target.value)} placeholder="Write your reply in English…"
                disabled={busy !== null} />
              <button type="submit" className="btn" disabled={busy !== null || !text.trim()} aria-label="Send">
                {busy === "send" ? <Spinner /> : <SendIcon size={17} />}
                <span className="hide-mobile">Send</span>
              </button>
            </form>
          )}

          {active && (
            <div className="card-foot mt-16">
              <span className="small muted">
                {learnerTurns === 0 ? "Say something to begin." : "Finish whenever you have reached your goals."}
              </span>
              <button type="button" className="btn accent" onClick={finish} disabled={busy !== null || !learnerTurns}>
                {busy === "finish" ? <><Spinner /> Grading your turns…</> : <><CheckIcon size={16} /> Finish and get feedback</>}
              </button>
            </div>
          )}

          {conv.status === "finishing" && !s && (
            <Callout tone="info" icon={<Spinner size={16} />} role="status">
              Grading every turn. This page updates by itself.
            </Callout>
          )}
        </section>

        {s && (
          <Panel title="Your feedback" description="Each of your turns, graded for grammar and for getting the task done">
            <div className="grid cols-3">
              <Stat label="Average score" value={s.average_score !== null ? <>{Math.round(s.average_score)}<small>/100</small></> : "—"} tone="green" />
              <Stat label="Turns graded" value={<>{s.turns.length - s.ungraded_turns}<small>/ {s.turns.length}</small></>} />
              <Stat label="Mistakes" value={Object.values(s.error_counts).reduce((a, b) => a + b, 0)} />
            </div>

            {Object.keys(s.error_counts).length > 0 && (
              <div className="chip-row mt-16" aria-label="Mistakes by type">
                {Object.entries(s.error_counts).map(([k, v]) => (
                  <Tag key={k} tone="bad">{k.replace(/_/g, " ")} · {v}</Tag>
                ))}
              </div>
            )}

            <ol className="stack mt-24" style={{ listStyle: "none", padding: 0 }}>
              {s.turns.map((t, i) => (
                <li key={i}>
                  <p className="eyebrow">Turn {i + 1}</p>
                  <p className="strong" style={{ margin: "0 0 8px" }}>“{t.text}”</p>
                  {t.assessment ? (
                    <AssessmentView assessment={t.assessment} attemptId={t.attempt_id} />
                  ) : (
                    <p className="small muted">This turn could not be graded.</p>
                  )}
                </li>
              ))}
            </ol>

            <MasteryChanges changes={s.mastery_changes.filter((c, i, all) => all.findLastIndex((x) => x.skill_id === c.skill_id) === i)} />

            <div className="btn-row mt-24 stack-mobile">
              <Link className="btn large" href="/practice/conversation">
                Another scenario <ArrowRightIcon size={18} />
              </Link>
              <Link className="btn ghost large" href="/dashboard">Home</Link>
            </div>
          </Panel>
        )}
      </div>
    </>
  );
}
