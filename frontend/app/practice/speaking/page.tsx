"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, skillLabel } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { ErrorBox } from "@/components/Feedback";
import type { SpeakingPrompt } from "@/lib/types";
import { ArrowRightIcon, ClockIcon, SpeakingIcon, TargetIcon } from "@/components/ui/Icons";
import { CefrBadge, DifficultyBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonGrid } from "@/components/ui/Skeleton";

export default function SpeakingList() {
  useLearner();
  const [prompts, setPrompts] = useState<SpeakingPrompt[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ prompts: SpeakingPrompt[] }>("/speaking/prompts")
      .then((r) => setPrompts(r.prompts))
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <>
      <PageHeader
        back={{ href: "/practice", label: "Practice" }}
        title="Speaking"
        description="Answer a question out loud. You get a transcript, feedback on your grammar, and your speed, pauses and filler words."
      />
      <ErrorBox error={error} />
      {!prompts && !error ? (
        <SkeletonGrid count={4} columns={2} />
      ) : prompts && prompts.length === 0 ? (
        <EmptyState title="No prompts yet" description="Speaking prompts will appear here once they are published." />
      ) : (
        <div className="grid cols-2">
          {prompts?.map((p) => (
            <Link key={p.id} href={`/practice/speaking/${p.id}`} className="card interactive">
              <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start", gap: 14 }}>
                <IconTile icon={<SpeakingIcon size={20} />} tone="orange" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h2 style={{ margin: "0 0 4px" }}>{p.title}</h2>
                  <p className="small secondary clamp-2" style={{ margin: 0 }}>{p.instruction}</p>
                </div>
              </div>
              {p.target_grammar && (
                <p className="small row" style={{ gap: 6, margin: 0 }}>
                  <TargetIcon size={14} className="muted" /> Try to use <strong>{p.target_grammar_name ?? skillLabel(p.target_grammar)}</strong>
                </p>
              )}
              <div className="card-foot">
                <span className="chip-row">
                  <CefrBadge level={p.cefr_level} />
                  <DifficultyBadge difficulty={p.difficulty} />
                  <span className="small muted row" style={{ gap: 4 }}>
                    <ClockIcon size={13} /> {p.min_seconds}–{p.max_seconds}s
                  </span>
                </span>
                <span className="go">
                  Practise <ArrowRightIcon size={15} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
