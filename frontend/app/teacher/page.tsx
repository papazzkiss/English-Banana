"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox } from "@/components/Feedback";
import { RoleGate } from "@/components/RoleGate";
import { useLearner } from "@/components/useLearner";
import { EmptyState } from "@/components/ui/EmptyState";
import { UserIcon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { accuracy, teacherApi, type UsersPage } from "@/lib/admin";

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "—");

export default function TeacherPage() {
  return (
    <RoleGate area="teacher">
      <Students />
    </RoleGate>
  );
}

function Students() {
  const { profile } = useLearner();
  const [q, setQ] = useState("");
  const [page, setPage] = useState<UsersPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPage(await teacherApi.students({ q, limit: 200 }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [q]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const admin = profile?.role === "admin";
  return (
    <div className="stack">
      <PageHeader
        eyebrow={admin ? "Administration" : "Teaching"}
        title="Students"
        description={admin
          ? "Every student's progress and results."
          : "The students assigned to you: their progress and their latest answers."}
      />
      <ErrorBox error={error} onRetry={load} />
      {!page ? (
        !error && <SkeletonCard lines={5} />
      ) : !page.total && !q ? (
        <EmptyState
          icon={<UserIcon size={28} />}
          title="No students yet"
          description="An administrator assigns students to teachers. They will appear here."
        />
      ) : (
        <Panel flush>
          <div style={{ padding: "16px 16px 0" }}>
            <div className="staff-toolbar">
              <div className="field grow">
                <label htmlFor="student-q">Search</label>
                <input id="student-q" type="search" placeholder="Name or e-mail" value={q}
                  onChange={(e) => setQ(e.target.value)} />
              </div>
            </div>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Student</th><th>Answers</th><th>Correct</th><th>Last active</th><th /></tr>
              </thead>
              <tbody>
                {page.users.map((u) => (
                  <tr key={u.user_id}>
                    <td>
                      <strong>{u.display_name}</strong>
                      <div className="row-sub">{u.email}{u.is_active ? "" : " · disabled"}</div>
                    </td>
                    <td>{u.attempts.toLocaleString()}</td>
                    <td>{accuracy(u) === null ? "—" : `${accuracy(u)}%`}</td>
                    <td className="nowrap">{day(u.last_active)}</td>
                    <td className="actions">
                      <Link className="btn small ghost" href={`/teacher/students/${u.user_id}`}>Progress</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!page.users.length && <p className="muted" style={{ padding: 16 }}>No students match.</p>}
          </div>
        </Panel>
      )}
    </div>
  );
}
