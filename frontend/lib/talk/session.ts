/** Talk mode: a hands-free voice conversation with AI Monkey.
 *
 *   listening ─(voice)→ hearing ─(silence ≥ 1.2 s)→ processing (Whisper) → thinking (LLM)
 *       ↑                  │ (too short: noise)                               │
 *       └──────────────────┴────── 300 ms after TTS ends ←── speaking ←────────┘
 *
 * Every browser dependency is injected (TalkDeps), so the whole loop is unit-tested with fakes.
 * Each start() opens a new generation: work from an older generation (a late Whisper or LLM
 * response, a timer) is dropped, so it can never write into a newer conversation.
 *
 * While the monkey speaks, the microphone is closed (as the tap-to-talk mode always did): an
 * open microphone with echo cancellation can make the OS duck or mute speech output, and the
 * monkey must not hear itself. It reopens only after speech really ended (see tts.ts).
 *
 * Barge-in (talking over the monkey) is not enabled yet. The hook is `bargeIn` in the config:
 * it would keep the microphone open while speaking and, on `speech_start`, cancel TTS and go
 * to `hearing`. */

import { speakChunks, spokenText, type SpeakHandle, type Synth, type TtsLog } from "./tts";
import { VAD_DEFAULTS, VoiceActivityDetector, type VadConfig } from "./vad";

export type TalkPhase =
  | "off"
  | "starting"
  | "listening"
  | "hearing"
  | "processing"
  | "thinking"
  | "speaking"
  | "blocked"; // microphone permission refused: needs the user, no automatic retry

export interface Latency {
  recordingMs: number;
  whisperMs: number;
  llmMs: number;
  ttsStartMs: number | null; // null when there is no TTS, or it never reported starting
  totalMs: number; // end of recording -> monkey starts talking (or the reply is shown)
}

export interface TalkConfig extends VadConfig {
  frameMs: number;
  reopenDelayMs: number; // wait after TTS before listening again (avoid hearing the echo)
  idleRestartMs: number; // restart the recorder after this much silence (bounds the upload)
  releaseMicWhileSpeaking: boolean;
  bargeIn: boolean; // reserved: not implemented yet
}

export const TALK_DEFAULTS: TalkConfig = {
  ...VAD_DEFAULTS,
  frameMs: 50,
  reopenDelayMs: 300,
  idleRestartMs: 10_000,
  releaseMicWhileSpeaking: true,
  bargeIn: false,
};

export const TALK_ERRORS = {
  permission: "Microphone permission is required for Talk mode.",
  transcribe: "I couldn't understand that. Try again.",
  reply: "Sorry, I couldn't respond right now.",
  unsupported: "Talk mode needs a microphone and a recent browser.",
  audio: "I couldn't play my voice here, so my replies are shown as text.",
} as const;

// --- the browser surface Talk mode needs -------------------------------------------------

export interface TrackLike { stop(): void }
export interface StreamLike { getTracks(): TrackLike[] }
export interface RecorderLike {
  readonly state: "inactive" | "recording" | "paused";
  readonly mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  start(): void;
  stop(): void;
}
export interface LevelMeter {
  /** Current microphone level, RMS 0..1. */
  level(): number;
  close(): void;
}

export interface TalkDeps {
  getUserMedia(): Promise<StreamLike>;
  createMeter(stream: StreamLike): LevelMeter;
  createRecorder(stream: StreamLike): RecorderLike;
  transcribe(audio: Blob, signal: AbortSignal): Promise<string>;
  /** Send the learner's words; resolve with the monkey's reply. */
  reply(text: string, signal: AbortSignal): Promise<string>;
  synth: Synth | null;
  /** Diagnostics for speech output (the browser implementation logs to the console). */
  log?: TtsLog;
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  setInterval(fn: () => void, ms: number): unknown;
  clearInterval(handle: unknown): void;
}

export interface TalkEvents {
  onPhase?(phase: TalkPhase): void;
  /** The learner's transcribed words, before the monkey is asked. */
  onHeard?(text: string): void;
  /** The monkey's reply, as soon as it arrives (before it is spoken). */
  onReply?(text: string): void;
  /** Timings for the last reply, once the monkey starts talking (or it is shown). */
  onLatency?(latency: Latency): void;
  onError?(message: string): void;
  /** Autoplay refused the reply: show a "tap to listen" button that calls unblockAudio(). */
  onAudioBlocked?(blocked: boolean): void;
}

/** Whisper's usual output for noise or silence: never worth a reply. */
const NOISE_TRANSCRIPTS = /^(you|thank you|thanks for watching|bye|\.+|uh+|um+|hmm+)[.!?]*$/i;

