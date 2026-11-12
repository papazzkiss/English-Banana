import { describe, expect, it } from "vitest";
import { areaForPath, canAccess, staffLinks } from "@/lib/access";

describe("role-based screens", () => {
  it("opens each staff area to its roles only", () => {
    expect(canAccess("admin", "admin")).toBe(true);
    expect(canAccess("teacher", "admin")).toBe(false);
    expect(canAccess("student", "admin")).toBe(false);
    expect(canAccess("teacher", "teacher")).toBe(true);
    expect(canAccess("teacher", "review")).toBe(true);
    expect(canAccess("student", "teacher")).toBe(false);
    expect(canAccess("student", "review")).toBe(false);
    expect(canAccess(undefined, "review")).toBe(false);
  });

  it("maps typed URLs to their area", () => {
    expect(areaForPath("/admin")).toBe("admin");
    expect(areaForPath("/admin/users")).toBe("admin");
    expect(areaForPath("/teacher/students/42")).toBe("teacher");
    expect(areaForPath("/review")).toBe("review");
    expect(areaForPath("/administrator")).toBeNull();
    expect(areaForPath("/practice/grammar")).toBeNull();
  });

  it("shows staff links by role", () => {
    expect(staffLinks("student")).toEqual([]);
    expect(staffLinks("teacher").map((l) => l.href)).toEqual(["/teacher", "/review"]);
    expect(staffLinks("admin").map((l) => l.href)).toEqual(["/admin", "/admin/users", "/teacher", "/review"]);
  });
});
