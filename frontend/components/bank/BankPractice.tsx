"use client";

/** Question-bank practice: choose filters, get a fresh set drawn from the pool, answer with
 * instant feedback (checked by rules on the server), see the score, draw another set. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  bankApi, EMPTY_FILTERS, errorParts, pointLabel, QTYPE_LABEL, setScore, topicLabel,
  type AnswerValue, type BankAnswer, type BankFacets, type BankPassage, type BankQuestion,
  type BankSet, type BankSkill, type BankSummary, type QType, type SetFilters,
} from "@/lib/bank";
import type { Cefr } from "@/lib/types";
import { ErrorBox } from "@/components/Feedback";
import { AudioPlayer } from "@/components/practice/AudioPlayer";
import { CefrBadge, Tag } from "@/components/ui/Badge";
import { Segmented } from "@/components/ui/Segmented";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { ArrowRightIcon, CheckIcon, RotateCcwIcon, XCircleIcon } from "@/components/ui/Icons";

const LEVELS: Cefr[] = ["A1", "A2", "B1", "B2", "C1"];
const COPY: Record<BankSkill, { focus: string; focusKey: "points" | "topics" | "qtypes" }> = {
  grammar: { focus: "Grammar point", focusKey: "points" },
  vocabulary: { focus: "Question type", focusKey: "points" },
  reading: { focus: "Topic", focusKey: "topics" },
  listening: { focus: "Topic", focusKey: "topics" },
};

export function BankPractice({ skill, defaultLevel }: { skill: BankSkill; defaultLevel?: Cefr }) {
  const [facets, setFacets] = useState<BankFacets | null>(null);
  const [summary, setSummary] = useState<BankSummary | null>(null);
  const [filters, setFilters] = useState<SetFilters>({
    ...EMPTY_FILTERS, levels: defaultLevel ? [defaultLevel] : [],
  });
  // the learner's level arrives after the first render on most pages: apply it then, unless
  // the learner has already picked levels
  const levelsPicked = useRef(false);
  useEffect(() => {
    if (defaultLevel && !levelsPicked.current) setFilters((f) => ({ ...f, levels: [defaultLevel] }));
  }, [defaultLevel]);
  const [set, setSet] = useState<BankSet | null>(null);
  const [results, setResults] = useState<BankAnswer[]>([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(() => {
    bankApi.summary(skill).then(setSummary).catch(() => undefined);
  }, [skill]);

  useEffect(() => {
    bankApi.facets(skill).then(setFacets).catch((e) => setError((e as Error).message));
    refresh();
  }, [skill, refresh]);

  const start = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await bankApi.newSet(skill, filters);
      setSet(s);
      setResults([]);
      setIndex(0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const finish = () => {
    setSet(null);
    refresh();
  };

  if (set && set.questions.length > 0 && index < set.questions.length) {
    return (
      <SetRunner
        key={set.questions[0].id}
        set={set}
        index={index}
        results={results}
        onAnswered={(r) => setResults((prev) => [...prev, r])}
        onNext={() => setIndex((i) => i + 1)}
        onQuit={finish}
        names={facets?.point_names ?? {}}
      />
    );
  }

  if (set && set.questions.length > 0) {
    const score = setScore(results);
    return (
      <section className="card bank-done" aria-live="polite">
        <p className="eyebrow">Set complete</p>
        <h2 style={{ margin: "0 0 4px" }}>{score.correct} / {score.total} correct</h2>
        <p className="secondary" style={{ margin: "0 0 16px" }}>
          Score {score.percent}% · {set.review_count ? `${set.review_count} were review questions · ` : ""}
          every answer updated your progress.
        </p>
        <ProgressBar value={score.percent} label="Set score" tone={score.percent >= 70 ? "green" : "orange"} />
        <div className="btn-row mt-16">
          <button type="button" className="btn accent" onClick={start} disabled={loading}>
            <RotateCcwIcon size={16} /> New set, same filters
          </button>
          <button type="button" className="btn ghost" onClick={finish}>Change filters</button>
        </div>
      </section>
    );
  }

  const focus = COPY[skill];
  const focusCounts = facets ? facets[focus.focusKey] : {};
  const selectedFocus = filters[focus.focusKey === "qtypes" ? "qtypes" : focus.focusKey] as string[];
  return (
    <section className="card bank-setup" aria-labelledby={`bank-${skill}`}>
      <div className="row-between" style={{ alignItems: "flex-start" }}>
        <div>
          <h2 id={`bank-${skill}`} style={{ margin: "0 0 4px" }}>Practice sets</h2>
          <p className="small secondary" style={{ margin: 0 }}>
            A new set from the question pool every time. Answers are checked instantly.
          </p>
        </div>
        {summary && (
          <span className="chip-row">
            <Tag>{summary.pool_size.toLocaleString()} questions</Tag>
            <Tag tone="blue">{summary.questions_seen.toLocaleString()} done</Tag>
            {summary.to_review > 0 && <Tag tone="orange">{summary.to_review} to review</Tag>}
          </span>
        )}
      </div>
      <ErrorBox error={error} />
      {facets && facets.total === 0 ? (
        <p className="small muted mt-16">The question pool is empty. Import it with <code>python -m banana_english.contentbank import</code>.</p>
      ) : (
        <div className="bank-filters mt-16">
          <div>
            <span className="bank-label">Level</span>
            <div className="chip-row" role="group" aria-label="Levels">
              {LEVELS.map((l) => (
                <button key={l} type="button" className="chip"
                  aria-pressed={filters.levels.includes(l)} disabled={!facets?.levels[l]}
                  onClick={() => {
                    levelsPicked.current = true;
                    setFilters((f) => ({ ...f, levels: toggle(f.levels, l) }));
                  }}>
                  {l}{facets?.levels[l] ? <span className="chip-soft"> {facets.levels[l].toLocaleString()}</span> : null}
                </button>
              ))}
            </div>
          </div>
          <label className="bank-label" htmlFor={`focus-${skill}`}>
            {focus.focus}
            <select id={`focus-${skill}`} value={selectedFocus[0] ?? ""}
              onChange={(e) => setFilters((f) => ({ ...f, [focus.focusKey]: e.target.value ? [e.target.value] : [] }))}>
              <option value="">All</option>
              {Object.entries(focusCounts).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                <option key={k} value={k}>
                  {focus.focusKey === "topics" ? topicLabel(k) : pointLabel(k, facets?.point_names ?? {})} ({n.toLocaleString()})
                </option>
              ))}
            </select>
          </label>
          {skill === "grammar" && facets && (
            <label className="bank-label" htmlFor="qtype-grammar">
              Question type
              <select id="qtype-grammar" value={filters.qtypes[0] ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, qtypes: e.target.value ? [e.target.value as QType] : [] }))}>
                <option value="">All</option>
                {Object.entries(facets.qtypes).map(([k, n]) => (
                  <option key={k} value={k}>{QTYPE_LABEL[k as QType] ?? k} ({n.toLocaleString()})</option>
                ))}
              </select>
            </label>
          )}
          <div>
            <span className="bank-label">Questions</span>
            <Segmented label="Number of questions" size="sm" value={filters.count}
              onChange={(count) => setFilters((f) => ({ ...f, count }))}
              options={[5, 10, 20, 30].map((n) => ({ value: n, label: String(n) }))} />
          </div>
          <div className="btn-row">
            <button type="button" className="btn accent large" onClick={start} disabled={loading || !facets}>
              {loading ? "Drawing a set…" : "Start practice"} <ArrowRightIcon size={18} />
            </button>
          </div>
          {set && set.questions.length === 0 && (
            <p className="small muted">No questions match these filters. Try another level or topic.</p>
          )}
        </div>
      )}
    </section>
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

/* --- running a set ---------------------------------------------------------------------- */