export function isMeaningful(text: string, speechMs: number): boolean {
  const t = text.trim();
  if (!/[a-z]/i.test(t) || t.replace(/[^a-z]/gi, "").length < 2) return false;
  return !(speechMs < 1000 && NOISE_TRANSCRIPTS.test(t));
}

export class TalkSession {
  readonly config: TalkConfig;
  private _phase: TalkPhase = "off";
  private generation = 0;
  private stream: StreamLike | null = null;
  private meter: LevelMeter | null = null;
  private recorder: RecorderLike | null = null;
  private chunks: Blob[] = [];
  private vad: VoiceActivityDetector;
  private frameTimer: unknown = null;
  private timers = new Set<unknown>();
  private abort: AbortController | null = null;
  private speech: SpeakHandle | null = null;
  private listeningSince = 0;
  private speechStartedAt = 0;
  private audioFailed = false;

  constructor(private readonly deps: TalkDeps, private readonly events: TalkEvents = {},
    config: Partial<TalkConfig> = {}) {
    this.config = { ...TALK_DEFAULTS, ...config };
    this.vad = new VoiceActivityDetector(this.config);
  }

  get phase(): TalkPhase {
    return this._phase;
  }

  get active(): boolean {
    return this._phase !== "off" && this._phase !== "blocked";
  }

  /** Ask for the microphone and start listening. Call from a user gesture. */
  async start(): Promise<void> {
    if (this.active) return;
    const gen = ++this.generation;
    this.audioFailed = false;
    this.setPhase("starting");
    this.vad = new VoiceActivityDetector(this.config);
    if (!(await this.openMic(gen))) return;
    this.frameTimer = this.deps.setInterval(() => this.frame(gen), this.config.frameMs);
  }

  /** Open the microphone and start listening. False if Talk cannot go on. */
  private async openMic(gen: number): Promise<boolean> {
    let stream: StreamLike;
    try {
      stream = await this.deps.getUserMedia();
    } catch {
      if (gen !== this.generation) return false;
      this.release();
      this.setPhase("blocked");
      this.events.onError?.(TALK_ERRORS.permission);
      return false;
    }
    if (gen !== this.generation) { // ended while the permission prompt was open
      stream.getTracks().forEach((t) => t.stop());
      return false;
    }
    this.stream = stream;
    try {
      this.meter = this.deps.createMeter(stream);
      this.listen(gen);
    } catch { // no Web Audio, or MediaRecorder cannot record this stream
      this.release();
      this.setPhase("blocked");
      this.events.onError?.(TALK_ERRORS.unsupported);
      return false;
    }
    return true;
  }

