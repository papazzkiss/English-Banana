/** Text-to-speech for Talk mode on top of the browser's speechSynthesis.
 *
 * Rules (each one fixes a way Speaking used to end before the monkey had spoken):
 * - Never cancel() right before speak(): if something is still queued, cancel, wait ~150 ms,
 *   then speak (Chrome drops an utterance queued right after cancel()).
 * - A chunk is done only when `end` arrives AFTER `start`. `end` without `start`, or an
 *   `interrupted` / `canceled` error we did not cause, is retried once, never taken as "done".
 * - The fallback timeout (Chrome's `onend` is unreliable) starts at `onstart` and is based on
 *   the length: words × 500 ms + 3 s. Before `start`, we wait up to 5 s for the voice.
 * - `not-allowed` means the browser refuses to speak: no retry; the reply stays as text.
 * - Long replies are split into sentence chunks (Chrome stops utterances after ~15 s). */

export interface Utterance {
  text: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((error: string) => void) | null;
  /** Autoplay refused: waits (without a timeout) until unblock() is called from a click. */
  onblocked?: (() => void) | null;
}

/** A voice: the server voice (audio.ts) or the browser's speechSynthesis (a fake in tests). */
export interface Synth {
  speak(text: string): Utterance;
  cancel(): void;
  /** Something is speaking or queued. */
  busy(): boolean;
  /** Longest chunk per speak() call (default 200 characters). */
  maxChunk?: number;
  /** How long to wait for `start` (default 5 s). */
  startTimeoutMs?: number;
  /** Call synchronously in a click handler so later replies may play without one. */
  unlock?(): void;
  /** From a click: play what autoplay refused. */
  unblock?(): void;
}

export type SpeakOutcome = "done" | "failed" | "cancelled";
export type TtsLog = (event: string, detail?: Record<string, unknown>) => void;

const MAX_CHUNK = 200;
export const START_TIMEOUT_MS = 5000;
export const CANCEL_SETTLE_MS = 150;

