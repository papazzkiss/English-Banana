"use client";

import type { ReactNode } from "react";
import { useLearner } from "@/components/useLearner";
import { EmptyState } from "@/components/ui/EmptyState";
import { LockIcon } from "@/components/ui/Icons";
import { LoadingScreen } from "@/components/ui/Skeleton";
import { canAccess, type Area } from "@/lib/access";

/** Renders a staff page only for the roles of its area. Someone who types /admin without the
 * role gets a "no access" screen (the API would answer 403 to every call anyway). */
export function RoleGate({ area, children }: { area: Area; children: ReactNode }) {
  const { profile, ready } = useLearner();
  if (!ready || !profile) return <LoadingScreen />;
  if (!canAccess(profile.role, area)) {
    return (
      <EmptyState
        icon={<LockIcon size={28} />}
        title="You don't have access to this page"
        description="This page is for staff accounts. Ask an administrator if you think you should see it."
        actionText="Back to home"
        actionHref="/dashboard"
      />
    );
  }
  return <>{children}</>;
}
