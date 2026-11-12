"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox } from "@/components/Feedback";
import { RoleGate } from "@/components/RoleGate";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel, Stat } from "@/components/ui/Panel";
import { SkeletonGrid } from "@/components/ui/Skeleton";
import { Tag } from "@/components/ui/Badge";
import { ArrowRightIcon } from "@/components/ui/Icons";
import { adminApi, type AdminStats } from "@/lib/admin";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["admin", "teacher", "student"];
const STATUSES = ["approved", "validated", "draft", "disabled"] as const;
const n = (x: number | undefined) => (x ?? 0).toLocaleString();

export default function AdminPage() {
  return (
    <RoleGate area="admin">
      <AdminDashboard />
    </RoleGate>
  );
}

function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStats(await adminApi.stats());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const users = stats?.users;
  const totalUsers = users ? ROLES.reduce((s, r) => s + users[r].active + users[r].inactive, 0) : 0;
  const skills = stats ? Object.keys(stats.bank).sort() : [];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Administration"
        title="Admin dashboard"
        description="Users, activity and the question bank at a glance."
        actions={
          <Link href="/admin/users" className="btn ghost">
            Manage users <ArrowRightIcon size={16} />
          </Link>
        }
      />
      <ErrorBox error={error} onRetry={load} />
      {!stats ? (
        !error && <SkeletonGrid count={4} columns={4} />
      ) : (
        <>
          <div className="grid cols-4">
            <Stat label="Users" value={n(totalUsers)}>
              {n(stats.new_users_7d)} new in 7 days
            </Stat>
            <Stat label="Active learners · 7 days" value={n(stats.attempts.active_learners)} />
            <Stat label="Answers · 7 days" value={n(stats.attempts.recent)}>
              {n(stats.attempts.total)} in total
            </Stat>
            <Stat
              label="Bank questions served"
              value={n(skills.reduce((s, k) => s + (stats.bank[k].validated ?? 0) + (stats.bank[k].approved ?? 0), 0))}
            >
              <Link href="/review">Review questions</Link>
            </Stat>
          </div>

          <div className="split">
            <Panel title="Users by role">
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr><th>Role</th><th>Active</th><th>Disabled</th></tr>
                  </thead>
                  <tbody>
                    {ROLES.map((r) => (
                      <tr key={r}>
                        <td style={{ textTransform: "capitalize" }}>
                          <Link href={`/admin/users?role=${r}`}>{r}</Link>
                        </td>
                        <td>{n(users?.[r].active)}</td>
                        <td>{n(users?.[r].inactive)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Answers in the last 7 days" description="By module">
              <div className="table-wrap">
                <table className="data">
                  <tbody>
                    {Object.entries(stats.attempts)
                      .filter(([k]) => k.startsWith("recent_"))
                      .sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => (
                        <tr key={k}>
                          <td style={{ textTransform: "capitalize" }}>{k.replace("recent_", "")}</td>
                          <td className="strong">{n(v)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>

          <Panel
            title="Question bank"
            description={
              stats.bank_last_import
                ? `Last import ${new Date(stats.bank_last_import.imported_at).toLocaleString()} · ` +
                  `${n(stats.bank_last_import.questions)} questions, ${n(stats.bank_last_import.passages)} passages`
                : "Not imported yet"
            }
          >
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Skill</th>
                    {STATUSES.map((s) => <th key={s}>{s}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {skills.map((k) => (
                    <tr key={k}>
                      <td style={{ textTransform: "capitalize" }}>
                        <Link href={`/review?skill=${k}`}>{k}</Link>
                      </td>
                      {STATUSES.map((s) => <td key={s}>{n(stats.bank[k][s])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Settings" description="Read-only. Change these in the server's environment and restart the API.">
            <SystemSettings system={stats.system} />
          </Panel>
        </>
      )}
    </div>
  );
}

function SystemSettings({ system }: { system: Record<string, unknown> }) {
  const llm = (system.llm ?? {}) as Record<string, unknown>;
  const prompts = (system.prompt_versions ?? {}) as Record<string, string>;
  const review = (system.content_review_status ?? {}) as Record<string, Record<string, number>>;
  const rows: [string, React.ReactNode][] = [
    ["Model", String(llm.model ?? system.llm_provider ?? "—")],
    ["Fallback model", String(llm.fallback_model || "none")],
    ["LLM timeout", `${llm.timeout_seconds ?? "—"} s · keep-alive ${llm.keep_alive ?? "—"}`],
    ["Speech-to-text", String(system.stt_provider ?? "—")],
    ["AI Monkey", system.feature_ai_monkey ? <Tag tone="good">on</Tag> : <Tag>off</Tag>],
    ["Serve reviewed content only", system.require_reviewed_content ? <Tag tone="good">yes</Tag> : <Tag tone="warn">no</Tag>],
    ["Prompt versions", Object.entries(prompts).map(([k, v]) => `${k} ${v}`).join(" · ")],
    ["Lesson content", Object.entries(review).map(([k, v]) => `${k}: ${Object.entries(v).map(([s, c]) => `${c} ${s}`).join(", ")}`).join(" · ") || "—"],
  ];
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
