"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, skillLabel, waitForJob } from "@/lib/api";
import { fileNameFor, pickMimeType } from "@/lib/talk/browser";
import { useLearner } from "@/components/useLearner";
import { AssessmentView, ErrorBox, MasteryChanges } from "@/components/Feedback";
import type { Job, SpeakingPrompt, SpeakingResult } from "@/lib/types";
import {
  ArrowRightIcon,
  CheckIcon,
  ClockIcon,
  FileTextIcon,
  RotateCcwIcon,
  SpeakingIcon,
  StopIcon,
  TargetIcon,
  UploadIcon,
} from "@/components/ui/Icons";
import { CefrBadge, DifficultyBadge, Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Callout, Spinner, Stat } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingScreen } from "@/components/ui/Skeleton";

type Phase = "idle" | "recording" | "recorded" | "uploading" | "processing" | "done";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

const STEPS: { phase: Phase[]; label: string }[] = [
  { phase: ["uploading"], label: "Uploading your recording" },
  { phase: ["processing"], label: "Transcribing and grading (about 15–25 s)" },
];

export default function SpeakingPage() {
  useLearner();
  const { id } = useParams<{ id: string }>();
  const [prompt, setPrompt] = useState<SpeakingPrompt | null | undefined>(undefined);
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [result, setResult] = useState<SpeakingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api<{ prompts: SpeakingPrompt[] }>("/speaking/prompts")
      .then((r) => setPrompt(r.prompts.find((p) => p.id === id) ?? null))
      .catch((e) => {
        setError((e as Error).message);
        setPrompt(null);
      });
  }, [id]);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }, []);

  // Release the microphone if the learner leaves mid-recording.
  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
      stream.current?.getTracks().forEach((t) => t.stop());
    },
    []
  );

  // Stop automatically at the maximum length.
  useEffect(() => {
    if (phase === "recording" && prompt && seconds >= prompt.max_seconds) stop();
  }, [phase, prompt, seconds, stop]);

  async function start() {
    setError(null);
    setResult(null);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = media;
      const mimeType = pickMimeType((t) => MediaRecorder.isTypeSupported(t));
      const rec = new MediaRecorder(media, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      rec.onstop = () => {
        media.getTracks().forEach((t) => t.stop());
        setBlob(new Blob(chunks, { type: rec.mimeType || mimeType || "audio/webm" }));
        setPhase("recorded");
      };
      recorder.current = rec;
      rec.start();
      setSeconds(0);
      setPhase("recording");
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    } catch {
      setError("The microphone is not available. Allow microphone access in your browser, or upload a recording below.");
    }
  }

  async function submit(audio: Blob, name: string) {
    setPhase("uploading");
    setError(null);
    try {
      const form = new FormData();
      form.append("prompt_id", id);
      form.append("audio", audio, name);
      const res = await fetch("/api/v1/speaking/attempt", { method: "POST", body: form, credentials: "same-origin" });
      const job = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(job.error?.message ?? "Upload failed. Please try again.");
      setPhase("processing");
      const done = await waitForJob<SpeakingResult>(job.job_id, (_j: Job<SpeakingResult>) => undefined);
      if (done.status === "failed" || !done.result) throw new Error(done.error ?? "Your recording could not be graded.");
      setResult(done.result);
      setPhase("done");
    } catch (e) {
      setError((e as Error).message);
      setPhase(blob ? "recorded" : "idle");
    }
  }

  const blobUrl = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => {
    if (blobUrl) URL.revokeObjectURL(blobUrl);
  }, [blobUrl]);

  if (prompt === undefined) return <LoadingScreen label="Loading prompt" />;
  if (prompt === null) {
    return error ? (
      <ErrorBox error={error} />
    ) : (
      <EmptyState title="Prompt not found" description="This speaking prompt does not exist any more."
        actionText="All prompts" actionHref="/practice/speaking" />
    );
  }

  const minReached = seconds >= prompt.min_seconds;
  const working = phase === "uploading" || phase === "processing";

  return (
    <>
      <PageHeader
        back={{ href: "/practice/speaking", label: "All prompts" }}
        eyebrow="Speaking"
        title={prompt.title}
        meta={
          <>
            <CefrBadge level={prompt.cefr_level} />
            <DifficultyBadge difficulty={prompt.difficulty} />
            <Tag><ClockIcon size={12} /> {prompt.min_seconds}–{prompt.max_seconds}s</Tag>
          </>
        }
      />

      <div className="narrow stack">
        <section className="card">
          <p className="prompt" style={{ marginTop: 0 }}>{prompt.instruction}</p>
          {prompt.target_grammar && (
            <Callout tone="accent" icon={<TargetIcon size={17} />}>
              Try to use <strong>{prompt.target_grammar_name ?? skillLabel(prompt.target_grammar)}</strong>.
            </Callout>
          )}
        </section>

        {phase !== "done" && (
          <section className="recorder" aria-live="polite">
            {phase === "recording" ? (
              <>
                <div className="rec-timer">
                  <span className="rec-dot" aria-hidden />
                  <span>{clock(seconds)}</span>
                  <span className="small muted" style={{ fontFamily: "var(--font-sans)", fontWeight: 600 }}>
                    / {clock(prompt.max_seconds)}
                  </span>
                </div>
                <div className="audio-wave" aria-hidden>
                  <span className="wave-bar" /><span className="wave-bar" /><span className="wave-bar" />
                  <span className="wave-bar" /><span className="wave-bar" />
                </div>
                <div style={{ width: "100%", maxWidth: 340 }}>
                  <ProgressBar value={(100 * seconds) / prompt.max_seconds} tone={minReached ? "good" : "accent"}
                    label="Recording length" size="sm" />
                  <p className="small muted" style={{ margin: "6px 0 0" }}>
                    {minReached ? "Good length. Stop when you are done." : `Keep going for at least ${prompt.min_seconds - seconds}s more`}
                  </p>
                </div>
                <button type="button" className="btn large danger" onClick={stop}>
                  <StopIcon size={16} /> Stop
                </button>
              </>
            ) : phase === "recorded" && blob && blobUrl ? (
              <>
                <strong>Listen back, then submit</strong>
                <audio controls src={blobUrl} style={{ width: "100%", maxWidth: 420 }} />
                <div className="btn-row center">
                  <button type="button" className="btn large accent" onClick={() => submit(blob, fileNameFor(blob.type))}>
                    Submit for feedback <ArrowRightIcon size={18} />
                  </button>
                  <button type="button" className="btn large ghost" onClick={start}>
                    <RotateCcwIcon size={16} /> Record again
                  </button>
                </div>
              </>
            ) : working ? (
              <>
                <Spinner size={28} />
                <ol className="steps" aria-label="Progress">
                  {STEPS.map((s, i) => {
                    const active = s.phase.includes(phase);
                    const done = phase === "processing" && i === 0;
                    return (
                      <li key={s.label} className="step" data-state={done ? "done" : active ? "active" : "todo"}>
                        <span className="step-mark">{done ? <CheckIcon size={12} /> : active ? <Spinner size={14} /> : null}</span>
                        {s.label}
                      </li>
                    );
                  })}
                </ol>
              </>
            ) : (
              <>
                <button type="button" className="mic-btn big" onClick={start} aria-label="Start recording">
                  <SpeakingIcon size={30} />
                </button>
                <strong>Tap to start recording</strong>
                <span className="small muted">Speak for {prompt.min_seconds}–{prompt.max_seconds} seconds.</span>
              </>
            )}
          </section>
        )}

        {!working && phase !== "recording" && phase !== "done" && (
          <details>
            <summary className="small secondary" style={{ cursor: "pointer", fontWeight: 600 }}>
              <UploadIcon size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
              Upload a recording instead
            </summary>
            <input type="file" accept="audio/*" className="mt-8" aria-label="Audio file"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) submit(f, f.name);
              }} />
          </details>
        )}

        <ErrorBox error={error} />

        {result && (
          <>
            <Callout tone="info" icon={<FileTextIcon size={18} />} title="What we heard">
              <p style={{ margin: 0, fontSize: "1.05rem" }}>“{result.transcript || "…"}”</p>
              <span className="xsmall muted">Transcribed by {result.stt_model} · {Math.round(result.duration_seconds)}s</span>
            </Callout>

            <div className="grid cols-4">
              <Stat label="Fluency" value={<>{Math.round(result.fluency.score)}<small>/100</small></>} tone="blue" />
              <Stat label="Words / min" value={result.fluency.words_per_minute} />
              <Stat label="Filler words" value={result.fluency.filler_count} />
              <Stat label="Long pauses" value={result.fluency.long_pauses} />
            </div>

            <section>
              <h2>Grammar</h2>
              <AssessmentView assessment={result.grammar} attemptId={result.attempt_id} />
              <MasteryChanges changes={result.mastery_changes} />
            </section>

            <div className="btn-row stack-mobile">
              <button type="button" className="btn large" onClick={() => { setBlob(null); setPhase("idle"); setResult(null); }}>
                <RotateCcwIcon size={16} /> Try again
              </button>
              <Link className="btn ghost large" href="/practice/speaking">
                Another prompt <ArrowRightIcon size={18} />
              </Link>
            </div>
          </>
        )}
      </div>
    </>
  );
}
