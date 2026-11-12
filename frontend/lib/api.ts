"use client";

import type { Job } from "./types";

/** Auth is an httpOnly session cookie set by /api/v1/auth/*; JavaScript never sees the token. */

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api/v1${path}`, {
    ...init, headers, cache: "no-store", credentials: "same-origin",
  });
  if (!res.ok) {
    let code = "error";
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      // Non-JSON error = the request never reached the API (it is down or restarting).
      if (res.status >= 500) {
        code = "server_unreachable";
        message = "The server is not reachable right now. Please try again in a moment.";
      }
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

/** Poll a background job (grading, speaking assessment, conversation summary) until it settles. */
export async function waitForJob<T>(jobId: string, onTick?: (j: Job<T>) => void): Promise<Job<T>> {
  for (let i = 0; i < 180; i++) {
    const job = await api<Job<T>>(`/jobs/${jobId}`);
    onTick?.(job);
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, i < 10 ? 1000 : 2000));
  }
  throw new ApiError(504, "timeout", "The job is taking too long. Please try again later.");
}

/** Submit an LLM-graded answer as a background job and wait for its result. Grading can take
 * longer than the proxy keeps a request open; resubmitting while it runs returns the same job. */
export async function postGraded<T>(path: string, body: unknown): Promise<T> {
  const job = await api<Job<T>>(path, {
    method: "POST", body: JSON.stringify(body), headers: { Prefer: "respond-async" },
  });
  const done = job.status === "succeeded" || job.status === "failed" ? job : await waitForJob<T>(job.job_id);
  if (done.status !== "succeeded" || !done.result) {
    throw new ApiError(503, "assessment_unavailable",
      done.error ?? "Your answer could not be graded right now. Please try again.");
  }
  return done.result;
}

export const MODULE_HREF: Record<string, (id: string) => string> = {
  vocabulary: () => "/practice/vocabulary",
  grammar: (id) => `/practice/grammar?exercise=${encodeURIComponent(id)}`,
  listening: (id) => `/practice/listening/${encodeURIComponent(id)}`,
  speaking: (id) => `/practice/speaking/${encodeURIComponent(id)}`,
  conversation: (id) => `/practice/conversation/${encodeURIComponent(id)}`,
};

export const skillLabel = (id: string) =>
  id.replace(/^[a-z]+\./, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