  /** Close the microphone (the frame timer keeps running and finds no meter). */
  private closeMic(): void {
    this.discardRecorder();
    this.meter?.close();
    this.meter = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  /** From a click: play the reply that autoplay refused. */
  unblockAudio(): void {
    this.deps.synth?.unblock?.();
  }

  /** Stop everything: recorder, microphone, audio graph, speech, timers, requests. */
  end(): void {
    this.generation++;
    this.release();
    this.setPhase("off");
  }

  // --- the loop -------------------------------------------------------------------------

  private listen(gen: number): void {
    if (gen !== this.generation || !this.stream) return;
    this.vad.resetUtterance();
    this.startRecorder();
    this.listeningSince = this.deps.now();
    this.setPhase("listening");
  }

  private frame(gen: number): void {
    if (gen !== this.generation || !this.meter) return;
    // The microphone is ignored unless we are waiting for the learner (no barge-in yet).
    if (this._phase !== "listening" && this._phase !== "hearing") return;
    const now = this.deps.now();
    const event = this.vad.push(this.meter.level(), now);
    if (!event) {
      if (this._phase === "listening" && now - this.listeningSince >= this.config.idleRestartMs) {
        this.startRecorder(); // keep the eventual upload small
        this.listeningSince = now;
      }
      return;
    }
    switch (event.type) {
      case "speech_start":
        this.speechStartedAt = event.at;
        this.setPhase("hearing");
        break;
      case "noise":
        this.listen(gen); // drop the noise from the recording too
        break;
      case "speech_end":
      case "max_length":
        void this.process(gen, event.speechMs);
        break;
    }
  }

  private async process(gen: number, speechMs: number): Promise<void> {
    this.setPhase("processing");
    const stoppedAt = this.deps.now();
    const recordingMs = stoppedAt - this.speechStartedAt;
    const audio = await this.stopRecorder();
    if (gen !== this.generation) return;
    if (!audio || audio.size === 0) return this.listen(gen);

    this.abort = new AbortController();
    const signal = this.abort.signal;
    let text: string;
    const t0 = this.deps.now();
    try {
      text = await this.deps.transcribe(audio, signal);
    } catch {
      if (gen !== this.generation) return;
      this.events.onError?.(TALK_ERRORS.transcribe);
      return this.listen(gen);
    }
    if (gen !== this.generation) return;
    const whisperMs = this.deps.now() - t0;
    if (!isMeaningful(text, speechMs)) return this.listen(gen); // no message, no LLM call

    text = text.trim();
    this.events.onHeard?.(text);
    this.setPhase("thinking");
    let reply: string;
    const t1 = this.deps.now();
    try {
      reply = await this.deps.reply(text, signal);
    } catch {
      if (gen !== this.generation) return;
      this.events.onError?.(TALK_ERRORS.reply);
      return this.listen(gen);
    }
    if (gen !== this.generation) return;
    const llmMs = this.deps.now() - t1;
    this.abort = null;
    await this.speak(gen, reply, { recordingMs, whisperMs, llmMs, stoppedAt });
  }

  private async speak(gen: number, reply: string,
    t: { recordingMs: number; whisperMs: number; llmMs: number; stoppedAt: number }): Promise<void> {
    const shownAt = this.deps.now();
    this.events.onReply?.(reply);
    let reported = false;
    const report = (ttsStartMs: number | null) => {
      if (reported || gen !== this.generation) return;
      reported = true;
      this.events.onLatency?.({
        recordingMs: t.recordingMs, whisperMs: t.whisperMs, llmMs: t.llmMs, ttsStartMs,
        totalMs: shownAt + (ttsStartMs ?? 0) - t.stoppedAt,
      });
    };
    const spoken = spokenText(reply);
    // No usable TTS, or nothing it can say (a Vietnamese reply): the reply is shown as text.
    if (!this.deps.synth || this.audioFailed || !spoken) {
      report(null);
      return this.listen(gen);
    }
    this.setPhase("speaking");
    if (this.config.releaseMicWhileSpeaking && !this.config.bargeIn) this.closeMic();
    this.speech = speakChunks(this.deps.synth, spoken, {
      onStart: () => report(this.deps.now() - shownAt),
      onBlocked: (blocked) => this.events.onAudioBlocked?.(blocked),
      log: this.deps.log,
      setTimer: (fn, ms) => this.later(fn, ms),
      clearTimer: (h) => this.cancelTimer(h),
    });
    const outcome = await this.speech.done;
    this.speech = null;
    if (gen !== this.generation || outcome === "cancelled") return;
    report(null);
    if (outcome === "failed" && !this.audioFailed) { // e.g. "not-allowed": keep going as text
      this.audioFailed = true;
      this.events.onError?.(TALK_ERRORS.audio);
    }
    this.later(() => void this.resumeListening(gen), this.config.reopenDelayMs);
  }

  private async resumeListening(gen: number): Promise<void> {
    if (gen !== this.generation) return;
    if (this.stream) return this.listen(gen);
    await this.openMic(gen);
  }

  // --- recorder & cleanup ------------------------------------------------------------------

  private startRecorder(): void {
    this.discardRecorder();
    if (!this.stream) return;
    const rec = this.deps.createRecorder(this.stream);
    this.chunks = [];
    rec.ondataavailable = (e) => { if (e.data.size) this.chunks.push(e.data); };
    this.recorder = rec;
    rec.start();
  }

  private stopRecorder(): Promise<Blob | null> {
    const rec = this.recorder;
    this.recorder = null;
    if (!rec || rec.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      rec.onstop = () => {
        const chunks = this.chunks;
        this.chunks = [];
        resolve(chunks.length ? new Blob(chunks, { type: rec.mimeType || "audio/webm" }) : null);
      };
      rec.stop();
    });
  }

  private discardRecorder(): void {
    const rec = this.recorder;
    this.recorder = null;
    this.chunks = [];
    if (rec) {
      rec.ondataavailable = null;
      rec.onstop = null;
      if (rec.state !== "inactive") rec.stop();
    }
  }

  private later(fn: () => void, ms: number): unknown {
    const handle = this.deps.setTimeout(() => {
      this.timers.delete(handle);
      fn();
    }, ms);
    this.timers.add(handle);
    return handle;
  }

  private cancelTimer(handle: unknown): void {
    this.deps.clearTimeout(handle);
    this.timers.delete(handle);
  }

  private release(): void {
    this.abort?.abort();
    this.abort = null;
    if (this.speech) this.speech.cancel(); // cancels TTS
    else if (this.deps.synth?.busy()) this.deps.synth.cancel();
    this.speech = null;
    this.discardRecorder();
    if (this.frameTimer !== null) this.deps.clearInterval(this.frameTimer);
    this.frameTimer = null;
    this.timers.forEach((h) => this.deps.clearTimeout(h));
    this.timers.clear();
    this.meter?.close();
    this.meter = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  private setPhase(phase: TalkPhase): void {
    if (this._phase === phase) return;
    this._phase = phase;
    this.events.onPhase?.(phase);
  }
}

