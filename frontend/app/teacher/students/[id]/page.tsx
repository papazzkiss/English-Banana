"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ActivityBars, MasteryBars } from "@/components/charts";
import { ErrorBox } from "@/components/Feedback";
import { RoleGate } from "@/components/RoleGate";
import { Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel, Stat } from "@/components/ui/Panel";
import { SkeletonGrid } from "@/components/ui/Skeleton";
import { skillLabel } from "@/lib/api";
import { accuracy, teacherApi, type StudentProgress } from "@/lib/admin";
import type { RecentAttempt } from "@/lib/types";

export default function StudentPage() {
  return (
    <RoleGate area="teacher">
      <Student />
    </RoleGate>
  );
}

function Student() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<StudentProgress | null>(null);
  const [attempts, setAttempts] = useState<RecentAttempt[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, a] = await Promise.all([teacherApi.progress(id), teacherApi.attempts(id)]);
      setData(p);
      setAttempts(a);
    } catch (e) {
      // 403: not one of this teacher's students (the server decides, whatever the URL says)
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const practised = data?.mastery.skills.filter((s) => s.attempt_count > 0) ?? [];
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Student"
        title={data?.student.display_name ?? "Student"}
        description={data?.student.email ?? undefined}
        back={{ href: "/teacher", label: "Students" }}
      />
      <ErrorBox error={error} />
      {!data ? (
        !error && <SkeletonGrid count={4} columns={4} />
      ) : (
        <>
          <div className="grid cols-4">
            <Stat label="Answers" value={data.student.attempts.toLocaleString()} />
            <Stat label="Correct" value={accuracy(data.student) === null ? "—" : `${accuracy(data.student)}%`} />
            <Stat label="Active days" value={data.activity.active_days}>last {data.activity.days.length} days</Stat>
            <Stat label="Streak" value={`${data.activity.current_streak} d`} />
          </div>
          <div className="split">
            <Panel title="Mastery by skill" description="0–100 · below the line is a weak skill">
              <MasteryBars skills={practised} threshold={data.mastery.weakness_threshold} />
            </Panel>
            <Panel title="Weak skills">
              {data.weak_skills.skills.length ? (
                <ul className="list">
                  {data.weak_skills.skills.map((w) => (
                    <li key={w.skill_id} className="list-row">
                      <div className="row-main">
                        <span className="row-title">{w.skill_name}</span>
                        <span className="row-sub">{w.attempt_count} answers</span>
                      </div>
                      <Tag tone="bad">{w.effective_mastery.toFixed(0)}</Tag>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted small">No weak skills.</p>
              )}
            </Panel>
          </div>
          <Panel title="Activity"><ActivityBars days={data.activity.days} /></Panel>
          <Panel title="Latest answers" flush>
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>When</th><th>Module</th><th>Skill</th><th>Answer</th><th>Score</th></tr></thead>
                <tbody>
                  {attempts.map((a) => (
                    <tr key={a.attempt_id}>
                      <td className="nowrap">{new Date(a.submitted_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</td>
                      <td style={{ textTransform: "capitalize" }}>{a.module}</td>
                      <td>{skillLabel(a.skill_id)}</td>
                      <td className="clamp-2" style={{ maxWidth: 280 }}>{a.answer}</td>
                      <td>{a.score === null ? "—" : <Tag tone={a.is_correct ? "good" : "bad"}>{a.score.toFixed(0)}</Tag>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!attempts.length && <p className="muted" style={{ padding: 16 }}>No answers yet.</p>}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
