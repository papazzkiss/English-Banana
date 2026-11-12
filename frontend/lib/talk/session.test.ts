import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  isMeaningful, TALK_ERRORS, TalkSession, type RecorderLike, type TalkDeps, type TalkPhase,
} from "./session";
import type { Synth, Utterance } from "./tts";

// --- fakes ------------------------------------------------------------------------------

class FakeTrack {
  stopped = false;
  stop() { this.stopped = true; }
}

class FakeRecorder implements RecorderLike {
  state: "inactive" | "recording" | "paused" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() { this.state = "recording"; }
  stop() {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["voice"], { type: "audio/webm" }) });
    setTimeout(() => this.onstop?.(), 0); // like the browser: onstop comes later
  }
}

/** Like Chrome: start after 20 ms, end after `autoEndMs` (null: `end` never comes), and
 * cancel() fires `canceled` on the utterance being spoken. `script` overrides the next
 * utterances: an error code fired before `start`, or "end-first" (end without start). */
class FakeSynth implements Synth {
  spoken: Utterance[] = [];
  times: number[] = [];
  cancelTimes: number[] = [];
  cancelled = 0;
  private active: Utterance | null = null;
  constructor(private readonly autoEndMs: number | null = 500, public script: string[] = []) {}
  speak(text: string): Utterance {
    const u: Utterance = { text, onstart: null, onend: null, onerror: null };
    this.spoken.push(u);
    this.times.push(Date.now());
    this.active = u;
    const step = this.script.shift();
    if (step === "blocked") { // autoplay refused until unblock()
      setTimeout(() => u.onblocked?.(), 5);
      this.pendingUnblock = () => {
        setTimeout(() => u.onstart?.(), 5);
        setTimeout(() => { this.active = null; u.onend?.(); }, 1000);
      };
    } else if (step === "end-first") {
      setTimeout(() => { this.active = null; u.onend?.(); }, 5);
    } else if (step) {
      setTimeout(() => { this.active = null; u.onerror?.(step); }, 5);
    } else {
      setTimeout(() => u.onstart?.(), 20);
      if (this.autoEndMs !== null) {
        setTimeout(() => { if (this.active === u) this.active = null; u.onend?.(); }, this.autoEndMs);
      }
    }
    return u;
  }
  cancel() {
    this.cancelled++;
    this.cancelTimes.push(Date.now());
    const u = this.active;
    this.active = null;
    if (u) setTimeout(() => u.onerror?.("canceled"), 0);
  }
  busy() { return this.active !== null; }
  pendingUnblock: (() => void) | null = null;
  unblock() { this.pendingUnblock?.(); this.pendingUnblock = null; }
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function setup(opts: {
  transcripts?: (string | Error)[];
  replies?: (string | Error)[];
  synth?: FakeSynth | null;
  micDenied?: boolean;
} = {}) {
  const tracks: FakeTrack[] = [];
  const recorders: FakeRecorder[] = [];
  const levels = { value: 0.002 };
  const meters: { closed: boolean }[] = [];
  const meter = {
    get value() { return levels.value; }, set value(v: number) { levels.value = v; },
    get closed() { return meters.every((m) => m.closed); },
  };
  const transcripts = [...(opts.transcripts ?? ["I like bananas.", "What about you?", "See you."])];
  const replies = [...(opts.replies ?? ["Me too! Why?", "I love them.", "Bye!"])];
  const signals: AbortSignal[] = [];
  const synth = opts.synth === undefined ? new FakeSynth() : opts.synth;
  const deps: TalkDeps = {
    getUserMedia: vi.fn(async () => {
      if (opts.micDenied) throw new DOMException("denied", "NotAllowedError");
      const own = [new FakeTrack()];
      tracks.push(...own);
      return { getTracks: () => own };
    }),
    createMeter: vi.fn(() => {
      const m = { closed: false, level: () => levels.value, close() { this.closed = true; } };
      meters.push(m);
      return m;
    }),
    createRecorder: vi.fn(() => {
      const r = new FakeRecorder();
      recorders.push(r);
      return r;
    }),
    transcribe: vi.fn(async (_audio: Blob, signal: AbortSignal) => {
      signals.push(signal);
      await new Promise((r) => setTimeout(r, 400));
      const next = transcripts.shift() ?? "";
      if (next instanceof Error) throw next;
      return next;
    }),
    reply: vi.fn(async (_text: string, signal: AbortSignal) => {
      signals.push(signal);
      await new Promise((r) => setTimeout(r, 1000));
      const next = replies.shift() ?? "Okay!";
      if (next instanceof Error) throw next;
      return next;
    }),
    synth,
    now: () => Date.now(),
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    setInterval: (fn, ms) => setInterval(fn, ms),
    clearInterval: (h) => clearInterval(h as ReturnType<typeof setInterval>),
  };
  const phases: TalkPhase[] = [];
  const heard: string[] = [];
  const said: string[] = [];
  const errors: string[] = [];
  const latencies: unknown[] = [];
  const session = new TalkSession(deps, {
    onPhase: (p) => phases.push(p),
    onHeard: (t) => heard.push(t),
    onReply: (t) => said.push(t),
    onLatency: (l) => latencies.push(l),
    onError: (e) => errors.push(e),
  });
  /** Hold the microphone at `level` for `ms`. */
  const hold = async (level: number, ms: number) => {
    meter.value = level;
    await vi.advanceTimersByTimeAsync(ms);
  };
  /** Say something: speech, then enough silence to end the utterance. */
  const utter = async (ms = 1500) => {
    await hold(0.3, ms);
    await hold(0.002, 1300);
  };
  const begin = async () => {
    await session.start();
    await hold(0.002, 600); // calibration
  };
  return { session, deps, tracks, recorders, meter, synth, phases, heard, said, errors, latencies,
    signals, hold, utter, begin };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

// --- the loop -----------------------------------------------------------------------------

describe("TalkSession loop", () => {
  it("listens, hears, transcribes, replies, speaks and listens again, turn after turn", async () => {
    const t = setup();
    await t.begin();
    expect(t.session.phase).toBe("listening");

    for (let turn = 0; turn < 3; turn++) {
      await t.hold(0.3, 400);
      expect(t.session.phase).toBe("hearing");
      await t.hold(0.3, 1100);
      await t.hold(0.002, 1300); // silence -> processing starts on its own (no Send)
      expect(["processing", "thinking"]).toContain(t.session.phase);
      await vi.advanceTimersByTimeAsync(1500); // Whisper + LLM
      expect(t.session.phase).toBe("speaking");
      await vi.advanceTimersByTimeAsync(600); // TTS ends
      await vi.advanceTimersByTimeAsync(400); // + reopen delay
      expect(t.session.phase).toBe("listening");
    }
    expect(t.heard).toEqual(["I like bananas.", "What about you?", "See you."]);
    expect(t.said).toEqual(["Me too! Why?", "I love them.", "Bye!"]);
    expect(t.deps.transcribe).toHaveBeenCalledTimes(3);
    expect(t.deps.reply).toHaveBeenCalledTimes(3);
    expect(t.deps.getUserMedia).toHaveBeenCalledTimes(4); // reopened after each reply
    expect(t.errors).toEqual([]);
    expect(new Set(t.phases)).toEqual(
      new Set(["starting", "listening", "hearing", "processing", "thinking", "speaking"]));
  });

  it("shows a Vietnamese reply as text, speaks only English, and keeps listening", async () => {
    const t = setup({
      transcripts: ["Why is it wrong?", "Okay, thanks."],
      replies: ["Vì 'yesterday' là quá khứ nên dùng 'went'.", "Great! Tiếp tục nhé. Try again?"],
    });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.said).toEqual(["Vì 'yesterday' là quá khứ nên dùng 'went'."]);
    expect(t.synth!.spoken).toHaveLength(0); // the English voice would mangle it
    expect(t.session.phase).toBe("listening"); // no speaking phase, straight back to listening
    expect((t.latencies[0] as { ttsStartMs: number | null }).ttsStartMs).toBeNull();

    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.synth!.spoken.map((u) => u.text)).toEqual(["Great! Try again?"]);
    expect(t.errors).toEqual([]);
  });

  it("reports latency for each reply", async () => {
    const t = setup();
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(3000);
    expect(t.latencies).toHaveLength(1);
    const l = t.latencies[0] as Record<string, number>;
    expect(l.whisperMs).toBe(400);
    expect(l.llmMs).toBe(1000);
    expect(l.ttsStartMs).toBe(20);
    expect(l.recordingMs).toBeGreaterThanOrEqual(1450 + 1200); // detected on the first 50 ms frame
    expect(l.totalMs).toBeGreaterThanOrEqual(1420);
  });

  it("ignores noise shorter than 300 ms: no upload, no reply", async () => {
    const t = setup();
    await t.begin();
    await t.hold(0.3, 150);
    await t.hold(0.002, 1500);
    expect(t.session.phase).toBe("listening");
    expect(t.deps.transcribe).not.toHaveBeenCalled();
  });

  it.each([[""], ["   "], ["you"], ["..."]])(
    "drops an empty or noise transcript %j without a message or an LLM call", async (text) => {
      const t = setup({ transcripts: [text] });
      await t.begin();
      await t.hold(0.3, 400);
      await t.hold(0.002, 1300);
      await vi.advanceTimersByTimeAsync(500);
      expect(t.heard).toEqual([]);
      expect(t.deps.reply).not.toHaveBeenCalled();
      expect(t.session.phase).toBe("listening");
    });

  it("cuts a monologue at 30 s and processes it", async () => {
    const t = setup();
    await t.begin();
    await t.hold(0.3, 30_100);
    expect(["processing", "thinking"]).toContain(t.session.phase);
  });

  it("ignores the microphone while the monkey speaks (no barge-in yet)", async () => {
    const t = setup({ synth: new FakeSynth(4000) });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.session.phase).toBe("speaking");
    await t.hold(0.3, 2000); // the learner (or the echo) talks over it
    expect(t.session.phase).toBe("speaking");
    expect(t.deps.transcribe).toHaveBeenCalledTimes(1);
  });

