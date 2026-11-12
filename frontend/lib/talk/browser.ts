/** Real browser implementations of TalkDeps: microphone, level meter, recorder, speech. */

import type { LevelMeter, RecorderLike, StreamLike, TalkDeps } from "./session";
import { ReplyPlayer, serverVoice, SpeechRequestError, type AudioLike } from "./audio";
import type { Synth, Utterance } from "./tts";
import { rms } from "./vad";

export const AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
};

/** Recording formats in order of preference; Whisper (ffmpeg) decodes all of them. */
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

export function pickMimeType(isSupported: (type: string) => boolean): string | undefined {
  return MIME_TYPES.find((t) => {
    try {
      return isSupported(t);
    } catch {
      return false;
    }
  });
}

export function fileNameFor(mimeType: string): string {
  if (mimeType.includes("ogg")) return "voice.ogg";
  if (mimeType.includes("mp4")) return "voice.m4a";
  return "voice.webm";
}

/** iOS Safari only allows speech output started by a tap, which breaks the hands-free loop,
 * so Talk mode shows the manual microphone instead there. */
export function isIOS(nav: Pick<Navigator, "userAgent" | "platform" | "maxTouchPoints">): boolean {
  return /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === "MacIntel" && nav.maxTouchPoints > 1);
}

export type TalkSupport = "ok" | "ios" | "unsupported";

export function talkSupport(): TalkSupport {
  if (typeof window === "undefined") return "unsupported";
  const w = window as typeof window & { webkitAudioContext?: typeof AudioContext };
  const hasMic = !!navigator.mediaDevices?.getUserMedia;
  const hasRecorder = typeof window.MediaRecorder !== "undefined";
  const hasAudio = typeof window.AudioContext !== "undefined" || !!w.webkitAudioContext;
  if (!hasMic || !hasRecorder || !hasAudio) return "unsupported";
  return isIOS(navigator) ? "ios" : "ok";
}

class AnalyserMeter implements LevelMeter {
  private readonly ctx: AudioContext;
  private readonly analyser: AnalyserNode;
  private readonly buffer: Float32Array<ArrayBuffer>;

  constructor(stream: MediaStream) {
    const w = window as typeof window & { webkitAudioContext?: typeof AudioContext };
    const Ctx = window.AudioContext ?? w.webkitAudioContext!;
    this.ctx = new Ctx();
    void this.ctx.resume(); // started from the Talk button (a user gesture)
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.buffer = new Float32Array(this.analyser.fftSize);
    this.ctx.createMediaStreamSource(stream).connect(this.analyser); // not to the speakers
  }

  level(): number {
    this.analyser.getFloatTimeDomainData(this.buffer);
    return rms(this.buffer);
  }

  close(): void {
    if (this.ctx.state !== "closed") void this.ctx.close();
  }
}

/** Speech diagnostics: `[talk-tts]` lines in the console and `window.__talkTtsLog` (last 200),
 * so a report of "the monkey did not speak" comes with the exact event order and error code. */
export function ttsLog(event: string, detail: Record<string, unknown> = {}): void {
  const w = window as typeof window & { __talkTtsLog?: unknown[] };
  const entry = { t: Math.round(performance.now()), event, ...detail };
  (w.__talkTtsLog ??= []).push(entry);
  if (w.__talkTtsLog.length > 200) w.__talkTtsLog.shift();
  console.debug("[talk-tts]", event, detail);
}

