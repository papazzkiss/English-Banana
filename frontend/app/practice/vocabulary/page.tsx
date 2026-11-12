"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { api, post } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { AssessmentView, ErrorBox, MasteryChanges, NextUp } from "@/components/Feedback";
import type { Cefr, DueCard, Rating, ReviewResponse } from "@/lib/types";
import { ArrowRightIcon, CheckIcon, LightbulbIcon, SearchIcon, VolumeIcon } from "@/components/ui/Icons";
import { CefrBadge, Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel, Stat } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { useSearchParams } from "next/navigation";
import { Segmented } from "@/components/ui/Segmented";
import { BankPractice } from "@/components/bank/BankPractice";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { speakWord } from "@/lib/speech";

const RATINGS: { rating: Rating; label: string; hint: string; key: string; className: string }[] = [
  { rating: "again", label: "Again", hint: "Forgot it", key: "1", className: "ghost again" },
  { rating: "hard", label: "Hard", hint: "Struggled", key: "2", className: "ghost hard" },
  { rating: "good", label: "Good", hint: "Remembered", key: "3", className: "" },
  { rating: "easy", label: "Easy", hint: "Instant", key: "4", className: "accent" },
];

type Tally = Record<Rating, number>;
const EMPTY_TALLY: Tally = { again: 0, hard: 0, good: 0, easy: 0 };

