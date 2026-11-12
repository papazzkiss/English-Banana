"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { notifyLearnerChanged, useLearnerContext } from "@/components/LearnerProvider";

export { notifyLearnerChanged };

/** The signed-in learner (session cookie). Redirects to the sign-in page when there is none. */
export function useLearner({ redirect = true }: { redirect?: boolean } = {}) {
  const router = useRouter();
  const ctx = useLearnerContext();

  useEffect(() => {
    if (redirect && ctx.ready && !ctx.profile) router.replace("/");
  }, [redirect, ctx.ready, ctx.profile, router]);

  return ctx;
}