function SetRunner({
  set, index, results, onAnswered, onNext, onQuit, names,
}: {
  set: BankSet;
  index: number;
  results: BankAnswer[];
  onAnswered: (r: BankAnswer) => void;
  onNext: () => void;
  onQuit: () => void;
  names: Record<string, string>;
}) {
  const q = set.questions[index];
  const passage = useMemo(() => set.passages.find((p) => p.id === q.passage_id) ?? null, [set, q]);
  const answered = results.length > index ? results[index] : null;
  const correct = results.filter((r) => r.correct).length;
  return (
    <div className="bank-run">
      <div className="row-between bank-progress">
        <span className="small secondary">
          Question {index + 1} of {set.questions.length} · {correct} correct
        </span>
        <button type="button" className="btn small ghost" onClick={onQuit}>End set</button>
      </div>
      <ProgressBar value={(100 * index) / set.questions.length} label="Set progress" size="sm" />
      <div className={passage ? "bank-split" : ""}>
        {passage && <PassagePanel passage={passage} answeredOne={results.some((r, i) =>
          set.questions[i]?.passage_id === passage.id && r)} />}
        <QuestionCard key={q.id} q={q} names={names} answered={answered}
          onAnswered={onAnswered} onNext={onNext} last={index + 1 === set.questions.length} />
      </div>
    </div>
  );
}

