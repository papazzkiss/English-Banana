import { describe, expect, it } from "vitest";
import { AUDIO_CONSTRAINTS, fileNameFor, isIOS, pickMimeType } from "./browser";

describe("browser helpers", () => {
  it("asks for echo cancellation, noise suppression and auto gain", () => {
    expect(AUDIO_CONSTRAINTS.audio).toEqual({
      echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    });
  });

  it("picks the first recording format the browser supports", () => {
    expect(pickMimeType(() => true)).toBe("audio/webm;codecs=opus"); // Chrome, Firefox
    expect(pickMimeType((t) => t === "audio/mp4")).toBe("audio/mp4"); // Safari
    expect(pickMimeType(() => false)).toBeUndefined();
    expect(pickMimeType(() => { throw new Error("old browser"); })).toBeUndefined();
  });

  it("names uploads so the server accepts the format", () => {
    expect(fileNameFor("audio/webm;codecs=opus")).toBe("voice.webm");
    expect(fileNameFor("audio/ogg;codecs=opus")).toBe("voice.ogg");
    expect(fileNameFor("audio/mp4")).toBe("voice.m4a");
    expect(fileNameFor("")).toBe("voice.webm");
  });

  it("recognises iOS, including iPadOS that reports a Mac", () => {
    const nav = (userAgent: string, platform = "Linux", maxTouchPoints = 0) =>
      ({ userAgent, platform, maxTouchPoints });
    expect(isIOS(nav("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"))).toBe(true);
    expect(isIOS(nav("Mozilla/5.0 (Macintosh)", "MacIntel", 5))).toBe(true);
    expect(isIOS(nav("Mozilla/5.0 (Macintosh)", "MacIntel", 0))).toBe(false);
    expect(isIOS(nav("Mozilla/5.0 (Linux; Android 14) Chrome/140"))).toBe(false);
  });
});
