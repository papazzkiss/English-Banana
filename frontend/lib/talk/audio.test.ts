import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReplyPlayer, serverVoice, SILENT_WAV, SpeechRequestError, type AudioLike } from "./audio";
import { speakChunks, type Synth, type Utterance } from "./tts";

/** An <audio> element: play() resolves (or rejects with `refuse`), then `playing` and `ended`. */
class FakeAudio implements AudioLike {
  src = "";
  preload = "";
  error: { code: number } | null = null;
  plays: string[] = [];
  refuse: string[] = []; // e.g. ["NotAllowedError"] rejects the next play()
  paused = 0;
  private listeners = new Map<string, Set<() => void>>();
  constructor(private readonly durationMs = 2000) {}
  play(): Promise<void> {
    this.plays.push(this.src);
    const refusal = this.refuse.shift();
    if (refusal) return Promise.reject(Object.assign(new Error(refusal), { name: refusal }));
    if (this.src !== SILENT_WAV) {
      const src = this.src;
      setTimeout(() => this.src === src && this.emit("playing"), 10);
      setTimeout(() => this.src === src && this.emit("ended"), 10 + this.durationMs);
    }
    return Promise.resolve();
  }
  pause() { this.paused++; }
  load() {}
  removeAttribute(name: string) { if (name === "src") this.src = ""; }
  addEventListener(type: string, fn: () => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(fn);
  }
  removeEventListener(type: string, fn: () => void) { this.listeners.get(type)?.delete(fn); }
  emit(type: string) { [...(this.listeners.get(type) ?? [])].forEach((fn) => fn()); }
  listenerCount() { return [...this.listeners.values()].reduce((n, s) => n + s.size, 0); }
}

function makePlayer(audio = new FakeAudio()) {
  const created: FakeAudio[] = [];
  let n = 0;
  const revoked: string[] = [];
  const player = new ReplyPlayer(
    () => { created.push(audio); return audio; },
    { create: () => `blob:${++n}`, revoke: (u) => revoked.push(u) },
  );
  return { player, audio, created, revoked };
}

const WAV = new Blob([new Uint8Array(2000)], { type: "audio/wav" });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("ReplyPlayer", () => {
  it("unlock() plays a short silence on the shared element", () => {
    const { player, audio } = makePlayer();
    player.unlock();
    expect(audio.plays).toEqual([SILENT_WAV]);
  });

  it("reuses ONE element for every reply, changing only its src", async () => {
    const { player, audio, created, revoked } = makePlayer(new FakeAudio(100));
    const ended = vi.fn();
    player.unlock();
    player.play(WAV, { onPlaying: vi.fn(), onEnded: ended, onError: vi.fn(), onBlocked: vi.fn() });
    await vi.advanceTimersByTimeAsync(200);
    player.play(WAV, { onPlaying: vi.fn(), onEnded: ended, onError: vi.fn(), onBlocked: vi.fn() });
    await vi.advanceTimersByTimeAsync(200);
    expect(created).toHaveLength(1);
    expect(audio.plays).toEqual([SILENT_WAV, "blob:1", "blob:2"]);
    expect(ended).toHaveBeenCalledTimes(2);
    expect(revoked).toContain("blob:1"); // object URLs are released
    expect(audio.listenerCount()).toBe(0);
  });

  it("NotAllowedError -> blocked; resumeBlocked() from a click plays it", async () => {
    const audio = new FakeAudio(100);
    audio.refuse = ["NotAllowedError"];
    const { player } = makePlayer(audio);
    const h = { onPlaying: vi.fn(), onEnded: vi.fn(), onError: vi.fn(), onBlocked: vi.fn() };
    player.play(WAV, h);
    await vi.advanceTimersByTimeAsync(50);
    expect(h.onBlocked).toHaveBeenCalledTimes(1);
    expect(h.onError).not.toHaveBeenCalled();
    expect(player.blocked).toBe(true);
    expect(player.resumeBlocked()).toBe(true);
    await vi.advanceTimersByTimeAsync(200);
    expect(h.onPlaying).toHaveBeenCalledTimes(1);
    expect(h.onEnded).toHaveBeenCalledTimes(1);
  });

  it("reports other play() failures and media errors", async () => {
    const audio = new FakeAudio();
    audio.refuse = ["NotSupportedError"];
    const { player } = makePlayer(audio);
    const onError = vi.fn();
    player.play(WAV, { onPlaying: vi.fn(), onEnded: vi.fn(), onError, onBlocked: vi.fn() });
    await vi.advanceTimersByTimeAsync(0);
    expect(onError).toHaveBeenCalledWith("NotSupportedError");
  });

  it("stop() silences the element and forgets the reply", async () => {
    const { player, audio } = makePlayer();
    const ended = vi.fn();
    player.play(WAV, { onPlaying: vi.fn(), onEnded: ended, onError: vi.fn(), onBlocked: vi.fn() });
    player.stop();
    await vi.advanceTimersByTimeAsync(5000);
    expect(ended).not.toHaveBeenCalled();
    expect(audio.paused).toBeGreaterThan(0);
    expect(player.playing).toBe(false);
  });
});

