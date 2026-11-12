"use client";

import { useEffect, useRef } from "react";
import { useLearner } from "@/components/useLearner";
import { ErrorBox } from "@/components/Feedback";
import { MonkeyAvatar, type MonkeyState } from "@/components/MonkeyAvatar";
import { useMonkey } from "@/components/MonkeyProvider";
import { TutorSettings } from "@/components/TutorSettings";
import { spokenText } from "@/lib/talk/tts";
import type { Latency, TalkPhase } from "@/lib/talk/session";
import { PageHeader } from "@/components/ui/PageHeader";
import { Segmented } from "@/components/ui/Segmented";
import {
  PlayIcon,
  RotateCcwIcon,
  SpeakingIcon,
  StopIcon,
  VolumeIcon,
} from "@/components/ui/Icons";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

const TALK_STATUS: Record<TalkPhase, string> = {
  off: "Tap 'Start Talk', then speak freely. No buttons needed.",
  starting: "Requesting microphone permission…",
  listening: "Listening… start speaking anytime.",
  hearing: "Hearing your voice… pause when you're done.",
  processing: "Transcribing your speech…",
  thinking: "AI Monkey is formulating a reply…",
  speaking: "AI Monkey is replying…",
  blocked: "Talk mode requires microphone permission.",
};

const STEPS = [
  ["listening", "Listening"],
  ["hearing", "Hearing"],
  ["thinking", "Thinking"],
  ["speaking", "Speaking"],
] as const;

function stepOf(phase: TalkPhase): string | null {
  if (phase === "processing") return "thinking";
  return STEPS.some(([p]) => p === phase) ? phase : null;
}

function LatencyLine({ latency }: { latency: Latency }) {
  const parts = [
    `rec ${secs(latency.recordingMs)}`,
    `whisper ${secs(latency.whisperMs)}`,
    `llm ${secs(latency.llmMs)}`,
    latency.ttsStartMs === null ? "tts —" : `tts ${secs(latency.ttsStartMs)}`,
    `total ${secs(latency.totalMs)}`,
  ];
  return (
    <small
      className="latency"
      title="Recording, Whisper, LLM, time until speech starts, and total wait"
      style={{ opacity: 0.7, fontSize: "0.74rem", display: "block", marginTop: 4 }}
    >
      {parts.join(" · ")}
    </small>
  );
}

// The last one shows that questions in Vietnamese work too.
const ICEBREAKERS = [
  "How are you doing today?",
  "Tell me an interesting fun fact",
  "Help me practise everyday English",
  "What is your favourite food?",
  "Giải thích thì hiện tại đơn giản cho tôi",
];

