import { describe, expect, it } from "vitest";
import {
  EMPTY_FILTERS, errorParts, isBankItem, pointLabel, setBody, setScore, type BankAnswer,
} from "@/lib/bank";

describe("question bank helpers", () => {
  it("tells bank items from lesson exercises", () => {
    expect(isBankItem("gr.present_perfect.3f9a0c1b2d4e")).toBe(true);
    expect(isBankItem("vo.meaning.0123456789ab")).toBe(true);
    expect(isBankItem("rd.true_false.abcdefabcdef")).toBe(true);
    expect(isBankItem("gr.present.001")).toBe(false); // a grammar lesson exercise
    expect(isBankItem("ls.voicemail.001.q1")).toBe(false); // a listening lesson question
  });

  it("sends only the filters that are set", () => {
    expect(setBody(EMPTY_FILTERS)).toEqual({ count: 10 });
    expect(setBody({ ...EMPTY_FILTERS, levels: ["B1"], points: ["present_perfect"], count: 20 }))
      .toEqual({ count: 20, levels: ["B1"], points: ["present_perfect"] });
  });

  it("splits a find-the-mistake sentence into its parts", () => {
    expect(errorParts("[The twins] [has come] [down] [with measles].")).toEqual({
      parts: ["The twins", "has come", "down", "with measles"], end: ".",
    });
    expect(errorParts("No brackets here.")).toBeNull();
  });

  it("labels points and scores sets", () => {
    expect(pointLabel("present_perfect", { present_perfect: "Present perfect" })).toBe("Present perfect");
    expect(pointLabel("word_form", {})).toBe("Word forms");
    expect(pointLabel("daily_life", {})).toBe("Daily life");
    const r = (correct: boolean, score: number) => ({ correct, score }) as BankAnswer;
    expect(setScore([r(true, 100), r(false, 0), r(false, 80)])).toEqual({ correct: 1, total: 3, percent: 60 });
    expect(setScore([])).toEqual({ correct: 0, total: 0, percent: 0 });
  });
});