function PassagePanel({ passage, answeredOne }: { passage: BankPassage; answeredOne: boolean }) {
  const [transcript, setTranscript] = useState<string | null>(null);
  useEffect(() => setTranscript(null), [passage.id]);
  return (
    <section className="card bank-passage" aria-label="Text">
      <div className="row-between" style={{ marginBottom: 8 }}>
        <strong>{passage.audio_url ? "Listen" : passage.title}</strong>
        <span className="chip-row"><CefrBadge level={passage.level} /><Tag>{topicLabel(passage.topic)}</Tag></span>
      </div>
      {passage.audio_url && (
        <AudioPlayer key={passage.id} src={passage.audio_url} fallbackDuration={passage.duration_s ?? 20} />
      )}
      {passage.text && <p className="bank-text">{passage.text}</p>}
      {passage.audio_url && (
        transcript ? (
          <p className="bank-text transcript">{transcript}</p>
        ) : (
          <button type="button" className="link-btn small mt-8" disabled={!answeredOne}
            title={answeredOne ? undefined : "Answer a question first"}
            onClick={() => bankApi.transcript(passage.id).then((t) => setTranscript(t.transcript))}>
            Show transcript
          </button>
        )
      )}
      {passage.source?.license && passage.source.id && !passage.source.id.startsWith("template") && (
        <p className="small muted mt-8">Source: {passage.source.id === "simplewiki" ? "Simple English Wikipedia" :
          passage.source.id.startsWith("enwiki") ? "Wikipedia" : "Tatoeba"} ({passage.source.license})</p>
      )}
    </section>
  );
}