  it("waits ~300 ms after speech before listening again", async () => {
    const t = setup();
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1400 + 500); // reply + TTS end
    await vi.advanceTimersByTimeAsync(200);
    expect(t.session.phase).toBe("speaking");
    await vi.advanceTimersByTimeAsync(150);
    expect(t.session.phase).toBe("listening");
  });

  it("does not hang when TTS never reports the end", async () => {
    const t = setup({ synth: new FakeSynth(null) });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1400);
    expect(t.session.phase).toBe("speaking");
    await vi.advanceTimersByTimeAsync(6000); // fallback timeout
    expect(t.session.phase).toBe("listening");
  });

  it("without TTS shows the reply as text and listens again", async () => {
    const t = setup({ synth: null });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.said).toEqual(["Me too! Why?"]);
    expect(t.phases).not.toContain("speaking");
    expect(t.session.phase).toBe("listening");
    expect((t.latencies[0] as { ttsStartMs: number | null }).ttsStartMs).toBeNull();
  });

  it("sends one request at a time: voice during thinking is not a second turn", async () => {
    const t = setup();
    await t.begin();
    await t.utter();
    await t.hold(0.3, 800); // still thinking
    await vi.advanceTimersByTimeAsync(3000);
    expect(t.deps.transcribe).toHaveBeenCalledTimes(1);
    expect(t.deps.reply).toHaveBeenCalledTimes(1);
  });
});

