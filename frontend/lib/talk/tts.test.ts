import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CANCEL_SETTLE_MS, chunkText, isVietnamese, speakChunks, speechTimeoutMs, spokenText, START_TIMEOUT_MS,
  type Synth, type Utterance,
} from "./tts";

describe("chunkText", () => {
  it("keeps normal replies whole", () => {
    expect(chunkText("Hi there! How are you?")).toEqual(["Hi there! How are you?"]);
  });

  it("splits long replies at sentence ends, each chunk at most 200 characters", () => {
    const sentence = "Bananas are yellow and sweet, and monkeys love them a lot. ";
    const chunks = chunkText(sentence.repeat(8));
    expect(chunks.length).toBeGreaterThan(1);
    chunks.forEach((c) => {
      expect(c.length).toBeLessThanOrEqual(200);
      expect(c.endsWith(".")).toBe(true);
    });
    expect(chunks.join(" ")).toBe(sentence.repeat(8).trim());
  });

  it("breaks a single very long sentence at commas or spaces", () => {
    const long = Array.from({ length: 80 }, (_, i) => `word${i}`).join(" ");
    const chunks = chunkText(long);
    expect(chunks.length).toBeGreaterThan(1);
    chunks.forEach((c) => expect(c.length).toBeLessThanOrEqual(200));
    expect(chunks.join(" ")).toBe(long);
  });
});

describe("timing and text", () => {
  it("allows 500 ms per word plus 3 s after the voice starts", () => {
    expect(speechTimeoutMs("Hello there my friend")).toBe(4 * 500 + 3000);
  });

  it("does not read the grammar tip aloud", () => {
    expect(spokenText('Fun! (Tip: we say "I went", not "I goed".) What next?')).toBe("Fun! What next?");
    expect(spokenText("(Tip: only a tip)")).toBe("(Tip: only a tip)"); // never speak nothing
  });

  it("drops Vietnamese sentences: the server voice speaks English only", () => {
    expect(spokenText("Great job! Câu đúng là 'I went'. Do you like school?"))
      .toBe("Great job! Do you like school?");
    expect(spokenText("Thì hiện tại đơn giản dùng cho thói quen.")).toBe(""); // shown, not spoken
    expect(spokenText("I had a café latte at the café.")).toBe("I had a café latte at the café.");
    expect(spokenText("Nice! (Tip: nói 'I went', không nói 'I go'.) What next?")).toBe("Nice! What next?");
  });

  it("recognises Vietnamese", () => {
    expect(isVietnamese("Tôi thích chuối")).toBe(true);
    expect(isVietnamese("I live in Hà Nội")).toBe(true);
    expect(isVietnamese("Let's go to the café")).toBe(false);
  });
});

/** A controllable speech engine: the test fires start / end / error by hand. */
class ManualSynth implements Synth {
  spoken: Utterance[] = [];
  cancelled = 0;
  speaking = false;
  speak(text: string): Utterance {
    const u: Utterance = { text, onstart: null, onend: null, onerror: null };
    this.spoken.push(u);
    return u;
  }
  cancel() { this.cancelled++; this.speaking = false; }
  busy() { return this.speaking; }
}

describe("speakChunks", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const settled = (p: Promise<unknown>) => {
    let value: unknown = "pending";
    p.then((v) => { value = v; });
    return () => value;
  };

  it("is done only when end comes after start, chunk after chunk", async () => {
    const synth = new ManualSynth();
    const onStart = vi.fn();
    const h = speakChunks(synth, "First sentence here. ".repeat(12), { onStart });
    const state = settled(h.done);
    await vi.advanceTimersByTimeAsync(0);
    expect(synth.spoken).toHaveLength(1);
    synth.spoken[0].onstart?.();
    synth.spoken[0].onend?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(synth.spoken).toHaveLength(2);
    synth.spoken[1].onstart?.();
    synth.spoken[1].onend?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(state()).toBe("done");
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([["interrupted"], ["canceled"]])("an unexpected %s is retried, not taken as done", async (code) => {
    const synth = new ManualSynth();
    const h = speakChunks(synth, "Hello there.");
    const state = settled(h.done);
    await vi.advanceTimersByTimeAsync(0);
    synth.spoken[0].onstart?.();
    synth.spoken[0].onerror?.(code);
    await vi.advanceTimersByTimeAsync(CANCEL_SETTLE_MS);
    expect(state()).toBe("pending");
    expect(synth.spoken).toHaveLength(2);
    synth.spoken[1].onstart?.();
    synth.spoken[1].onend?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(state()).toBe("done");
  });

  it("end without start is retried", async () => {
    const synth = new ManualSynth();
    const h = speakChunks(synth, "Hello there.");
    const state = settled(h.done);
    await vi.advanceTimersByTimeAsync(0);
    synth.spoken[0].onend?.();
    await vi.advanceTimersByTimeAsync(CANCEL_SETTLE_MS);
    expect(synth.spoken).toHaveLength(2);
    expect(state()).toBe("pending");
  });

  it("not-allowed fails at once, without retrying", async () => {
    const synth = new ManualSynth();
    const h = speakChunks(synth, "Hello there.");
    await vi.advanceTimersByTimeAsync(0);
    synth.spoken[0].onerror?.("not-allowed");
    expect(await h.done).toBe("failed");
    expect(synth.spoken).toHaveLength(1);
  });

  it("no start within 5 s twice: failed", async () => {
    const synth = new ManualSynth();
    const h = speakChunks(synth, "Hello there.");
    const state = settled(h.done);
    await vi.advanceTimersByTimeAsync(START_TIMEOUT_MS + CANCEL_SETTLE_MS);
    expect(synth.spoken).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(START_TIMEOUT_MS);
    expect(state()).toBe("failed");
  });

  it("when end never comes, moves on after words × 500 ms + 3 s from the start", async () => {
    const synth = new ManualSynth();
    const text = "Hello there my friend.";
    const h = speakChunks(synth, text);
    const state = settled(h.done);
    await vi.advanceTimersByTimeAsync(2000); // slow voice: starts after 2 s
    synth.spoken[0].onstart?.();
    await vi.advanceTimersByTimeAsync(speechTimeoutMs(text) - 10);
    expect(state()).toBe("pending");
    await vi.advanceTimersByTimeAsync(20);
    expect(state()).toBe("done");
  });

  it("never cancels right before speaking: waits after cancelling a queued utterance", async () => {
    const synth = new ManualSynth();
    synth.speaking = true;
    speakChunks(synth, "Hello.");
    await vi.advanceTimersByTimeAsync(0);
    expect(synth.cancelled).toBe(1);
    expect(synth.spoken).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(CANCEL_SETTLE_MS);
    expect(synth.spoken).toHaveLength(1);
  });

  it("does not cancel when nothing is playing", async () => {
    const synth = new ManualSynth();
    speakChunks(synth, "Hello.");
    await vi.advanceTimersByTimeAsync(0);
    expect(synth.cancelled).toBe(0);
    expect(synth.spoken).toHaveLength(1);
  });

  it("cancel() stops speech and resolves as cancelled", async () => {
    const synth = new ManualSynth();
    const h = speakChunks(synth, "A long reply. ".repeat(30));
    await vi.advanceTimersByTimeAsync(0);
    synth.spoken[0].onstart?.();
    h.cancel();
    expect(await h.done).toBe("cancelled");
    expect(synth.cancelled).toBe(1);
    expect(synth.spoken).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
