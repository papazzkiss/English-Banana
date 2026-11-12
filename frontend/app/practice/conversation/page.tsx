"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, post } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { ErrorBox } from "@/components/Feedback";
import type { Conversation, Scenario } from "@/lib/types";
import { ArrowRightIcon, CheckIcon, ConversationIcon, UserIcon } from "@/components/ui/Icons";
import { CefrBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile, Spinner } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonGrid } from "@/components/ui/Skeleton";

export default function ScenarioList() {
  useLearner();
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ scenarios: Scenario[] }>("/conversation/scenarios")
      .then((r) => setScenarios(r.scenarios))
      .catch((e) => setError((e as Error).message));
  }, []);

  async function start(id: string) {
    setBusy(id);
    setError(null);
    try {
      const c = await post<Conversation>("/conversations", { scenario_id: id });
      router.push(`/practice/conversation/${c.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        back={{ href: "/practice", label: "Practice" }}
        title="Conversation"
        description="Role-play a real situation. Your partner stays in character; when you finish, every one of your turns is graded."
      />
      <ErrorBox error={error} />
      {!scenarios && !error ? (
        <SkeletonGrid count={4} columns={2} />
      ) : scenarios && scenarios.length === 0 ? (
        <EmptyState title="No scenarios yet" description="Role-play scenarios will appear here once they are published." />
      ) : (
        <div className="grid cols-2">
          {scenarios?.map((s) => (
            <section key={s.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start", gap: 14 }}>
                <IconTile icon={<ConversationIcon size={20} />} tone="green" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h2 style={{ margin: 0 }}>{s.title}</h2>
                </div>
              </div>
              <div className="card tinted" style={{ padding: 14 }}>
                <p className="small" style={{ margin: "0 0 8px" }}>
                  <UserIcon size={14} className="muted" style={{ verticalAlign: -2, marginRight: 6 }} />
                  You are <strong>{s.learner_role}</strong>
                </p>
                <ul className="list small" aria-label="Goals">
                  {s.goals.map((g) => (
                    <li key={g} className="row" style={{ flexWrap: "nowrap", gap: 8, padding: "3px 0", border: 0, alignItems: "flex-start" }}>
                      <CheckIcon size={14} className="muted" style={{ marginTop: 3, flexShrink: 0 }} />
                      <span className="secondary">{g}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="card-foot">
                <span className="chip-row">
                  <CefrBadge level={s.cefr_level} />
                  <span className="small muted">Up to {s.max_learner_turns} turns</span>
                </span>
                <button type="button" className="btn" onClick={() => start(s.id)} disabled={busy !== null}>
                  {busy === s.id ? <><Spinner /> Starting…</> : <>Start <ArrowRightIcon size={16} /></>}
                </button>
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
