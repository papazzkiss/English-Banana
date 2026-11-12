"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { BankPractice } from "@/components/bank/BankPractice";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api, postGraded } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { AssessmentView, ErrorBox, MasteryChanges, NextUp } from "@/components/Feedback";
import type { AttemptResponse, Exercise, GrammarTopic, MasteryResponse, SkillMastery } from "@/lib/types";
import { GRAMMAR_LESSONS } from "@/lib/grammarLessons";
import { masteryBand } from "@/lib/modules";
import { ArrowRightIcon, BookOpenIcon, CheckIcon, LightbulbIcon } from "@/components/ui/Icons";
import { CefrBadge, DifficultyBadge, Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Callout, IconTile, Panel, Spinner } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Segmented } from "@/components/ui/Segmented";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingScreen, SkeletonGrid } from "@/components/ui/Skeleton";

const BASE = "/practice/grammar";
const topicHref = (skillId: string, tab?: "practice") =>
  `${BASE}?topic=${encodeURIComponent(skillId)}${tab ? "&tab=practice" : ""}`;
const exerciseHref = (id: string) => `${BASE}?exercise=${encodeURIComponent(id)}`;

/** Topics, the learner's mastery and one topic's exercises: loaded once per screen. */
function useGrammarData(skillId?: string) {
  const [topics, setTopics] = useState<GrammarTopic[] | null>(null);
  const [mastery, setMastery] = useState<SkillMastery[]>([]);
  const [exercises, setExercises] = useState<Exercise[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<GrammarTopic[]>("/grammar/topics"), api<MasteryResponse>("/learner/mastery")])
      .then(([t, m]) => {
        setTopics(t);
        setMastery(m.skills);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    if (!skillId) return;
    setExercises(null);
    api<{ exercises: Exercise[] }>(`/grammar/exercises?skill_id=${encodeURIComponent(skillId)}`)
      .then((r) => setExercises(r.exercises))
      .catch((e) => setError((e as Error).message));
  }, [skillId]);

  return { topics, mastery, exercises, error };
}

function skillMastery(mastery: SkillMastery[], skillId: string) {
  const s = mastery.find((m) => m.skill_id === skillId);
  return s && s.attempt_count > 0 ? s.effective_mastery : null;
}

/* Topics ---------------------------------------------------------------------------------- */

