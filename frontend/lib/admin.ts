/** Admin, teacher and question-review API: types and calls. Every call is checked by role on
 * the server; these screens only exist to make the allowed actions easy. */

import { api } from "@/lib/api";
import type { BankSkill } from "@/lib/bank";
import type {
  ActivityResponse, Cefr, MasteryResponse, RecentAttempt, Role, WeakSkillsResponse,
} from "@/lib/types";

export interface UserRow {
  user_id: string;
  display_name: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  attempts: number;
  correct: number;
  last_active: string | null;
}

export interface UserDetail extends UserRow {
  teacher_ids: string[];
  student_ids: string[];
}

export interface UsersPage { total: number; users: UserRow[] }

export interface AdminStats {
  users: Record<Role, { active: number; inactive: number }>;
  new_users_7d: number;
  attempts: Record<string, number>;
  bank: Record<string, Record<string, number>>;
  bank_last_import: { manifest_hash: string; questions: number; passages: number; imported_at: string } | null;
  system: Record<string, unknown>;
}

export interface StudentProgress {
  student: UserRow;
  mastery: MasteryResponse;
  weak_skills: WeakSkillsResponse;
  activity: ActivityResponse;
}

export type ReviewStatus = "draft" | "validated" | "approved" | "disabled";

export interface ReviewQuestion {
  id: string;
  skill: BankSkill;
  skill_id: string;
  level: Cefr;
  topic: string;
  point: string;
  difficulty: string;
  qtype: string;
  status: ReviewStatus;
  quality: number;
  instruction: string;
  prompt: string;
  options: { id: string; text: string }[];
  display: Record<string, unknown>;
  answer: Record<string, unknown>;
  explanation: string;
  explanation_vi: string;
  passage_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface ReviewPage { total: number; questions: ReviewQuestion[] }

const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

/** Query string from the parameters that are set. */
export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const adminApi = {
  stats: () => api<AdminStats>("/admin/stats"),
  users: (p: { q?: string; role?: Role | ""; active?: boolean | null; limit?: number; offset?: number }) =>
    api<UsersPage>(`/admin/users${query(p)}`),
  user: (id: string) => api<UserDetail>(`/admin/users/${encodeURIComponent(id)}`),
  update: (id: string, change: { role?: Role; is_active?: boolean }) =>
    patch<UserDetail>(`/admin/users/${encodeURIComponent(id)}`, change),
  link: (teacherId: string, studentId: string, linked: boolean) =>
    api<UserDetail>(
      `/admin/users/${encodeURIComponent(teacherId)}/students/${encodeURIComponent(studentId)}`,
      { method: linked ? "PUT" : "DELETE" }),
};

export const teacherApi = {
  students: (p: { q?: string; limit?: number; offset?: number }) =>
    api<UsersPage>(`/teacher/students${query(p)}`),
  progress: (id: string) => api<StudentProgress>(`/teacher/students/${encodeURIComponent(id)}/progress`),
  attempts: (id: string) => api<RecentAttempt[]>(`/teacher/students/${encodeURIComponent(id)}/attempts`),
};

export const reviewApi = {
  page: (skill: BankSkill, p: { status?: ReviewStatus | ""; level?: Cefr | ""; q?: string; limit?: number; offset?: number }) =>
    api<ReviewPage>(`/bank/${skill}/review${query(p)}`),
  setStatus: (id: string, status: Exclude<ReviewStatus, "draft">) =>
    patch<ReviewQuestion>(`/bank/questions/${encodeURIComponent(id)}`, { status }),
};

/** The correct answer as a reviewer reads it. */
export function answerText(q: ReviewQuestion): string {
  const a = q.answer as Record<string, unknown>;
  if (typeof a.option === "string") return q.options.find((o) => o.id === a.option)?.text ?? a.option;
  if (Array.isArray(a.accepted)) return (a.accepted as string[]).join(" / ");
  if (typeof a.text === "string") return a.text;
  if (Array.isArray(a.order)) return (a.order as string[]).join(" ");
  if (a.pairs && typeof a.pairs === "object") {
    const left = (q.display.left as { id: string; text: string }[] | undefined) ?? [];
    return Object.entries(a.pairs as Record<string, string>)
      .map(([l, r]) => `${left.find((x) => x.id === l)?.text ?? l} → ${q.options.find((o) => o.id === r)?.text ?? r}`)
      .join("; ");
  }
  return JSON.stringify(a);
}

export const accuracy = (u: { attempts: number; correct: number }) =>
  u.attempts ? Math.round((100 * u.correct) / u.attempts) : null;
