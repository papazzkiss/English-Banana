"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, api, post } from "@/lib/api";
import type { LearnerProfile } from "@/lib/types";

interface LearnerContextValue {
  profile: LearnerProfile | null;
  /** The first /auth/me answer has arrived (signed in or not). */
  ready: boolean;
  reload: () => Promise<void>;
  signOut: () => Promise<void>;
}

const LearnerContext = createContext<LearnerContextValue | null>(null);
const listeners = new Set<() => void>();

/** Call after signing in or out, so every screen picks up the new learner. */
export function notifyLearnerChanged() {
  listeners.forEach((l) => l());
}

/** One /auth/me request per navigation for the whole app (it used to be one per component).
 * It refreshes on every route change so the counters in the profile stay current. */
export function LearnerProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [ready, setReady] = useState(false);

  const reload = useCallback(async () => {
    try {
      const next = await api<LearnerProfile>("/auth/me");
      // Same data: keep the same object, so screens that depend on it do not reload.
      setProfile((prev) => (prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
    } catch (e) {
      // Only a real "signed out" (or "account disabled") answer clears the learner; a network
      // blip keeps the screen.
      if (e instanceof ApiError && (e.status === 401 || e.code === "account_disabled")) setProfile(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload, pathname]);

  useEffect(() => {
    listeners.add(reload);
    return () => {
      listeners.delete(reload);
    };
  }, [reload]);

  const signOut = useCallback(async () => {
    try {
      await post("/auth/logout");
    } finally {
      setProfile(null);
      notifyLearnerChanged();
      router.push("/");
    }
  }, [router]);

  const value = useMemo(() => ({ profile, ready, reload, signOut }), [profile, ready, reload, signOut]);
  return <LearnerContext.Provider value={value}>{children}</LearnerContext.Provider>;
}

export function useLearnerContext(): LearnerContextValue {
  const ctx = useContext(LearnerContext);
  if (!ctx) throw new Error("useLearner must be used inside <LearnerProvider>");
  return ctx;
}