// --- errors -------------------------------------------------------------------------------

describe("TalkSession errors", () => {
  it("microphone refused: blocked with a clear message, nothing else starts", async () => {
    const t = setup({ micDenied: true });
    await t.session.start();
    expect(t.session.phase).toBe("blocked");
    expect(t.errors).toEqual([TALK_ERRORS.permission]);
    expect(t.deps.createMeter).not.toHaveBeenCalled();
    expect(t.deps.createRecorder).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(5000);
    expect(t.session.phase).toBe("blocked"); // no automatic retry
  });

  it("Whisper failure: message, back to listening, no LLM call", async () => {
    const t = setup({ transcripts: [new Error("500")] });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(600);
    expect(t.errors).toEqual([TALK_ERRORS.transcribe]);
    expect(t.deps.reply).not.toHaveBeenCalled();
    expect(t.session.phase).toBe("listening");
  });

  it("LLM failure: message, back to listening, and the next turn works", async () => {
    const t = setup({ replies: [new Error("503"), "Hello again!"] });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.errors).toEqual([TALK_ERRORS.reply]);
    expect(t.session.phase).toBe("listening");
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.said).toEqual(["Hello again!"]);
  });
});

// --- cleanup and races --------------------------------------------------------------------

describe("TalkSession cleanup", () => {
  it("end() releases the microphone, audio graph, recorder, speech, timers and requests", async () => {
    const t = setup();
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(500); // now waiting for the LLM
    expect(t.session.phase).toBe("thinking");
    t.session.end();
    expect(t.session.phase).toBe("off");
    expect(t.tracks.every((x) => x.stopped)).toBe(true);
    expect(t.meter.closed).toBe(true);
    expect(t.recorders.every((r) => r.state === "inactive")).toBe(true);
    expect(t.signals.at(-1)?.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(5000); // the aborted LLM call "returns" late
    expect(t.said).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("end() while speaking cancels TTS and never reopens the microphone", async () => {
    const synth = new FakeSynth(5000);
    const t = setup({ synth });
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.session.phase).toBe("speaking");
    t.session.end();
    expect(synth.cancelled).toBeGreaterThan(0);
    const recordersBefore = t.recorders.length;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.session.phase).toBe("off");
    expect(t.recorders.length).toBe(recordersBefore);
  });

  it("ending during the permission prompt stops the stream once it arrives", async () => {
    const t = setup();
    const gum = deferred<{ getTracks: () => FakeTrack[] }>();
    (t.deps.getUserMedia as ReturnType<typeof vi.fn>).mockReturnValueOnce(gum.promise);
    const starting = t.session.start();
    t.session.end();
    const late = [new FakeTrack()];
    gum.resolve({ getTracks: () => late });
    await starting;
    expect(late[0].stopped).toBe(true);
    expect(t.session.phase).toBe("off");
    expect(t.deps.createMeter).not.toHaveBeenCalled();
  });

  it("a reply from an ended session never reaches a new session", async () => {
    const t = setup();
    const slow = deferred<string>();
    (t.deps.reply as ReturnType<typeof vi.fn>).mockImplementationOnce(() => slow.promise);
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(500);
    expect(t.session.phase).toBe("thinking");
    t.session.end();
    await t.begin(); // Talk again: a new generation
    slow.resolve("stale answer");
    await vi.advanceTimersByTimeAsync(100);
    expect(t.said).toEqual([]);
    expect(t.session.phase).toBe("listening");
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.said).toEqual(["Me too! Why?"]);
  });

  it("start() twice does not open a second microphone", async () => {
    const t = setup();
    await t.session.start();
    await t.session.start();
    expect(t.deps.getUserMedia).toHaveBeenCalledTimes(1);
  });
});