describe("serverVoice", () => {
  const voiceWith = (fetchSpeech: (t: string, s: AbortSignal) => Promise<Blob>, fallback: Synth | null = null) => {
    const { player, audio } = makePlayer(new FakeAudio(300));
    return { voice: serverVoice({ fetchSpeech, player, fallback }), audio };
  };
  const events = (u: Utterance) => {
    const log: string[] = [];
    u.onstart = () => log.push("start");
    u.onend = () => log.push("end");
    u.onerror = (c) => log.push(`error:${c}`);
    u.onblocked = () => log.push("blocked");
    return log;
  };

  it("fetches the server audio and plays it: start, then end", async () => {
    const fetchSpeech = vi.fn(async () => WAV);
    const { voice } = voiceWith(fetchSpeech);
    const log = events(voice.speak("Hello Lan!"));
    expect(voice.busy()).toBe(true);
    await vi.advanceTimersByTimeAsync(500);
    expect(fetchSpeech).toHaveBeenCalledWith("Hello Lan!", expect.any(AbortSignal));
    expect(log).toEqual(["start", "end"]);
    expect(voice.busy()).toBe(false);
  });

  it("an empty audio file is an error, not silence", async () => {
    const { voice } = voiceWith(async () => new Blob([]));
    const log = events(voice.speak("Hi"));
    await vi.advanceTimersByTimeAsync(10);
    expect(log).toEqual(["error:empty-audio"]);
  });

  it("server without a voice (503) falls back to the browser's speech", async () => {
    const fb: Synth = {
      speak: vi.fn((text: string) => {
        const u: Utterance = { text, onstart: null, onend: null, onerror: null };
        setTimeout(() => u.onstart?.(), 5);
        setTimeout(() => u.onend?.(), 50);
        return u;
      }),
      cancel: vi.fn(), busy: () => false,
    };
    const fetchSpeech = vi.fn(async () => { throw new SpeechRequestError(503, "down"); });
    const { voice } = voiceWith(fetchSpeech, fb);
    const log = events(voice.speak("Hi"));
    await vi.advanceTimersByTimeAsync(100);
    expect(log).toEqual(["start", "end"]);
    voice.speak("Again"); // stays on the fallback: no second request
    expect(fetchSpeech).toHaveBeenCalledTimes(1);
    expect(fb.speak).toHaveBeenCalledTimes(2);
  });

  it("a 401 is not hidden behind the fallback", async () => {
    const { voice } = voiceWith(async () => { throw new SpeechRequestError(401, "signed out"); },
      { speak: vi.fn(), cancel: vi.fn(), busy: () => false } as unknown as Synth);
    const log = events(voice.speak("Hi"));
    await vi.advanceTimersByTimeAsync(10);
    expect(log).toEqual(["error:synthesis-failed"]);
  });

  it("cancel() aborts the request in flight", async () => {
    let signal: AbortSignal | null = null;
    const { voice } = voiceWith((_t, s) => { signal = s; return new Promise(() => undefined); });
    const log = events(voice.speak("Hi"));
    voice.cancel();
    expect(signal!.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(1000);
    expect(log).toEqual([]);
    expect(voice.busy()).toBe(false);
  });

  it("with speakChunks: blocked waits for the click without timing out", async () => {
    const audio = new FakeAudio(300);
    audio.refuse = ["NotAllowedError"];
    const { player } = makePlayer(audio);
    const voice = serverVoice({ fetchSpeech: async () => WAV, player, fallback: null });
    const blocked = vi.fn();
    const h = speakChunks(voice, "Hello there.", { onBlocked: blocked });
    let outcome = "pending";
    h.done.then((o) => { outcome = o; });
    await vi.advanceTimersByTimeAsync(60_000); // the learner looks away for a minute
    expect(blocked).toHaveBeenLastCalledWith(true);
    expect(outcome).toBe("pending");
    voice.unblock?.(); // the "🔊 Bấm để nghe" click
    await vi.advanceTimersByTimeAsync(500);
    expect(blocked).toHaveBeenLastCalledWith(false);
    expect(outcome).toBe("done");
  });
});