function browserSynth(): Synth | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const synth = window.speechSynthesis;
  // Chrome garbage-collects an utterance nobody references and then drops its events (or the
  // speech): keep every utterance until it has finished.
  const live = new Set<SpeechSynthesisUtterance>();
  let voices = synth.getVoices();
  synth.addEventListener?.("voiceschanged", () => { voices = synth.getVoices(); });
  const pickVoice = () => {
    if (!voices.length) voices = synth.getVoices();
    return voices.find((v) => v.lang === "en-US") ?? voices.find((v) => v.lang.startsWith("en"));
  };
  let seq = 0;
  return {
    speak(text: string): Utterance {
      const id = ++seq;
      const handle: Utterance = { text, onstart: null, onend: null, onerror: null };
      const u = new SpeechSynthesisUtterance(text);
      const voice = pickVoice();
      if (voice) u.voice = voice;
      u.lang = voice?.lang ?? "en-US";
      u.rate = 0.95;
      u.pitch = 1.25;
      const t0 = performance.now();
      const ms = () => Math.round(performance.now() - t0);
      u.onstart = () => {
        ttsLog("start", { id, ms: ms() });
        handle.onstart?.();
      };
      u.onend = () => {
        live.delete(u);
        ttsLog("end", { id, ms: ms() });
        handle.onend?.();
      };
      u.onerror = (e) => {
        live.delete(u);
        ttsLog("error", { id, ms: ms(), error: e.error });
        handle.onerror?.(e.error);
      };
      live.add(u);
      if (synth.paused) synth.resume(); // Chrome can get stuck paused
      ttsLog("speak", { id, chars: text.length, voice: voice?.name ?? "(default)", busy: synth.speaking || synth.pending });
      synth.speak(u);
      return handle;
    },
    cancel() {
      ttsLog("cancel", { busy: synth.speaking || synth.pending });
      synth.cancel();
      live.clear();
    },
    busy() {
      return synth.speaking || synth.pending;
    },
  };
}

/** POST /monkey/speech and return the WAV, logging what came back. */
async function fetchSpeech(text: string, signal: AbortSignal): Promise<Blob> {
  const t0 = performance.now();
  let res: Response;
  try {
    res = await fetch("/api/v1/monkey/speech", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      credentials: "same-origin",
      signal,
    });
  } catch (e) {
    ttsLog("speech-request", { error: (e as Error).name });
    throw new SpeechRequestError(null, (e as Error).message);
  }
  const type = res.headers.get("content-type");
  if (!res.ok) {
    ttsLog("speech-request", { status: res.status, type, ms: Math.round(performance.now() - t0) });
    throw new SpeechRequestError(res.status, `speech request failed (${res.status})`);
  }
  const audio = await res.blob();
  ttsLog("speech-request", {
    status: res.status, type, bytes: audio.size, ms: Math.round(performance.now() - t0),
  });
  if (!type?.startsWith("audio/")) throw new SpeechRequestError(res.status, `not audio: ${type}`);
  return audio;
}

let sharedVoice: Synth | null = null;

/** AI Monkey's voice for the whole page: server speech through one shared <audio> element,
 * with the browser's speechSynthesis as the fallback when the server has no voice. */
export function replyVoice(): Synth {
  if (!sharedVoice) {
    const player = new ReplyPlayer(
      () => new Audio() as unknown as AudioLike,
      { create: (b) => URL.createObjectURL(b), revoke: (u) => URL.revokeObjectURL(u) },
      ttsLog,
    );
    sharedVoice = serverVoice({ fetchSpeech, player, fallback: browserSynth(), log: ttsLog });
  }
  return sharedVoice;
}

export function browserTalkDeps(api: {
  transcribe(audio: Blob, fileName: string, signal: AbortSignal): Promise<string>;
  reply(text: string, signal: AbortSignal): Promise<string>;
}, synth: Synth | null): TalkDeps {
  const mimeType = pickMimeType((t) => MediaRecorder.isTypeSupported(t));
  return {
    getUserMedia: () => navigator.mediaDevices.getUserMedia(AUDIO_CONSTRAINTS),
    createMeter: (stream: StreamLike) => new AnalyserMeter(stream as MediaStream),
    createRecorder: (stream: StreamLike) =>
      new MediaRecorder(stream as MediaStream, mimeType ? { mimeType } : undefined) as unknown as RecorderLike,
    transcribe: (audio, signal) => api.transcribe(audio, fileNameFor(audio.type || mimeType || ""), signal),
    reply: api.reply,
    synth,
    log: ttsLog,
    now: () => performance.now(),
    setTimeout: (fn, ms) => window.setTimeout(fn, ms),
    clearTimeout: (h) => window.clearTimeout(h as number),
    setInterval: (fn, ms) => window.setInterval(fn, ms),
    clearInterval: (h) => window.clearInterval(h as number),
  };
}