function TopicsView({ sets }: { sets: boolean }) {
  const { topics, mastery, error } = useGrammarData();
  const { profile } = useLearner();
  const router = useRouter();

  return (
    <>
      <PageHeader
        back={{ href: "/practice", label: "Practice" }}
        title="Grammar"
        description="Each topic has a short lesson with rules and examples, then exercises that are graded with feedback. Practice sets draw new questions from a large pool."
        actions={
          <Segmented
            label="Grammar view"
            value={sets ? "sets" : "topics"}
            onChange={(v) => router.replace(v === "sets" ? `${BASE}?view=sets` : BASE)}
            options={[
              { value: "topics", label: "Topics" },
              { value: "sets", label: "Practice sets" },
            ]}
          />
        }
      />
      <ErrorBox error={error} />
      {sets ? (
        <BankPractice skill="grammar" defaultLevel={profile?.current_level} />
      ) : !topics ? (
        <SkeletonGrid count={6} columns={2} />
      ) : (
        <div className="grid cols-2">
          {topics.map((t) => {
            const value = skillMastery(mastery, t.skill_id);
            const band = masteryBand(value);
            return (
              <Link key={t.skill_id} href={topicHref(t.skill_id)} className="card interactive">
                <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start", gap: 14 }}>
                  <IconTile icon={<BookOpenIcon size={20} />} tone="violet" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h2 style={{ margin: "0 0 4px" }}>{t.name}</h2>
                    <p className="small secondary" style={{ margin: 0 }}>{t.description}</p>
                  </div>
                </div>
                <ProgressBar value={value ?? 0} label={`${t.name} mastery`} size="sm" tone="violet" />
                <div className="card-foot">
                  <span className="chip-row">
                    <Tag tone={band.tone}>{band.label}</Tag>
                    <span className="small muted">{t.exercise_count} exercises</span>
                  </span>
                  <span className="go">
                    {value === null ? "Start" : "Continue"} <ArrowRightIcon size={15} />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}

/* Lesson + exercise list for one topic ---------------------------------------------------- */

function TopicView({ skillId, tab }: { skillId: string; tab: "lesson" | "practice" }) {
  const { topics, mastery, exercises, error } = useGrammarData(skillId);
  const [view, setView] = useState(tab);
  useEffect(() => setView(tab), [tab]);

  const topic = topics?.find((t) => t.skill_id === skillId);
  const lesson = GRAMMAR_LESSONS[skillId];

  if (error) return <ErrorBox error={error} />;
  if (!topics) return <LoadingScreen label="Loading lesson" />;
  if (!topic) {
    return (
      <EmptyState title="Topic not found" description="This grammar topic does not exist any more."
        actionText="All topics" actionHref={BASE} />
    );
  }

  const value = skillMastery(mastery, skillId);
  const band = masteryBand(value);
  const count = exercises?.length ?? topic.exercise_count;

  return (
    <>
      <PageHeader
        back={{ href: BASE, label: "All topics" }}
        eyebrow="Grammar"
        title={topic.name}
        description={topic.description}
        meta={
          <>
            <Tag tone={band.tone}>{band.label}</Tag>
            {value !== null && <span className="small muted">Mastery {Math.round(value)}/100</span>}
          </>
        }
        actions={
          <Segmented
            label="Topic section"
            value={view}
            onChange={setView}
            options={[
              { value: "lesson", label: "1 · Lesson" },
              { value: "practice", label: "2 · Practice", count },
            ]}
          />
        }
      />

      {view === "lesson" ? (
        <div className="stack">
          {lesson ? (
            <>
              <Callout tone="accent" icon={<LightbulbIcon size={18} />} title="In short">
                {lesson.summary}
              </Callout>

              <section>
                <h2>Rules</h2>
                <div className="grid cols-3">
                  {lesson.rules.map((r) => (
                    <div key={r.name} className="card rule">
                      <strong>{r.name}</strong>
                      <code className="formula">{r.formula}</code>
                      <span className="small secondary">{r.usage}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h2>Examples</h2>
                <div className="grid cols-2">
                  {lesson.examples.map((ex) => (
                    <div key={ex.sentence} className="example">
                      <q>{ex.sentence}</q>
                      <span className="small secondary">{ex.explanation}</span>
                    </div>
                  ))}
                </div>
              </section>

              {lesson.mistakeAlerts.length > 0 && (
                <section>
                  <h2>Common mistakes</h2>
                  <div className="grid cols-2">
                    {lesson.mistakeAlerts.map((m) => (
                      <div key={m.wrong} className="pair">
                        <span className="wrong">{m.wrong}</span>
                        <span className="right">{m.correct}</span>
                        <span className="small secondary">{m.why}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <Callout tone="neutral" icon={<LightbulbIcon size={18} />} title="Tip">
                {lesson.quickTip}
              </Callout>
            </>
          ) : (
            <Callout tone="info" title="No written lesson for this topic yet">
              Go straight to the exercises: every answer comes with an explanation.
            </Callout>
          )}

          <div className="btn-row">
            <button type="button" className="btn large" onClick={() => setView("practice")}>
              Practise this topic <ArrowRightIcon size={18} />
            </button>
          </div>
        </div>
      ) : (
        <Panel title="Exercises" description="Pick one, or start at the top and work down" flush>
          {!exercises ? (
            <div style={{ padding: "0 22px 22px" }}><SkeletonGrid count={2} columns={2} /></div>
          ) : (
            <ol className="list" style={{ borderTop: "1px solid var(--border)" }}>
              {exercises.map((e, i) => (
                <li key={e.id}>
                  <Link href={exerciseHref(e.id)} className="list-row">
                    <span className="icon-tile sm tone-neutral num strong">{i + 1}</span>
                    <span className="row-main">
                      <span className="row-title">{e.prompt}</span>
                      <span className="row-sub">{e.instruction}</span>
                    </span>
                    <span className="row-end">
                      <DifficultyBadge difficulty={e.difficulty} />
                      <ArrowRightIcon size={16} className="muted" />
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
          <div style={{ height: 8 }} />
        </Panel>
      )}
    </>
  );
}

/* One exercise ----------------------------------------------------------------------------- */

function ExerciseRunner({ exerciseId }: { exerciseId: string }) {
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AttemptResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHint, setShowHint] = useState(false);
  const [started, setStarted] = useState(Date.now());
  const { topics, exercises } = useGrammarData(exercise?.skill_id);

  useEffect(() => {
    setExercise(null);
    setResult(null);
    setAnswer("");
    setError(null);
    setShowHint(false);
    setStarted(Date.now());
    api<Exercise>(`/grammar/exercises/${encodeURIComponent(exerciseId)}`)
      .then(setExercise)
      .catch((e) => setError((e as Error).message));
  }, [exerciseId]);

  const position = useMemo(() => exercises?.findIndex((e) => e.id === exerciseId) ?? -1, [exercises, exerciseId]);
  const nextInTopic = exercises && position >= 0 ? exercises[position + 1] : undefined;

  async function submit(e?: { preventDefault(): void }) {
    e?.preventDefault();
    if (!answer.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(
        await postGraded<AttemptResponse>("/grammar/attempt", {
          exercise_id: exerciseId,
          answer,
          response_time_ms: Date.now() - started,
        })
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!exercise) return error ? <ErrorBox error={error} /> : <LoadingScreen label="Loading exercise" />;

  const topic = topics?.find((t) => t.skill_id === exercise.skill_id);
  const long = exercise.exercise_type !== "fill_in_blank";

  return (
    <>
      <PageHeader
        back={{ href: topicHref(exercise.skill_id, "practice"), label: topic?.name ?? "Topic" }}
        eyebrow={exercises && position >= 0 ? `Exercise ${position + 1} of ${exercises.length}` : "Exercise"}
        title={topic?.name ?? "Grammar exercise"}
        meta={
          <>
            <CefrBadge level={exercise.cefr_level} />
            <DifficultyBadge difficulty={exercise.difficulty} />
          </>
        }
      />

      <div className="narrow stack">
        {exercises && position >= 0 && (
          <ProgressBar value={(100 * (position + (result ? 1 : 0))) / exercises.length} label="Topic progress" size="sm" tone="violet" />
        )}

        <section className="card">
          <p className="instruction">{exercise.instruction}</p>
          <p className="prompt">{exercise.prompt}</p>

          {exercise.hint && (
            showHint ? (
              <Callout tone="neutral" icon={<LightbulbIcon size={16} />}>{exercise.hint}</Callout>
            ) : (
              <button type="button" className="link-btn small row" style={{ gap: 5 }} onClick={() => setShowHint(true)}>
                <LightbulbIcon size={14} /> Show a hint
              </button>
            )
          )}

          <form onSubmit={submit} className="mt-16">
            <label htmlFor="answer" className="sr-only">Your answer</label>
            {long ? (
              <textarea id="answer" rows={3} value={answer} maxLength={300} disabled={busy || !!result}
                onChange={(e) => setAnswer(e.target.value)} placeholder="Write your answer…" autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
                }} />
            ) : (
              <input id="answer" type="text" className="input-lg" value={answer} maxLength={300}
                disabled={busy || !!result} onChange={(e) => setAnswer(e.target.value)}
                placeholder="Fill in the blank…" autoFocus autoComplete="off" />
            )}
            {!result && (
              <div className="btn-row mt-12">
                <button type="submit" className="btn large" disabled={busy || !answer.trim()}>
                  {busy ? <><Spinner /> Checking…</> : <>Check answer</>}
                </button>
                <span className="small muted" aria-live="polite">
                  {busy ? "Grading usually takes 10–20 seconds." : long ? "Ctrl + Enter to submit" : "Enter to submit"}
                </span>
              </div>
            )}
          </form>
          <ErrorBox error={error} />
        </section>

        {result && (
          <>
            <AssessmentView assessment={result.assessment} attemptId={result.attempt_id}
              referenceAnswers={result.reference_answers} explanation={result.explanation} />
            <MasteryChanges changes={result.mastery_changes} />
            <div className="btn-row stack-mobile">
              {nextInTopic ? (
                <Link className="btn large" href={exerciseHref(nextInTopic.id)}>
                  Next exercise <ArrowRightIcon size={18} />
                </Link>
              ) : (
                <Link className="btn large" href={topicHref(exercise.skill_id)}>
                  <CheckIcon size={18} /> Topic finished
                </Link>
              )}
              <Link className="btn ghost large" href={topicHref(exercise.skill_id, "practice")}>
                All exercises
              </Link>
            </div>
            {!nextInTopic && <NextUp rec={result.next_recommendation} />}
          </>
        )}
      </div>
    </>
  );
}

function GrammarPage() {
  useLearner();
  const params = useSearchParams();
  const exerciseId = params.get("exercise");
  const topic = params.get("topic");
  const tab = params.get("tab") === "practice" ? "practice" : "lesson";

  if (exerciseId) return <ExerciseRunner exerciseId={exerciseId} />;
  if (topic) return <TopicView skillId={topic} tab={tab} />;
  return <TopicsView sets={params.get("view") === "sets"} />;
}

export default function Page() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <GrammarPage />
    </Suspense>
  );
}