export default function MonkeyPage() {
  useLearner();
  const m = useMonkey();
  const logEnd = useRef<HTMLDivElement>(null);
  const voice = m.mode === "voice";
  const talking = m.talkPhase !== "off" && m.talkPhase !== "blocked";
  const handsFree = voice && m.talkSupport === "ok";

  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [m.messages.length, m.pending, m.talkPhase]);

  if (m.enabled === false) {
    return (
      <div className="card" style={{ marginTop: 24, textAlign: "center", padding: 32 }}>
        <h3>AI Monkey is currently disabled in configuration.</h3>
      </div>
    );
  }

  const avatar: MonkeyState = talking
    ? (
        {
          starting: "idle",
          listening: "listening",
          hearing: "hearing",
          processing: "thinking",
          thinking: "thinking",
          speaking: "talking",
        } as const
      )[m.talkPhase as Exclude<TalkPhase, "off" | "blocked">]
    : m.mic === "recording"
    ? "listening"
    : m.pending || m.mic === "transcribing"
    ? "thinking"
    : m.speaking
    ? "talking"
    : "idle";

  const status = m.audioBlocked
    ? "Your browser blocked the sound. Tap below to hear AI Monkey."
    : handsFree
    ? TALK_STATUS[m.talkPhase]
    : m.mic === "recording"
    ? `Listening… ${clock(m.seconds)} · Tap the mic again to send`
    : m.mic === "transcribing"
    ? "Transcribing your speech…"
    : m.pending
    ? "AI Monkey is thinking…"
    : m.speaking
    ? "AI Monkey is speaking…"
    : voice
    ? "Tap the mic and say something!"
    : null; // text mode, idle: the greeting bubble already says what to do

  const busy = m.pending || m.mic === "transcribing";
  const step = stepOf(m.talkPhase);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!m.draft.trim() || busy || talking) return;
    const text = m.draft;
    m.setDraft("");
    m.send(text);
  }

  const micButton = (big = false) => (
    <button
      type="button"
      className={`mic-btn${big ? " big" : ""}${m.mic === "recording" ? " live" : ""}`}
      onClick={() => (m.mic === "recording" ? m.stopMic() : m.startMic())}
      disabled={m.mic === "transcribing" || m.pending || talking}
      aria-label={m.mic === "recording" ? "Stop recording and send" : "Record voice message"}
      aria-pressed={m.mic === "recording"}
      title={talking ? "Talk mode is listening. End Talk to use the manual microphone." : undefined}
    >
      {m.mic === "recording" ? <StopIcon size={big ? 24 : 18} /> : <SpeakingIcon size={big ? 26 : 20} />}
    </button>
  );

  return (
    <div className="monkey-page">
      <PageHeader
        title="AI Monkey"
        description="Relaxed English practice. Talk or type about anything you like; nothing here is graded."
        actions={
          <>
            <Segmented
              label="Chat mode"
              value={voice ? "voice" : "text"}
              onChange={(v) => (v === "voice" ? m.setMode("voice") : m.setMode("text"))}
              options={[
                { value: "text", label: "Text chat" },
                { value: "voice", label: "Voice talk" },
              ]}
            />
            <button
              type="button"
              className="btn small ghost"
              onClick={m.clear}
              disabled={!m.messages.length || busy || talking}
            >
              <RotateCcwIcon size={14} />
              <span>New chat</span>
            </button>
          </>
        }
      />

      <TutorSettings prefs={m.prefs} onChange={m.setPrefs} />

      {(voice || status) && (
      <section
        className={`card monkey-stage${voice ? " voice" : ""}`}
        data-talk-phase={m.talkPhase}
        style={
          talking && m.talkPhase === "speaking"
            ? { background: "color-mix(in srgb, var(--surface-1) 90%, var(--accent) 10%)" }
            : undefined
        }
      >
        <button
          type="button"
          className="avatar-btn"
          onClick={m.stopSpeaking}
          aria-label={m.speaking ? "Stop AI Monkey talking" : "AI Monkey"}
          disabled={!m.speaking}
          title={m.speaking ? "Click to mute" : undefined}
        >
          <MonkeyAvatar state={avatar} size={voice ? 180 : 100} />
        </button>

        {status && (
          <p className="monkey-status" role="status" aria-live="polite">
            {status}
          </p>
        )}

        {m.audioBlocked && (
          <button type="button" className="btn talk-btn accent" onClick={m.unblockAudio}>
            <VolumeIcon size={18} />
            <span>Click to unblock audio</span>
          </button>
        )}

        {handsFree && (
          <>
            <div className="talk-steps" aria-label="Talk state">
              {STEPS.map(([id, label]) => (
                <span
                  key={id}
                  aria-current={step === id ? "step" : undefined}
                  style={{
                    background: step === id ? "var(--ink-button)" : undefined,
                    color: step === id ? "var(--ink-button-text)" : undefined,
                  }}
                >
                  {label}
                </span>
              ))}
            </div>

            {talking ? (
              <button
                type="button"
                className="btn talk-btn end"
                onClick={m.endTalk}
              >
                <StopIcon size={16} /> End talk
              </button>
            ) : (
              <button
                type="button"
                className="btn talk-btn accent"
                onClick={m.startTalk}
              >
                <PlayIcon size={16} /> Start hands-free talk
              </button>
            )}

            {!m.canSpeak && (
              <p className="small muted">
                Your browser speech synthesis is unavailable; text replies appear below.
              </p>
            )}
          </>
        )}

        {voice && m.talkSupport === "ios" && (
          <>
            <p className="small muted">
              Hands-free Talk is not available on iOS Safari yet. Tap the mic, speak, and tap
              again to send.
            </p>
            {micButton(true)}
          </>
        )}

        {voice && m.talkSupport === "unsupported" && (
          <>
            <p className="small muted">
              This browser does not support hands-free Web Audio VAD. Use the push-to-talk mic.
            </p>
            {micButton(true)}
          </>
        )}
      </section>
      )}

      <ErrorBox error={m.error} />

      {/* Chat Log */}
      <section className="card monkey-log" aria-label="Conversation with AI Monkey">
        <div className="chat">
          {m.messages.length === 0 && (
            <div
              className="bubble assistant"
              style={{
                background: "var(--surface-2)",
                padding: "18px 22px",
                borderBottomLeftRadius: 4,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <MonkeyAvatar mini size={22} />
                <strong style={{ color: "var(--accent-text)" }}>AI Monkey</strong>
              </div>
              <p style={{ margin: 0, fontSize: "1.05rem", lineHeight: 1.5 }}>
                Hi there! I&apos;m AI Monkey. Ask me anything, tell me about your day, or just
                chat in English. Type below or tap the microphone.
              </p>

              <div style={{ marginTop: 16 }}>
                <span className="small muted" style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>
                  Try one of these:
                </span>
                <div className="btn-row" style={{ gap: 8 }}>
                  {ICEBREAKERS.map((text) => (
                    <button
                      key={text}
                      type="button"
                      className="chip"
                      style={{ cursor: "pointer", padding: "6px 14px", fontSize: "0.85rem", fontWeight: 600 }}
                      onClick={() => {
                        m.setDraft(text);
                        m.send(text);
                      }}
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {m.messages.map((msg) => (
            <div
              key={msg.id}
              className={`bubble ${msg.role === "monkey" ? "assistant" : "learner"}`}
              style={{
                position: "relative",
              }}
            >
              {msg.role === "monkey" && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <MonkeyAvatar mini size={18} />
                  <span className="small muted" style={{ fontWeight: 700, fontSize: "0.74rem" }}>
                    AI Monkey
                  </span>
                </div>
              )}
              <div style={{ fontSize: "1rem" }}>{msg.text}</div>
              {msg.notice && (
                <span className="tutor-notice" role="status">
                  {msg.notice}
                </span>
              )}
              {msg.role === "monkey" && m.canSpeak && !talking && spokenText(msg.text) !== "" && (
                <button
                  type="button"
                  className="link-btn small speak-btn"
                  onClick={() => m.speak(msg.text)}
                  aria-label="Read this reply aloud"
                  title="Read aloud"
                >
                  <VolumeIcon size={14} />
                </button>
              )}
              {msg.latency && <LatencyLine latency={msg.latency} />}
            </div>
          ))}

          {(m.pending || m.talkPhase === "thinking" || m.talkPhase === "processing") && (
            <div className="bubble assistant typing" aria-label="AI Monkey is thinking">
              <span />
              <span />
              <span />
            </div>
          )}
          <div ref={logEnd} />
        </div>
      </section>

      {/* Input Row */}
      <form className="monkey-input" onSubmit={submit}>
        <textarea
          value={m.draft}
          onChange={(e) => m.setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={
            talking
              ? "Talk mode active: speak freely without pressing buttons. End Talk to type."
              : m.mic === "recording"
              ? "Listening to your voice…"
              : "Type in English or Vietnamese, then press Enter to send"
          }
          rows={1}
          maxLength={1000}
          disabled={talking}
          aria-label="Message to AI Monkey"
        />
        {micButton()}
        <button
          className="btn accent"
          type="submit"
          disabled={!m.draft.trim() || busy || talking}
          style={{ fontWeight: 700, minWidth: 80 }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
