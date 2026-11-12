import { describe, expect, it } from "vitest";
import {
  EXAM_TRACKS,
  EXTERNAL_LINK,
  STUDY4_TEST_LIBRARY,
  suggestedTracks,
} from "@/lib/examPrep";
import { MODULE } from "@/lib/modules";

describe("exam prep tracks", () => {
  it("offers IELTS, TOEIC and basic English, in that order", () => {
    expect(EXAM_TRACKS.map((t) => t.id)).toEqual(["ielts", "toeic", "basic"]);
    expect(EXAM_TRACKS.find((t) => t.id === "basic")?.name).toBe("Basic English");
  });

  it("links only to STUDY4 over HTTPS, one distinct page per track", () => {
    const urls = [...EXAM_TRACKS.map((t) => t.url), STUDY4_TEST_LIBRARY];
    for (const url of urls) {
      const u = new URL(url);
      expect(u.protocol).toBe("https:");
      expect(u.hostname).toBe("study4.com");
    }
    expect(new Set(urls).size).toBe(urls.length);
  });

  it("gives every track a description, skills, facts and existing practice modules", () => {
    for (const t of EXAM_TRACKS) {
      expect(t.blurb.length).toBeGreaterThan(30);
      expect(t.skills.length).toBeGreaterThanOrEqual(2);
      expect(t.facts.length).toBeGreaterThanOrEqual(2);
      expect(t.destination).toContain("STUDY4");
      for (const m of t.practiseHere) expect(MODULE[m]).toBeDefined();
    }
  });

  it("opens STUDY4 in a new tab without giving it this window or the referrer", () => {
    expect(EXTERNAL_LINK.target).toBe("_blank");
    expect(EXTERNAL_LINK.rel.split(" ")).toEqual(expect.arrayContaining(["noopener", "noreferrer"]));
  });
});

describe("suggestedTracks", () => {
  it("suggests foundations below B1 and the exams from B1 up", () => {
    expect(suggestedTracks("A1")).toEqual(["basic"]);
    expect(suggestedTracks("A2")).toEqual(["basic"]);
    for (const level of ["B1", "B2", "C1", "C2"] as const) {
      expect(suggestedTracks(level)).toEqual(["ielts", "toeic"]);
    }
    expect(suggestedTracks(null)).toEqual([]);
  });
});