function QuestionCard({
  q, names, answered, onAnswered, onNext, last,
}: {
  q: BankQuestion;
  names: Record<string, string>;
  answered: BankAnswer | null;
  onAnswered: (r: BankAnswer) => void;
  onNext: () => void;
  last: boolean;
}) {
  const shownAt = useRef(performance.now());
  const [chosen, setChosen] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [order, setOrder] = useState<string[]>([]);
  const [pairs, setPairs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (value: AnswerValue) => {
    if (answered || busy) return;
    setBusy(true);
    setError(null);
    try {
      onAnswered(await bankApi.answer(q.id, value, performance.now() - shownAt.current));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [answered, busy, onAnswered, q.id]);

  const choice = q.qtype === "mcq" || q.qtype === "true_false" || q.qtype === "error_id";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "TEXTAREA"
        || (e.target as HTMLElement)?.tagName === "SELECT") return;
      if (answered && e.key === "Enter") {
        e.preventDefault();
        onNext();
      } else if (!answered && choice && /^[1-8]$/.test(e.key)) {
        const option = q.options[Number(e.key) - 1];
        if (option) {
          setChosen(option.id);
          void submit(option.id);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [answered, choice, onNext, q.options, submit]);

  const right = answered?.detail?.right_option as string | undefined;
  const parts = q.qtype === "error_id" ? errorParts(q.prompt) : null;

  return (
    <section className="card bank-question" aria-live="polite">
      <div className="chip-row" style={{ marginBottom: 10 }}>
        <CefrBadge level={q.level} />
        <Tag>{pointLabel(q.point, names)}</Tag>
        <span className="small muted">{QTYPE_LABEL[q.qtype]}</span>
      </div>
      <p className="small secondary" style={{ margin: "0 0 8px" }}>{q.instruction}</p>
      {parts ? (
        <p className="bank-prompt">
          {parts.parts.map((p, i) => (
            <span key={i}><span className="error-part"><b>{String.fromCharCode(65 + i)}</b>{p}</span>{" "}</span>
          ))}{parts.end}
        </p>
      ) : (
        <p className="bank-prompt">{q.prompt}</p>
      )}

      {choice && (
        <div className={`bank-options${q.qtype === "true_false" ? " two" : ""}`} role="group" aria-label="Options">
          {q.options.map((o, i) => {
            const state = !answered ? (chosen === o.id ? "chosen" : "")
              : o.id === right ? "right" : o.id === chosen ? "wrong" : "dim";
            return (
              <button key={o.id} type="button" className={`bank-option ${state}`} disabled={!!answered || busy}
                aria-pressed={chosen === o.id}
                onClick={() => { setChosen(o.id); void submit(o.id); }}>
                <span className="bank-key" aria-hidden>{parts ? String.fromCharCode(65 + parts.parts.indexOf(o.text)) : i + 1}</span>
                <span>{o.text}</span>
                {answered && o.id === right && <CheckIcon size={16} />}
                {answered && o.id === chosen && o.id !== right && <XCircleIcon size={16} />}
              </button>
            );
          })}
        </div>
      )}

      {(q.qtype === "fill_blank" || q.qtype === "dictation") && (
        <form className="bank-typed" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void submit(text); }}>
          {q.qtype === "dictation" ? (
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} disabled={!!answered}
              placeholder="Type what you hear…" aria-label="Your answer" />
          ) : (
            <input type="text" value={text} onChange={(e) => setText(e.target.value)} disabled={!!answered}
              placeholder="Your answer" aria-label="Your answer" autoComplete="off" />
          )}
          {!answered && <button className="btn" type="submit" disabled={!text.trim() || busy}>Check</button>}
        </form>
      )}

      {q.qtype === "ordering" && q.pieces && (
        <div className="bank-ordering">
          <div className="bank-order-line" aria-label="Your sentence">
            {order.length === 0 ? <span className="small muted">Tap the words below in order.</span> :
              order.map((w, i) => (
                <button key={`${w}-${i}`} type="button" className="chip" disabled={!!answered}
                  onClick={() => setOrder((o) => o.filter((_, j) => j !== i))}>{w}</button>
              ))}
          </div>
          <div className="chip-row">
            {q.pieces.map((w, i) => {
              const used = order.filter((x) => x === w).length >= q.pieces!.filter((x) => x === w).length;
              return (
                <button key={`${w}-${i}`} type="button" className="chip" disabled={used || !!answered}
                  onClick={() => setOrder((o) => [...o, w])}>{w}</button>
              );
            })}
          </div>
          {!answered && (
            <div className="btn-row mt-8">
              <button type="button" className="btn" disabled={order.length !== q.pieces.length || busy}
                onClick={() => void submit(order)}>Check</button>
              <button type="button" className="btn ghost small" onClick={() => setOrder([])}>Reset</button>
            </div>
          )}
        </div>
      )}

      {q.qtype === "matching" && q.left && (
        <div className="bank-matching">
          {q.left.map((l) => (
            <label key={l.id} className="bank-match-row">
              <strong>{l.text}</strong>
              <select value={pairs[l.id] ?? ""} disabled={!!answered}
                onChange={(e) => setPairs((p) => ({ ...p, [l.id]: e.target.value }))}>
                <option value="">Choose…</option>
                {q.options.map((o) => <option key={o.id} value={o.id}>{o.text}</option>)}
              </select>
            </label>
          ))}
          {!answered && (
            <button type="button" className="btn mt-8" disabled={Object.keys(pairs).length !== q.left.length || busy}
              onClick={() => void submit(pairs)}>Check</button>
          )}
        </div>
      )}

      <ErrorBox error={error} />
      {answered && <Feedback a={answered} q={q} onNext={onNext} last={last} />}
    </section>
  );
}

function Feedback({ a, q, onNext, last }: { a: BankAnswer; q: BankQuestion; onNext: () => void; last: boolean }) {
  const next = useRef<HTMLButtonElement>(null);
  useEffect(() => next.current?.focus(), []);
  const accuracy = a.detail?.word_accuracy as number | undefined;
  return (
    <div className={`assessment ${a.correct ? "good" : "bad"} mt-16`} role="status">
      <div className="assessment-head">
        <strong>{a.correct ? "Correct!" : q.qtype === "matching" || q.qtype === "dictation" ? `Score ${Math.round(a.score)}%` : "Not quite"}</strong>
        {accuracy !== undefined && <span className="small muted">{Math.round(accuracy * 100)}% of the words right</span>}
      </div>
      {!a.correct && a.correct_answer && (
        <p className="answer-line"><span className="small muted">Answer:</span> <strong>{a.correct_answer}</strong></p>
      )}
      <p className="assessment-feedback">{a.explanation}</p>
      {a.explanation_vi && <p className="small secondary" lang="vi" style={{ margin: 0 }}>{a.explanation_vi}</p>}
      <div className="btn-row mt-12">
        <button ref={next} type="button" className="btn accent" onClick={onNext}>
          {last ? "See results" : "Next question"} <ArrowRightIcon size={16} />
        </button>
        <span className="small muted">Enter ↵</span>
      </div>
    </div>
  );
}
