/** AI Monkey's voice: replies are synthesised on the server (Piper, POST /monkey/speech) and
 * played through ONE shared <audio> element, so it sounds the same in every browser. Browsers
 * cannot be relied on to speak by themselves: Brave and Chromium on Linux have no
 * speechSynthesis voices at all (speak() fails with "synthesis-failed" after a few ms).
 *
 * Autoplay: unlock() plays a short silence from the Start Talk / listen click (synchronously,
 * before any await), and every later reply reuses the same element (only its src changes).
 * If play() is still refused (NotAllowedError), the utterance reports "blocked" and waits for
 * resumeBlocked(), which the "🔊 Bấm để nghe" button calls from its click. */

import type { Synth, TtsLog, Utterance } from "./tts";

export const SILENT_WAV = "data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YSADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==";

export interface PlayHandlers {
  onPlaying(): void;
  onEnded(): void;
  onError(code: string): void;
  onBlocked(): void;
}

/** The subset of HTMLAudioElement the player uses (a fake in tests). */
export interface AudioLike {
  src: string;
  preload: string;
  error: { code: number } | null;
  play(): Promise<void>;
  pause(): void;
  load(): void;
  removeAttribute(name: string): void;
  addEventListener(type: string, fn: () => void): void;
  removeEventListener(type: string, fn: () => void): void;
}

export class ReplyPlayer {
  private el: AudioLike | null = null;
  private url: string | null = null;
  private current: (() => void) | null = null; // cleanup of the reply being played
  private pendingPlay: (() => void) | null = null; // retry after NotAllowedError

  constructor(
    private readonly createElement: () => AudioLike,
    private readonly urls: { create(blob: Blob): string; revoke(url: string): void },
    private readonly log: TtsLog = () => undefined,
  ) {}

  get playing(): boolean {
    return this.current !== null;
  }

  get blocked(): boolean {
    return this.pendingPlay !== null;
  }

  private element(): AudioLike {
    if (!this.el) {
      this.el = this.createElement();
      this.el.preload = "auto";
    }
    return this.el;
  }

  /** Call synchronously inside a click handler: lets later replies play without a click. */
  unlock(): void {
    if (this.current) return;
    const el = this.element();
    el.src = SILENT_WAV;
    el.play().then(
      () => this.log("unlock", { ok: true }),
      (e: { name?: string }) => this.log("unlock", { ok: false, error: e?.name }),
    );
  }

  play(audio: Blob, h: PlayHandlers): void {
    this.stop();
    const el = this.element();
    const url = this.urls.create(audio);
    this.url = url;
    let started = false;
    const onPlaying = () => {
      if (started) return;
      started = true;
      this.log("play-start", { bytes: audio.size });
      h.onPlaying();
    };
    const onEnded = () => {
      cleanup();
      this.log("play-end");
      h.onEnded();
    };
    const onError = () => {
      const code = `media-error-${el.error?.code ?? "unknown"}`;
      cleanup();
      this.log("play-error", { error: code });
      h.onError(code);
    };
    const cleanup = () => {
      el.removeEventListener("playing", onPlaying);
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("error", onError);
      if (this.current === cleanup) this.current = null;
      this.pendingPlay = null;
    };
    el.addEventListener("playing", onPlaying);
    el.addEventListener("ended", onEnded);
    el.addEventListener("error", onError);
    this.current = cleanup;
    el.src = url;
    const attempt = () => {
      el.play().catch((e: { name?: string; message?: string }) => {
        if (this.current !== cleanup) return; // stopped meanwhile
        this.log("play-rejected", { error: e?.name, message: e?.message });
        if (e?.name === "NotAllowedError") {
          this.pendingPlay = attempt;
          h.onBlocked();
        } else if (e?.name !== "AbortError") {
          cleanup();
          h.onError(e?.name ?? "play-failed");
        }
      });
    };
    attempt();
  }

  /** From a click: play the reply that autoplay refused. */
  resumeBlocked(): boolean {
    const retry = this.pendingPlay;
    this.pendingPlay = null;
    retry?.();
    return retry !== null;
  }

  stop(): void {
    this.current?.();
    this.current = null;
    this.pendingPlay = null;
    if (this.el) {
      this.el.pause();
      this.el.removeAttribute("src");
      this.el.load();
    }
    if (this.url) {
      this.urls.revoke(this.url);
      this.url = null;
    }
  }
}

export class SpeechRequestError extends Error {
  constructor(public readonly status: number | null, message: string) {
    super(message);
  }
}

/** A Synth that asks the server for audio and plays it. If the server has no voice (404,
 * 5xx, network), it switches to the browser's speechSynthesis for the rest of the page. */
export function serverVoice(opts: {
  fetchSpeech(text: string, signal: AbortSignal): Promise<Blob>;
  player: ReplyPlayer;
  fallback: Synth | null;
  log?: TtsLog;
}): Synth {
  const log = opts.log ?? (() => undefined);
  let inflight: AbortController | null = null;
  let useFallback = false;

  const viaFallback = (fb: Synth, text: string, handle: Utterance) => {
    const u = fb.speak(text);
    u.onstart = () => handle.onstart?.();
    u.onend = () => handle.onend?.();
    u.onerror = (code) => handle.onerror?.(code);
  };

  return {
    maxChunk: 600, // one request per reply
    startTimeoutMs: 20_000, // request + synthesis (the first one also loads the voice)
    speak(text: string): Utterance {
      const handle: Utterance = { text, onstart: null, onend: null, onerror: null, onblocked: null };
      if (useFallback && opts.fallback) {
        viaFallback(opts.fallback, text, handle);
        return handle;
      }
      const ac = new AbortController();
      inflight = ac;
      void (async () => {
        let audio: Blob;
        try {
          audio = await opts.fetchSpeech(text, ac.signal);
        } catch (e) {
          if (ac.signal.aborted) return;
          const status = e instanceof SpeechRequestError ? e.status : null;
          log("speech-failed", { status, message: (e as Error).message });
          if (opts.fallback && (status === null || status === 404 || status >= 500)) {
            useFallback = true;
            log("fallback", { to: "speechSynthesis" });
            viaFallback(opts.fallback, text, handle);
          } else {
            handle.onerror?.("synthesis-failed");
          }
          return;
        } finally {
          if (inflight === ac) inflight = null;
        }
        if (ac.signal.aborted) return;
        if (!audio.size) {
          log("speech-empty");
          handle.onerror?.("empty-audio");
          return;
        }
        opts.player.play(audio, {
          onPlaying: () => handle.onstart?.(),
          onEnded: () => handle.onend?.(),
          onError: (code) => handle.onerror?.(code),
          onBlocked: () => handle.onblocked?.(),
        });
      })();
      return handle;
    },
    cancel() {
      inflight?.abort();
      inflight = null;
      opts.player.stop();
      if (useFallback && opts.fallback?.busy()) opts.fallback.cancel();
    },
    busy() {
      return inflight !== null || opts.player.playing || (useFallback && !!opts.fallback?.busy());
    },
    unlock() {
      opts.player.unlock();
    },
    unblock() {
      opts.player.resumeBlocked();
    },
  };
}