function VocabularyPractice() {
  const { profile } = useLearner();
  const learnerId = profile?.learner_id;
  const params = useSearchParams();
  const [tab, setTab] = useState<"review" | "queue" | "quiz">(
    params.get("tab") === "quiz" ? "quiz" : "review",
  );
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tally, setTally] = useState<Tally>(EMPTY_TALLY);
  const [finished, setFinished] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api<{ cards: DueCard[] }>("/vocabulary/due?limit=30");
      setCards(r.cards);
      setIndex(0);
      setRevealed(false);
      setResult(null);
      setAnswer("");
      setFinished(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (learnerId) load();
  }, [learnerId, load]);

  const card = cards?.[index];
  const total = cards?.length ?? 0;
  const reviewed = Object.values(tally).reduce((a, b) => a + b, 0);

  const reveal = useCallback(() => {
    if (!card) return;
    setRevealed(true);
    speakWord(card.back.word);
  }, [card]);

  const rate = useCallback(
    async (rating: Rating) => {
      if (!card || busy) return;
      setBusy(true);
      setError(null);
      try {
        const res = await post<ReviewResponse>("/vocabulary/review", {
          card_id: card.card_id,
          rating,
          answer: answer.trim() ? answer : undefined,
        });
        setResult(res);
        setTally((t) => ({ ...t, [rating]: t[rating] + 1 }));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [card, busy, answer]
  );

  const next = useCallback(() => {
    setResult(null);
    setRevealed(false);
    setAnswer("");
    if (cards && index + 1 < cards.length) setIndex(index + 1);
    else setFinished(true);
  }, [cards, index]);

  // Keyboard review: Space/Enter reveals and continues, 1–4 rate.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (tab !== "review" || !card || finished) return;
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "BUTTON") return;
      const go = e.code === "Space" || e.key === "Enter";
      if (!revealed && !result && go) {
        e.preventDefault();
        reveal();
      } else if (revealed && !result && ["1", "2", "3", "4"].includes(e.key)) {
        e.preventDefault();
        rate(RATINGS[Number(e.key) - 1].rating);
      } else if (result && go) {
        e.preventDefault();
        next();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tab, card, finished, revealed, result, reveal, rate, next]);

  return (
    <>
      <PageHeader
        back={{ href: "/practice", label: "Practice" }}
        title="Vocabulary"
        description="Recall the word, check it, then rate how hard it was. Words you find hard come back sooner."
        actions={
          <Segmented
            label="Vocabulary view"
            value={tab}
            onChange={setTab}
            options={[
              { value: "review", label: "Review" },
              { value: "queue", label: "Today's queue", count: total },
              { value: "quiz", label: "Quiz" },
            ]}
          />
        }
      />

      <ErrorBox error={error} onRetry={load} />

      {tab === "review" ? (
        cards === null ? (
          <div className="narrow"><SkeletonCard lines={4} /></div>
        ) : cards.length === 0 ? (
          <EmptyState
            icon={<CheckIcon size={28} />}
            title="No words due right now"
            description="You have reviewed everything that is due. New words will be scheduled as you keep practising."
            actionText="Check again"
            onAction={load}
            secondary={<Link href="/practice" className="btn ghost">Other practice</Link>}
          />
        ) : finished ? (
          <SessionSummary tally={tally} onMore={() => { setTally(EMPTY_TALLY); load(); }} />
        ) : card ? (
          <div className="narrow stack">
            <ProgressBar
              value={(100 * (index + (result ? 1 : 0))) / total}
              label="Session progress"
              showValue
              valueText={`${index + 1} / ${total}`}
            />

            <section className="card flashcard" aria-live="polite">
              <div className="chip-row" style={{ justifyContent: "center" }}>
                {card.is_new ? <Tag tone="good">New word</Tag> : <Tag>Review · every {card.state?.interval_days}d</Tag>}
                <CefrBadge level={card.cefr_level} />
                <Tag>{card.back.part_of_speech}</Tag>
              </div>

              <p className="prompt flash-prompt">{card.front.prompt}</p>
              {card.front.hint && (
                <p className="small muted row" style={{ justifyContent: "center", gap: 6 }}>
                  <LightbulbIcon size={14} /> {card.front.hint}
                </p>
              )}

              {!revealed && !result && (
                <form onSubmit={(e) => { e.preventDefault(); reveal(); }}>
                  <label htmlFor="spell" className="sr-only">Type the word (optional)</label>
                  <input id="spell" type="text" className="spell input-lg" value={answer} autoComplete="off"
                    autoCapitalize="off" spellCheck={false} onChange={(e) => setAnswer(e.target.value)}
                    placeholder="Type the word (optional)" autoFocus />
                  <button type="submit" className="btn large">
                    Show answer <kbd>Enter</kbd>
                  </button>
                </form>
              )}

              {(revealed || result) && (
                <div className="flash-reveal">
                  <div className="row" style={{ justifyContent: "center" }}>
                    <span className="flash-word">{card.back.word}</span>
                    <button type="button" className="btn icon ghost" onClick={() => speakWord(card.back.word)}
                      aria-label={`Pronounce ${card.back.word}`} title="Pronounce">
                      <VolumeIcon size={20} />
                    </button>
                  </div>
                  <p className="flash-def">{card.back.definition}</p>
                  {card.back.example && <p className="flash-example">“{card.back.example}”</p>}

                  {!result && (
                    <div className="mt-24">
                      <p className="eyebrow" id="rate-label">How well did you remember it?</p>
                      <div className="rating-grid" role="group" aria-labelledby="rate-label">
                        {RATINGS.map((r) => (
                          <button key={r.rating} type="button" className={`btn rating-btn ${r.className}`}
                            disabled={busy} onClick={() => rate(r.rating)}>
                            {r.label}
                            <small>{r.hint} · <kbd>{r.key}</kbd></small>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>

            {result && (
              <div className="stack tight">
                {answer.trim() && <AssessmentView assessment={result.assessment} />}
                <div className="callout neutral">
                  <div className="callout-body small">
                    Rated <strong>{result.rating_applied}</strong>. Next review in{" "}
                    <strong>
                      {result.state.interval_days} day{result.state.interval_days === 1 ? "" : "s"}
                    </strong>
                    {result.state.due_date && <> ({new Date(result.state.due_date).toLocaleDateString()})</>}.
                  </div>
                </div>
                <MasteryChanges changes={result.mastery_changes} />
                <div className="btn-row">
                  <button type="button" className="btn large" onClick={next} autoFocus>
                    {index + 1 < total ? "Next word" : "Finish"} <ArrowRightIcon size={18} />
                  </button>
                  <span className="small muted">or press <kbd>Enter</kbd></span>
                </div>
                {index + 1 >= total && <NextUp rec={result.next_recommendation} />}
              </div>
            )}

            {reviewed > 0 && !result && (
              <p className="small muted" style={{ textAlign: "center", margin: 0 }}>
                {reviewed} reviewed this session
              </p>
            )}
          </div>
        ) : null
      ) : tab === "quiz" ? (
        <BankPractice skill="vocabulary" defaultLevel={profile?.current_level} />
      ) : (
        <Queue cards={cards} />
      )}
    </>
  );
}

function SessionSummary({ tally, onMore }: { tally: Tally; onMore: () => void }) {
  const total = Object.values(tally).reduce((a, b) => a + b, 0);
  const remembered = tally.good + tally.easy;
  return (
    <div className="narrow stack">
      <EmptyState
        icon={<CheckIcon size={28} />}
        title="Session complete"
        description={`You reviewed ${total} word${total === 1 ? "" : "s"} and remembered ${remembered}. Words marked Again or Hard will come back soon.`}
        actionText="Review more"
        onAction={onMore}
        secondary={<Link href="/dashboard" className="btn ghost">Back to home</Link>}
      />
      <div className="grid cols-4">
        {RATINGS.map((r) => (
          <Stat key={r.rating} label={r.label} value={tally[r.rating]} />
        ))}
      </div>
    </div>
  );
}

function Queue({ cards }: { cards: DueCard[] | null }) {
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<"all" | Cefr>("all");
  const [status, setStatus] = useState<"all" | "new" | "review">("all");

  const levels = useMemo(
    () => Array.from(new Set((cards ?? []).map((c) => c.cefr_level))).sort(),
    [cards]
  );

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (cards ?? []).filter((c) => {
      const text = `${c.back.word} ${c.back.definition} ${c.back.example ?? ""}`.toLowerCase();
      return (
        (!q || text.includes(q)) &&
        (level === "all" || c.cefr_level === level) &&
        (status === "all" || (status === "new") === c.is_new)
      );
    });
  }, [cards, query, level, status]);

  if (cards === null) return <SkeletonCard lines={5} />;

  return (
    <Panel
      title="Today's queue"
      description="Words due for review now, and new words scheduled for today"
      flush
    >
      <div className="row" style={{ padding: "0 22px 14px", gap: 10 }}>
        <div className="input-icon">
          <SearchIcon size={17} />
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search words, meanings or examples" aria-label="Search the queue" />
        </div>
        <Segmented label="Status" size="sm" value={status} onChange={setStatus}
          options={[{ value: "all", label: "All" }, { value: "new", label: "New" }, { value: "review", label: "Review" }]} />
        {levels.length > 1 && (
          <Segmented label="Level" size="sm" value={level} onChange={setLevel}
            options={[{ value: "all" as const, label: "All levels" }, ...levels.map((l) => ({ value: l, label: l }))]} />
        )}
      </div>

      {shown.length === 0 ? (
        <EmptyState compact title={cards.length ? "No matches" : "The queue is empty"}
          description={cards.length ? "Try another search or filter." : "Nothing is due right now."} />
      ) : (
        <ul className="list" style={{ borderTop: "1px solid var(--border)" }}>
          {shown.map((c) => (
            <li key={c.card_id} className="list-row">
              <button type="button" className="btn icon ghost" onClick={() => speakWord(c.back.word)}
                aria-label={`Pronounce ${c.back.word}`}>
                <VolumeIcon size={18} />
              </button>
              <span className="row-main">
                <span className="row-title">
                  {c.back.word} <span className="muted small" style={{ fontWeight: 500 }}>{c.back.part_of_speech}</span>
                </span>
                <span className="row-sub" style={{ whiteSpace: "normal" }}>{c.back.definition}</span>
              </span>
              <span className="row-end">
                <CefrBadge level={c.cefr_level} />
                {c.is_new ? <Tag tone="good">New</Tag> : <Tag>{c.state?.interval_days ?? 1}d</Tag>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div style={{ height: 8 }} />
    </Panel>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <VocabularyPractice />
    </Suspense>
  );
}
