"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { bankApi } from "@/lib/bank";
import { useLearner } from "@/components/useLearner";
import { ErrorBox } from "@/components/Feedback";
import { MODULES, masteryBand } from "@/lib/modules";
import type {
  DueCard,
  GrammarTopic,
  ListeningLesson,
  MasteryResponse,
  Module,
  Recommendation,
  Scenario,
  SpeakingPrompt,
} from "@/lib/types";
import { MONKEY_PATH, useMonkey } from "@/components/MonkeyProvider";
import { MonkeyAvatar } from "@/components/MonkeyAvatar";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Tag } from "@/components/ui/Badge";
import { SkeletonGrid } from "@/components/ui/Skeleton";
import { ArrowRightIcon, SparklesIcon } from "@/components/ui/Icons";

interface HubData {
  mastery: MasteryResponse;
  count: Record<Module, string>;
  recommended: Module | null;
}

export default function PracticeHub() {
  const { profile } = useLearner();
  const learnerId = profile?.learner_id;
  const monkey = useMonkey();
  const [data, setData] = useState<HubData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!learnerId) return;
    Promise.all([
      api<MasteryResponse>("/learner/mastery"),
      api<{ cards: DueCard[] }>("/vocabulary/due?limit=50"),
      api<GrammarTopic[]>("/grammar/topics"),
      api<{ lessons: ListeningLesson[] }>("/listening/lessons"),
      api<{ prompts: SpeakingPrompt[] }>("/speaking/prompts"),
      api<{ scenarios: Scenario[] }>("/conversation/scenarios"),
      api<{ recommendations: Recommendation[] }>("/recommendation/next?n=1"),
      bankApi.summary("reading").catch(() => null),
    ])
      .then(([mastery, due, topics, lessons, prompts, scenarios, recs, reading]) => {
        // Same split as the dashboard: reviews due today, then today's new words.
        const fresh = due.cards.filter((c) => c.is_new).length;
        const reviews = due.cards.length - fresh;
        const vocab = [reviews && `${reviews} due`, fresh && `${fresh} new`].filter(Boolean).join(" · ");
        setData({
          mastery,
          count: {
            vocabulary: vocab || "Nothing due",
            grammar: `${topics.length} topics`,
            listening: `${lessons.lessons.length} lessons`,
            speaking: `${prompts.prompts.length} prompts`,
            conversation: `${scenarios.scenarios.length} scenarios`,
            reading: reading ? `${reading.pool_size.toLocaleString()} questions` : "Texts and questions",
          },
          recommended: recs.recommendations[0]?.module ?? null,
        });
      })
      .catch((e) => setError((e as Error).message));
  }, [learnerId]);

  if (!profile) return null;

  return (
    <>
      <PageHeader
        title="Practice"
        description="Choose a skill to work on. Every answer is graded and updates your plan."
      />
      <ErrorBox error={error} />

      {!data ? (
        <SkeletonGrid count={6} columns={3} />
      ) : (
        <div className="grid cols-3">
          {MODULES.map((m) => {
            const skills = data.mastery.skills.filter((s) => s.module === m.id && s.attempt_count > 0);
            const avg = skills.length
              ? skills.reduce((t, s) => t + s.effective_mastery, 0) / skills.length
              : null;
            const band = masteryBand(avg, data.mastery.weakness_threshold);
            return (
              <Link key={m.id} href={m.href} className="card interactive">
                <div className="row-between" style={{ alignItems: "flex-start" }}>
                  <IconTile icon={m.icon(22)} tone={m.tone} size="lg" />
                  {data.recommended === m.id ? (
                    <Tag tone="accent">
                      <SparklesIcon size={12} /> Recommended
                    </Tag>
                  ) : (
                    <Tag tone={band.tone}>{band.label}</Tag>
                  )}
                </div>
                <div>
                  <h2 style={{ margin: "0 0 4px" }}>{m.label}</h2>
                  <p className="small secondary" style={{ margin: 0 }}>
                    {m.blurb}
                  </p>
                </div>
                <ProgressBar value={avg ?? 0} label={`${m.label} mastery`} size="sm" tone={m.tone} />
                <div className="card-foot">
                  <span className="small muted">
                    {data.count[m.id]}
                    {avg !== null && ` · ${Math.round(avg)}/100`}
                  </span>
                  <span className="go">
                    Open <ArrowRightIcon size={15} />
                  </span>
                </div>
              </Link>
            );
          })}

          {monkey.enabled && (
            <Link href={MONKEY_PATH} className="card interactive">
              <div className="row-between" style={{ alignItems: "flex-start" }}>
                <MonkeyAvatar size={52} />
                <Tag>Not graded</Tag>
              </div>
              <div>
                <h2 style={{ margin: "0 0 4px" }}>AI Monkey</h2>
                <p className="small secondary" style={{ margin: 0 }}>
                  Chat or talk freely about anything. A relaxed way to warm up.
                </p>
              </div>
              <div className="card-foot">
                <span className="small muted">Text or hands-free voice</span>
                <span className="go">
                  Open <ArrowRightIcon size={15} />
                </span>
              </div>
            </Link>
          )}
        </div>
      )}
    </>
  );
}
