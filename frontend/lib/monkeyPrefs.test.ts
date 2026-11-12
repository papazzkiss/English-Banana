import { describe, expect, it } from "vitest";
import {
  chatBody, DEFAULT_PREFS, normalize, parsePrefs, prefsAfterReply, QUICK_ACTIONS, summary,
  withMode, withSetting, type MonkeyPrefs,
} from "@/lib/monkeyPrefs";

const action = (id: string) => QUICK_ACTIONS.find((a) => a.id === id)!;

describe("teaching modes", () => {
  it("defaults to auto everywhere", () => {
    expect(DEFAULT_PREFS).toEqual({
      mode: "auto", conversation_language: "auto", explanation_language: "auto",
      correction_language: "auto", corrections: "auto",
    });
  });

  it("applies the presets and keeps the correction level", () => {
    const strict = { ...DEFAULT_PREFS, corrections: "strict" as const };
    expect(withMode(strict, "vietnamese_support")).toEqual({
      mode: "vietnamese_support", conversation_language: "en", correction_language: "vi",
      explanation_language: "vi", corrections: "strict",
    });
    expect(withMode(DEFAULT_PREFS, "immersion").explanation_language).toBe("en");
    const bilingual = withMode(DEFAULT_PREFS, "bilingual");
    expect([bilingual.correction_language, bilingual.explanation_language]).toEqual(["en", "vi"]);
  });

  it("names the mode a combination matches, or custom", () => {
    const p = withSetting(withMode(DEFAULT_PREFS, "immersion"), "explanation_language", "vi");
    expect(p.mode).toBe("bilingual");
    expect(withSetting(p, "conversation_language", "vi").mode).toBe("custom");
    expect(normalize({ ...DEFAULT_PREFS, mode: "free_chat" }).mode).toBe("free_chat");
  });
});

describe("quick actions", () => {
  it("switch languages without touching the rest", () => {
    const vi = action("explain-vi").apply(DEFAULT_PREFS);
    expect([vi.explanation_language, vi.correction_language, vi.conversation_language])
      .toEqual(["vi", "vi", "auto"]);
    expect(action("explain-vi").active(vi)).toBe(true);
    expect(action("english-only").apply(vi).mode).toBe("immersion");
    const custom: MonkeyPrefs = { ...vi, corrections: "off" };
    expect(action("auto").apply(custom)).toEqual(DEFAULT_PREFS);
  });
});

describe("chat requests", () => {
  const history = Array.from({ length: 45 }, (_, i) => ({
    id: String(i), role: (i % 2 ? "monkey" : "learner") as "learner" | "monkey", text: `m${i}`,
  }));

  it("send the recent history and the preferences (typed and voice messages alike)", () => {
    const prefs = withMode(DEFAULT_PREFS, "bilingual");
    const body = chatBody(history, prefs);
    expect(body.messages).toHaveLength(40);
    expect(body.messages[0]).toEqual({ role: "monkey", text: "m5" }); // no client-only fields
    expect(body.preferences).toBe(prefs);
  });

  it("take the server's preferences only when the message changed them", () => {
    const mine = withMode(DEFAULT_PREFS, "bilingual");
    const server = { ...DEFAULT_PREFS, mode: "immersion", conversation_language: "en",
      explanation_language: "en", correction_language: "en" };
    expect(prefsAfterReply(mine, { reply: "ok", preferences: DEFAULT_PREFS, changes: [] })).toBe(mine);
    expect(prefsAfterReply(mine, { reply: "ok", preferences: server, changes: ["Mode: English Immersion"] }).mode)
      .toBe("immersion");
    expect(prefsAfterReply(mine, { reply: "ok" })).toBe(mine); // an older server
  });

  it("sanitise stored preferences", () => {
    expect(parsePrefs({ mode: "hacker", explanation_language: "fr", corrections: "all" })).toEqual(DEFAULT_PREFS);
    expect(parsePrefs(null)).toEqual(DEFAULT_PREFS);
  });

  it("summarise the settings in one line", () => {
    expect(summary(DEFAULT_PREFS)).toBe("Auto");
    expect(summary({ ...withMode(DEFAULT_PREFS, "immersion"), corrections: "off" }))
      .toBe("English Immersion · corrections Off");
  });
});
