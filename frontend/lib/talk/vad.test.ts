import { describe, expect, it } from "vitest";
import { rms, VoiceActivityDetector } from "./vad";

const QUIET = 0.002;
const LOUD = 0.2;

/** Feed `level` every 50 ms for `ms`; return the events. */
function feed(vad: VoiceActivityDetector, clock: { t: number }, level: number, ms: number) {
  const events = [];
  for (let i = 0; i < ms / 50; i++) {
    clock.t += 50;
    const e = vad.push(level, clock.t);
    if (e) events.push(e);
  }
  return events;
}

function calibrated(level = QUIET) {
  const vad = new VoiceActivityDetector();
  const clock = { t: 0 };
  const events = feed(vad, clock, level, 550);
  return { vad, clock, events };
}

describe("VoiceActivityDetector", () => {
  it("calibrates the threshold from ~500 ms of background noise", () => {
    const { vad, events } = calibrated(0.01);
    expect(events).toEqual([{ type: "calibrated", threshold: expect.closeTo(0.03, 5) }]);
    expect(vad.calibrated).toBe(true);
    // a silent room still gets a sensible minimum threshold
    expect(calibrated(0).vad.threshold).toBe(0.012);
  });

  it("ignores speech-like sound during calibration", () => {
    const vad = new VoiceActivityDetector();
    const clock = { t: 0 };
    expect(feed(vad, clock, LOUD, 450).filter((e) => e.type === "speech_start")).toEqual([]);
  });

  it("detects an utterance and ends it after 1200 ms of silence", () => {
    const { vad, clock } = calibrated();
    const start = feed(vad, clock, LOUD, 800);
    expect(start).toEqual([{ type: "speech_start", at: expect.any(Number) }]);
    expect(feed(vad, clock, QUIET, 1100)).toEqual([]); // not yet
    const end = feed(vad, clock, QUIET, 200);
    expect(end).toEqual([{ type: "speech_end", speechMs: expect.any(Number), at: expect.any(Number) }]);
    expect((end[0] as { speechMs: number }).speechMs).toBeGreaterThanOrEqual(700);
    expect(vad.speaking).toBe(false);
  });

  it("treats bursts shorter than 300 ms as noise", () => {
    const { vad, clock } = calibrated();
    feed(vad, clock, LOUD, 150);
    const events = feed(vad, clock, QUIET, 1300);
    expect(events).toEqual([{ type: "noise", speechMs: expect.any(Number) }]);
  });

  it("keeps a slightly quieter voice as speech (hysteresis) and short pauses inside it", () => {
    const { vad, clock } = calibrated();
    feed(vad, clock, LOUD, 400);
    const threshold = vad.threshold;
    expect(feed(vad, clock, threshold * 0.8, 2000)).toEqual([]); // softer, still speech
    expect(feed(vad, clock, QUIET, 800)).toEqual([]); // a pause between words
    expect(feed(vad, clock, LOUD, 300)).toEqual([]);
    expect(feed(vad, clock, QUIET, 1300).map((e) => e.type)).toEqual(["speech_end"]);
  });

  it("cuts an utterance at the maximum recording length", () => {
    const vad = new VoiceActivityDetector({ maxRecordingMs: 2000 });
    const clock = { t: 0 };
    feed(vad, clock, QUIET, 550);
    const events = feed(vad, clock, LOUD, 2200);
    // cut at 2 s; if the voice goes on, that is the start of the next utterance
    expect(events.map((e) => e.type)).toEqual(["speech_start", "max_length", "speech_start"]);
  });

  it("follows slow changes in background noise", () => {
    const { vad, clock } = calibrated(0.005);
    const before = vad.threshold;
    feed(vad, clock, 0.009, 3000); // the room got louder, still below the threshold
    expect(vad.threshold).toBeGreaterThan(before);
  });

  it("computes RMS", () => {
    expect(rms([0.5, -0.5, 0.5, -0.5])).toBeCloseTo(0.5);
    expect(rms([])).toBe(0);
  });
});
