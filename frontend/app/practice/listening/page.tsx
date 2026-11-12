"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { ErrorBox } from "@/components/Feedback";
import type { ListeningLesson } from "@/lib/types";
import { ArrowRightIcon, ClockIcon, ListeningIcon } from "@/components/ui/Icons";
import { CefrBadge, DifficultyBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonGrid } from "@/components/ui/Skeleton";
import { Segmented } from "@/components/ui/Segmented";
import { BankPractice } from "@/components/bank/BankPractice";

function ListeningList() {
  const { profile } = useLearner();
  const params = useSearchParams();
  const router = useRouter();
  const sets = params.get("view") === "sets";
  const [lessons, setLessons] = useState<ListeningLesson[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ lessons: ListeningLesson[] }>("/listening/lessons")
      .then((r) => setLessons(r.lessons))
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <>
      <PageHeader
        back={{ href: "/practice", label: "Practice" }}
        title="Listening"
        description="Play a short everyday clip as many times as you like, then answer in your own words. The transcript unlocks when you finish. Practice sets draw new recordings from a large pool."
        actions={
          <Segmented
            label="Listening view"
            value={sets ? "sets" : "lessons"}
            onChange={(v) => router.replace(v === "sets" ? "/practice/listening?view=sets" : "/practice/listening")}
            options={[
              { value: "lessons", label: "Lessons" },
              { value: "sets", label: "Practice sets" },
            ]}
          />
        }
      />
      <ErrorBox error={error} />
      {sets ? (
        <BankPractice skill="listening" defaultLevel={profile?.current_level} />
      ) : !lessons && !error ? (
        <SkeletonGrid count={4} columns={2} />
      ) : lessons && lessons.length === 0 ? (
        <EmptyState title="No lessons yet" description="Listening lessons will appear here once they are published." />
      ) : (
        <div className="grid cols-2">
          {lessons?.map((l) => (
            <Link key={l.id} href={`/practice/listening/${l.id}`} className="card interactive">
              <div className="row" style={{ flexWrap: "nowrap", gap: 14 }}>
                <IconTile icon={<ListeningIcon size={20} />} tone="blue" />
                <h2 style={{ margin: 0, flex: 1 }}>{l.title}</h2>
              </div>
              <div className="card-foot">
                <span className="chip-row">
                  <CefrBadge level={l.cefr_level} />
                  <DifficultyBadge difficulty={l.difficulty} />
                  <span className="small muted row" style={{ gap: 4 }}>
                    <ClockIcon size={13} /> {Math.round(l.duration_seconds)}s · {l.questions.length} questions
                  </span>
                </span>
                <span className="go">
                  Listen <ArrowRightIcon size={15} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ListeningList />
    </Suspense>
  );
}
