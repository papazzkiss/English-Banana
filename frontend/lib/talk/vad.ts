/** Voice activity detection for Talk mode: feed it one microphone level (RMS, 0..1) per audio
 * frame and it reports when an utterance starts, ends after enough silence, is too short to be
 * speech, or reaches the maximum length. Pure logic, so it is unit-tested without a browser. */

export interface VadConfig {
  /** Frames during the first `calibrationMs` measure the background noise. */
  calibrationMs: number;
  /** Shorter bursts of sound are treated as noise and ignored. */
  minSpeechMs: number;
  /** This much silence after speech ends the utterance. */
  silenceDurationMs: number;
  /** An utterance is cut (and processed) after this long. */
  maxRecordingMs: number;
  /** Speech must be this many times louder than the noise floor ... */
  thresholdRatio: number;
  /** ... and at least this loud (RMS), so a silent room still has a sensible threshold. */
  minThreshold: number;
}

export const VAD_DEFAULTS: VadConfig = {
  calibrationMs: 500,
  minSpeechMs: 300,
  silenceDurationMs: 1200,
  maxRecordingMs: 30_000,
  thresholdRatio: 3,
  minThreshold: 0.012,
};

export type VadEvent =
  | { type: "calibrated"; threshold: number }
  | { type: "speech_start"; at: number }
  | { type: "speech_end"; speechMs: number; at: number }
  | { type: "noise"; speechMs: number }
  | { type: "max_length"; speechMs: number; at: number };

/** Keep the noise floor tracking slow changes in the room while nobody is speaking. */
const FLOOR_ADAPT = 0.05;
/** Once speaking, a quieter level still counts as voice (hysteresis). */
const RELEASE_RATIO = 0.7;

export class VoiceActivityDetector {
  private readonly config: VadConfig;
  private startedAt: number | null = null;
  private calibration: number[] = [];
  private floor = 0;
  private speechStart: number | null = null;
  private lastVoice = 0;

  constructor(config: Partial<VadConfig> = {}) {
    this.config = { ...VAD_DEFAULTS, ...config };
  }

  get calibrated(): boolean {
    return this.startedAt !== null && this.calibration.length === 0 && this.floor > 0;
  }

  get threshold(): number {
    return Math.max(this.floor * this.config.thresholdRatio, this.config.minThreshold);
  }

  get speaking(): boolean {
    return this.speechStart !== null;
  }

  /** Forget the current utterance (keeps the calibration). Call when listening resumes. */
  resetUtterance(): void {
    this.speechStart = null;
  }

  /** Process one frame. Returns at most one event. */
  push(level: number, now: number): VadEvent | null {
    const c = this.config;
    if (this.startedAt === null) this.startedAt = now;

    if (!this.calibrated) {
      this.calibration.push(level);
      if (now - this.startedAt < c.calibrationMs) return null;
      const sorted = [...this.calibration].sort((a, b) => a - b);
      // The median ignores a click or a cough during calibration.
      this.floor = Math.max(sorted[Math.floor(sorted.length / 2)], 1e-4);
      this.calibration = [];
      return { type: "calibrated", threshold: this.threshold };
    }

    if (this.speechStart === null) {
      if (level >= this.threshold) {
        this.speechStart = now;
        this.lastVoice = now;
        return { type: "speech_start", at: now };
      }
      this.floor += (Math.max(level, 1e-4) - this.floor) * FLOOR_ADAPT;
      return null;
    }

    if (level >= this.threshold * RELEASE_RATIO) this.lastVoice = now;
    const speechMs = this.lastVoice - this.speechStart;
    if (now - this.speechStart >= c.maxRecordingMs) {
      this.speechStart = null;
      return { type: "max_length", speechMs, at: now };
    }
    if (now - this.lastVoice >= c.silenceDurationMs) {
      this.speechStart = null;
      return speechMs < c.minSpeechMs
        ? { type: "noise", speechMs }
        : { type: "speech_end", speechMs, at: now };
    }
    return null;
  }
}

/** Root-mean-square level of one block of time-domain samples (-1..1). */
export function rms(samples: ArrayLike<number>): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return samples.length ? Math.sqrt(sum / samples.length) : 0;
}
