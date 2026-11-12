"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, postGraded } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { AssessmentView, ErrorBox, MasteryChanges, NextUp } from "@/components/Feedback";
import type { AttemptResponse, ListeningLesson } from "@/lib/types";
import { AudioPlayer } from "@/components/practice/AudioPlayer";
import { ArrowRightIcon, CheckIcon, ClockIcon, FileTextIcon, LockIcon } from "@/components/ui/Icons";
import { CefrBadge, DifficultyBadge, Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Callout, Spinner } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { LoadingScreen } from "@/components/ui/Skeleton";

export default function ListeningLessonPage() {
  useLearner();
  const { id } = useParams<{ id: string }>();
  const [lesson, setLesson] = useState<ListeningLesson | null>(null);
  const [nextLessonId, setNextLessonId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, AttemptResponse>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<ListeningLesson>(`/listening/lessons/${encodeURIComponent(id)}`)
      .then(setLesson)
      .catch((e) => setError((e as Error).message));
    api<{ lessons: ListeningLesson[] }>("/listening/lessons")
      .then((r) => {
        const i = r.lessons.findIndex((l) => l.id === id);
        setNextLessonId(i >= 0 ? r.lessons[i + 1]?.id ?? null : null);
      })
      .catch(() => undefined);
  }, [id]);

  async function submit(questionId: string) {
    setBusy(questionId);
    setError(null);
    try {
      const r = await postGraded<AttemptResponse>("/listening/attempt", {
        question_id: questionId,
        answer: answers[questionId] ?? "",
      });
      setResults((prev) => ({ ...prev, [questionId]: r }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const answered = lesson ? lesson.questions.filter((q) => results[q.id]).length : 0;
  const allDone = !!lesson && answered === lesson.questions.length;

  useEffect(() => {
    if (allDone && !transcript) {
      api<{ transcript: string }>(`/listening/lessons/${encodeURIComponent(id)}/transcript`)
        .then((t) => setTranscript(t.transcript))
        .catch(() => undefined);
    }
  }, [allDone, transcript, id]);

  if (!lesson) return error ? <ErrorBox error={error} /> : <LoadingScreen label="Loading lesson" />;

  const lastAttempt = Object.values(results).at(-1);
  const correct = Object.values(results).filter((r) => r.assessment.is_correct).length;

  return (
    <>
      <PageHeader
        back={{ href: "/practice/listening", label: "All lessons" }}
        eyebrow="Listening"
        title={lesson.title}
        meta={
          <>
            <CefrBadge level={lesson.cefr_level} />
            <DifficultyBadge difficulty={lesson.difficulty} />
            <Tag><ClockIcon size={12} /> {Math.round(lesson.duration_seconds)}s</Tag>
          </>
        }
      />

      <div className="narrow stack">
        <AudioPlayer src={lesson.audio_url} fallbackDuration={lesson.duration_seconds} />

        <ProgressBar value={(100 * answered) / lesson.questions.length} label="Questions answered" showValue
          valueText={`${answered} of ${lesson.questions.length}`} tone="blue" size="sm" />

        <ErrorBox error={error} />

        <ol className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {lesson.questions.map((q, i) => {
            const result = results[q.id];
            const submitting = busy === q.id;
            return (
              <li key={q.id} className="card">
                <p className="eyebrow">Question {i + 1}</p>
                <label htmlFor={`q-${q.id}`} className="question-label">{q.question}</label>
                <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(q.id); }}>
                  <input id={`q-${q.id}`} type="text" maxLength={250} value={answers[q.id] ?? ""}
                    disabled={submitting || !!result} placeholder="Answer in your own words"
                    onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))} />
                  {!result && (
                    <button type="submit" className="btn" disabled={busy !== null || !(answers[q.id] ?? "").trim()}>
                      {submitting ? <><Spinner /> Checking</> : "Check"}
                    </button>
                  )}
                </form>
                {result && (
                  <div className="mt-12">
                    <AssessmentView assessment={result.assessment} attemptId={result.attempt_id} />
                  </div>
                )}
              </li>
            );
          })}
        </ol>

        {transcript ? (
          <Callout tone="info" icon={<FileTextIcon size={18} />} title="Transcript">
            <p style={{ margin: 0, lineHeight: 1.7 }}>{transcript}</p>
          </Callout>
        ) : (
          <Callout tone="neutral" icon={<LockIcon size={18} />}>
            The transcript unlocks when you have answered every question.
          </Callout>
        )}

        {allDone && lastAttempt && (
          <section className="card">
            <div className="row" style={{ gap: 12 }}>
              <span className="icon-tile tone-green"><CheckIcon size={20} /></span>
              <div style={{ flex: 1 }}>
                <h2 style={{ margin: 0 }}>Lesson complete</h2>
                <p className="small secondary" style={{ margin: 0 }}>
                  {correct} of {lesson.questions.length} answers correct
                </p>
              </div>
            </div>
            <MasteryChanges changes={lastAttempt.mastery_changes} />
            <div className="btn-row mt-16 stack-mobile">
              {nextLessonId ? (
                <Link className="btn large" href={`/practice/listening/${nextLessonId}`}>
                  Next lesson <ArrowRightIcon size={18} />
                </Link>
              ) : (
                <Link className="btn large" href="/practice/listening">
                  All lessons <ArrowRightIcon size={18} />
                </Link>
              )}
              <Link className="btn ghost large" href="/dashboard">Home</Link>
            </div>
            <NextUp rec={lastAttempt.next_recommendation} />
          </section>
        )}
      </div>
    </>
  );
}