/** Split text into sentence-sized chunks of at most `max` characters. */
export function chunkText(text: string, max = MAX_CHUNK): string[] {
  const sentences = text.replace(/\s+/g, " ").trim().match(/[^.!?]+[.!?]*["')\]]*\s*/g) ?? [];
  const chunks: string[] = [];
  let current = "";
  const flush = () => {
    if (current.trim()) chunks.push(current.trim());
    current = "";
  };
  for (const sentence of sentences) {
    if ((current + sentence).length <= max) {
      current += sentence;
      continue;
    }
    flush();
    if (sentence.length <= max) {
      current = sentence;
      continue;
    }
    // A very long sentence: break at commas, then at spaces.
    for (const part of sentence.split(/(?<=,)\s+|\s+/)) {
      if ((current + " " + part).trim().length > max) flush();
      current = current ? `${current} ${part}` : part;
    }
  }
  flush();
  return chunks;
}

/** How long a chunk may run after `onstart` before we stop waiting for `onend`. */
export function speechTimeoutMs(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return words * 500 + 3000;
}

// Letters only Vietnamese uses (ă â đ ê ô ơ ư ĩ ũ, tone marks U+1EA0-U+1EF9); two different
// words with toned Latin-1 vowels also count ("café" stays English, however often it appears).
const VI_LETTER = /[ăâđêôơưĩũ\u1ea0-\u1ef9]/i;
const TONED_WORD = /[^\s.,!?;:"'()]*[àáãèéìíòóõùúýỳ][^\s.,!?;:"'()]*/gi;

/** A sentence in Vietnamese: the server voice (Piper en_US) cannot pronounce it. */
export function isVietnamese(sentence: string): boolean {
  if (VI_LETTER.test(sentence)) return true;
  const toned = new Set((sentence.match(TONED_WORD) ?? []).map((w) => w.toLowerCase()));
  return toned.size >= 2;
}

/** What is read aloud: the reply without its "(Tip: …)" (the tip stays in the chat) and
 * without Vietnamese sentences (shown as text; the voice speaks English only). An all-Vietnamese
 * reply gives "": it is shown, not spoken. */
export function spokenText(reply: string): string {
  const withoutTip = reply.replace(/\s*\(Tip:[^)]*\)/gi, "").trim() || reply;
  const sentences = withoutTip.match(/[^.!?]+[.!?]*["')\]]*\s*/g) ?? [withoutTip];
  const english = sentences.filter((s) => !isVietnamese(s)).join("").replace(/\s+/g, " ").trim();
  if (english) return english;
  return sentences.some(isVietnamese) ? "" : withoutTip;
}

export interface SpeakHandle {
  done: Promise<SpeakOutcome>;
  cancel(): void;
}

type Attempt = "end" | "end-before-start" | "no-start" | "no-end" | "cancelled" | `error:${string}`;

/** Speak `text` chunk by chunk. `onStart` fires once, when the first chunk really starts. */
export function speakChunks(
  synth: Synth,
  text: string,
  opts: {
    onStart?: () => void;
    /** true when autoplay refused and a click is needed; false once it plays. */
    onBlocked?: (blocked: boolean) => void;
    log?: TtsLog;
    setTimer?: (fn: () => void, ms: number) => unknown;
    clearTimer?: (handle: unknown) => void;
  } = {},
): SpeakHandle {
  const setTimer = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
  const clearTimer = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  const log = opts.log ?? (() => undefined);
  let cancelled = false;
  let started = false;
  let blocked = false;
  const startTimeout = synth.startTimeoutMs ?? START_TIMEOUT_MS;
  let abortAttempt: (() => void) | null = null;

  const sleep = (ms: number) => new Promise<void>((resolve) => {
    const h = setTimer(() => { abortAttempt = null; resolve(); }, ms);
    abortAttempt = () => { clearTimer(h); resolve(); };
  });

  const attempt = (chunk: string) => new Promise<Attempt>((resolve) => {
    let chunkStarted = false;
    let timer: unknown = null;
    let settled = false;
    const settle = (result: Attempt) => {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimer(timer);
      abortAttempt = null;
      resolve(result);
    };
    abortAttempt = () => settle("cancelled");
    const u = synth.speak(chunk);
    timer = setTimer(() => settle("no-start"), startTimeout);
    u.onblocked = () => { // no timeout while we wait for the learner's click
      if (settled) return;
      if (timer !== null) clearTimer(timer);
      timer = null;
      blocked = true;
      log("blocked");
      opts.onBlocked?.(true);
    };
    u.onstart = () => {
      if (settled) return;
      if (blocked) {
        blocked = false;
        opts.onBlocked?.(false);
      }
      chunkStarted = true;
      if (timer !== null) clearTimer(timer);
      timer = setTimer(() => settle("no-end"), speechTimeoutMs(chunk));
      if (!started) {
        started = true;
        opts.onStart?.();
      }
    };
    u.onend = () => settle(chunkStarted ? "end" : "end-before-start");
    u.onerror = (error) => settle(`error:${error}`);
  });

  const done = (async (): Promise<SpeakOutcome> => {
    if (synth.busy()) { // something else is queued: cancel it, then give Chrome time to settle
      log("cancel-before-speak");
      synth.cancel();
      await sleep(CANCEL_SETTLE_MS);
    }
    for (const chunk of chunkText(text, synth.maxChunk ?? MAX_CHUNK)) {
      let result: Attempt = "no-start";
      for (let tryNo = 0; tryNo < 2; tryNo++) {
        if (cancelled) return "cancelled";
        result = await attempt(chunk);
        log("chunk", { result, try: tryNo + 1, chars: chunk.length });
        if (result === "end" || result === "no-end" || result === "cancelled") break;
        if (result === "error:not-allowed") return "failed"; // the browser refuses to speak
        if (tryNo === 0) { // end-before-start, no-start, interrupted, canceled, other errors
          if (synth.busy()) synth.cancel();
          await sleep(CANCEL_SETTLE_MS);
        }
      }
      if (cancelled || result === "cancelled") return "cancelled";
      if (result !== "end" && result !== "no-end") return "failed";
    }
    return "done";
  })();

  return {
    done,
    cancel() {
      if (cancelled) return;
      cancelled = true;
      synth.cancel();
      abortAttempt?.();
      if (blocked) opts.onBlocked?.(false);
    },
  };
}