describe("TalkSession speech output", () => {
  /** One full turn up to the moment the reply arrives (Whisper 400 ms + LLM 1000 ms). */
  const toReply = async (t: ReturnType<typeof setup>) => {
    await t.begin();
    await t.utter();
    await vi.advanceTimersByTimeAsync(1400);
  };

  it("stays in Speaking until onend comes after onstart, then reopens the mic", async () => {
    const synth = new FakeSynth(4000);
    const t = setup({ synth });
    await toReply(t);
    expect(t.session.phase).toBe("speaking");
    expect(t.tracks.every((x) => x.stopped)).toBe(true); // microphone closed while speaking
    await vi.advanceTimersByTimeAsync(3900);
    expect(t.session.phase).toBe("speaking"); // still talking: never cut short
    await vi.advanceTimersByTimeAsync(150 + 300);
    expect(t.session.phase).toBe("listening");
    expect(t.deps.getUserMedia).toHaveBeenCalledTimes(2);
    expect(t.tracks.at(-1)?.stopped).toBe(false);
    expect(synth.cancelled).toBe(0); // nothing cancelled the monkey
  });

  it("does not speak the grammar tip, but keeps it in the chat", async () => {
    const synth = new FakeSynth();
    const t = setup({ synth, replies: ['Nice! (Tip: we say "I went", not "I goed".)'] });
    await toReply(t);
    expect(t.said[0]).toContain("(Tip:");
    expect(synth.spoken[0].text).toBe("Nice!");
  });

  it.each([["interrupted"], ["canceled"], ["end-first"], ["audio-busy"]])(
    "retries once after %s before the start, instead of taking it as done", async (step) => {
      const synth = new FakeSynth(3000, [step]);
      const t = setup({ synth });
      await toReply(t);
      await vi.advanceTimersByTimeAsync(500);
      expect(t.session.phase).toBe("speaking");
      expect(synth.spoken).toHaveLength(2); // the same reply again
      expect(synth.spoken[1].text).toBe(synth.spoken[0].text);
      await vi.advanceTimersByTimeAsync(3500);
      expect(t.session.phase).toBe("listening");
      expect(t.errors).toEqual([]);
    });

  it("the retry waits after a cancel instead of speaking right after it", async () => {
    const synth = new FakeSynth(3000, ["interrupted"]);
    const t = setup({ synth });
    await toReply(t);
    await vi.advanceTimersByTimeAsync(400);
    expect(synth.spoken).toHaveLength(2);
    expect(synth.times[1] - synth.times[0]).toBeGreaterThanOrEqual(150); // ~150 ms settle time
  });

  it("not-allowed: shows replies as text, says so once, and the loop goes on", async () => {
    const synth = new FakeSynth(500, ["not-allowed"]);
    const t = setup({ synth });
    await toReply(t);
    await vi.advanceTimersByTimeAsync(400);
    expect(t.errors).toEqual([TALK_ERRORS.audio]);
    expect(t.session.phase).toBe("listening");
    expect(synth.spoken).toHaveLength(1); // no retry for a refusal
    await t.utter();
    await vi.advanceTimersByTimeAsync(1500);
    expect(t.said).toHaveLength(2); // second reply shown as text, no second error
    expect(synth.spoken).toHaveLength(1);
    expect(t.errors).toHaveLength(1);
  });

  it("gives up after two failed starts and continues as text", async () => {
    const synth = new FakeSynth(500, ["synthesis-failed", "synthesis-failed"]);
    const t = setup({ synth });
    await toReply(t);
    await vi.advanceTimersByTimeAsync(700);
    expect(synth.spoken).toHaveLength(2);
    expect(t.errors).toEqual([TALK_ERRORS.audio]);
    expect(t.session.phase).toBe("listening");
  });

  it("the fallback timeout counts from onstart and scales with the words", async () => {
    const long = "one two three four five six seven eight nine ten."; // 10 words -> 8 s
    const t = setup({ synth: new FakeSynth(null), replies: [long] });
    await toReply(t);
    await vi.advanceTimersByTimeAsync(20 + 7900);
    expect(t.session.phase).toBe("speaking");
    await vi.advanceTimersByTimeAsync(200 + 300);
    expect(t.session.phase).toBe("listening");
  });

  it("autoplay blocked: waits for the tap (mic stays closed), then finishes and listens", async () => {
    const synth = new FakeSynth(500, ["blocked"]);
    const blocked: boolean[] = [];
    const t = setup({ synth });
    (t.session as unknown as { events: { onAudioBlocked?: (b: boolean) => void } })
      .events.onAudioBlocked = (b) => blocked.push(b);
    await toReply(t);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(blocked).toEqual([true]);
    expect(t.session.phase).toBe("speaking");
    expect(t.tracks.every((x) => x.stopped)).toBe(true);
    t.session.unblockAudio(); // the "🔊 Bấm để nghe" click
    await vi.advanceTimersByTimeAsync(1400);
    expect(blocked).toEqual([true, false]);
    expect(t.session.phase).toBe("listening");
    expect(t.errors).toEqual([]);
  });

  it("cancels something still queued, waits, then speaks", async () => {
    const synth = new FakeSynth(20_000);
    const t = setup({ synth });
    synth.speak("left over from before"); // still busy when the reply arrives
    await toReply(t);
    await vi.advanceTimersByTimeAsync(400);
    expect(synth.cancelled).toBe(1);
    expect(synth.spoken).toHaveLength(2);
    expect(synth.times[1] - synth.cancelTimes[0]).toBeGreaterThanOrEqual(150);
  });
});

describe("isMeaningful", () => {
  it("rejects empty, punctuation, one letter and short hallucinations", () => {
    expect(isMeaningful("", 2000)).toBe(false);
    expect(isMeaningful("...", 2000)).toBe(false);
    expect(isMeaningful("a", 2000)).toBe(false);
    expect(isMeaningful("Thank you.", 600)).toBe(false);
    expect(isMeaningful("Thank you.", 1500)).toBe(true); // said on purpose
    expect(isMeaningful("I like bananas", 900)).toBe(true);
  });
});
