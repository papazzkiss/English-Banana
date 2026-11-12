"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ErrorBox } from "@/components/Feedback";
import { RoleGate } from "@/components/RoleGate";
import { useLearner } from "@/components/useLearner";
import { Tag } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Callout, Panel } from "@/components/ui/Panel";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ROLE_LABEL } from "@/lib/access";
import { accuracy, adminApi, type UserDetail, type UserRow, type UsersPage } from "@/lib/admin";
import type { Role } from "@/lib/types";

const PAGE = 25;
const ROLES: Role[] = ["student", "teacher", "admin"];
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "—");

export default function UsersPageRoute() {
  return (
    <RoleGate area="admin">
      <Suspense>
        <Users />
      </Suspense>
    </RoleGate>
  );
}

function Users() {
  const params = useSearchParams();
  const { profile } = useLearner();
  const [q, setQ] = useState("");
  const [role, setRole] = useState<Role | "">((params.get("role") as Role) || "");
  const [active, setActive] = useState<"" | "true" | "false">("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<UsersPage | null>(null);
  const [selected, setSelected] = useState<UserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setPage(await adminApi.users({
        q, role, active: active === "" ? null : active === "true", limit: PAGE, offset,
      }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [q, role, active, offset]);

  useEffect(() => {
    const t = setTimeout(load, 250); // typing in the search box
    return () => clearTimeout(t);
  }, [load]);

  async function change(u: UserRow, next: { role?: Role; is_active?: boolean }, what: string) {
    if (next.role === "admin" && !confirm(`Make ${u.display_name} an admin? Admins can manage every account.`)) return;
    if (next.is_active === false && !confirm(`Disable ${u.display_name}? They are signed out everywhere and cannot sign in until enabled again. Their learning history is kept.`)) return;
    setBusy(u.user_id);
    setError(null);
    try {
      const updated = await adminApi.update(u.user_id, next);
      setNotice(`${updated.display_name}: ${what}.`);
      if (selected?.user_id === u.user_id) setSelected(updated);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function open(u: UserRow) {
    try {
      setSelected(await adminApi.user(u.user_id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Administration"
        title="Users"
        back={{ href: "/admin", label: "Admin dashboard" }}
        description="Change roles, disable or enable accounts, and choose which students a teacher follows. Accounts are never deleted: disabling one keeps its history."
      />
      <ErrorBox error={error} />
      {notice && <Callout tone="good" role="status">{notice}</Callout>}

      <Panel flush>
        <div style={{ padding: "16px 16px 0" }}>
          <div className="staff-toolbar">
            <div className="field grow">
              <label htmlFor="user-q">Search</label>
              <input id="user-q" type="search" placeholder="Name or e-mail" value={q}
                onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
            </div>
            <div className="field">
              <label htmlFor="user-role">Role</label>
              <select id="user-role" value={role} onChange={(e) => { setRole(e.target.value as Role | ""); setOffset(0); }}>
                <option value="">All roles</option>
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="user-active">Status</label>
              <select id="user-active" value={active} onChange={(e) => { setActive(e.target.value as "" | "true" | "false"); setOffset(0); }}>
                <option value="">Any</option>
                <option value="true">Active</option>
                <option value="false">Disabled</option>
              </select>
            </div>
          </div>
        </div>
        {!page ? (
          <div style={{ padding: 16 }}><SkeletonCard lines={5} /></div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>User</th><th>Role</th><th>Status</th><th>Answers</th><th>Last active</th><th>Joined</th>
                  <th className="actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {page.users.map((u) => {
                  const self = u.user_id === profile?.learner_id;
                  const acc = accuracy(u);
                  return (
                    <tr key={u.user_id}>
                      <td>
                        <button type="button" className="link-btn" onClick={() => open(u)}>
                          <strong>{u.display_name}</strong>
                        </button>
                        <div className="row-sub">{u.email ?? "no e-mail"}{self ? " · you" : ""}</div>
                      </td>
                      <td>
                        <select aria-label={`Role of ${u.display_name}`} value={u.role}
                          disabled={self || busy === u.user_id}
                          title={self ? "You cannot change your own role" : undefined}
                          onChange={(e) => change(u, { role: e.target.value as Role }, `role set to ${e.target.value}`)}>
                          {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                        </select>
                      </td>
                      <td>{u.is_active ? <Tag tone="good">Active</Tag> : <Tag tone="bad">Disabled</Tag>}</td>
                      <td className="nowrap">{u.attempts.toLocaleString()}{acc !== null && <span className="muted"> · {acc}%</span>}</td>
                      <td className="nowrap">{day(u.last_active)}</td>
                      <td className="nowrap">{day(u.created_at)}</td>
                      <td className="actions">
                        {!self && (
                          <button type="button" className={`btn small ${u.is_active ? "ghost" : "subtle"}`}
                            disabled={busy === u.user_id}
                            onClick={() => change(u, { is_active: !u.is_active }, u.is_active ? "disabled" : "enabled")}>
                            {u.is_active ? "Disable" : "Enable"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!page.users.length && <p className="muted" style={{ padding: 16 }}>No users match.</p>}
          </div>
        )}
        {page && page.total > PAGE && (
          <div className="pager" style={{ padding: "0 16px 16px" }}>
            <span className="small muted">{offset + 1}–{Math.min(offset + PAGE, page.total)} of {page.total}</span>
            <div className="btn-row">
              <button type="button" className="btn small ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
              <button type="button" className="btn small ghost" disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </div>
          </div>
        )}
      </Panel>

      {selected && (
        <UserPanel user={selected} onChanged={(u) => { setSelected(u); load(); }} onError={setError}
          onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

/** One user: details and, for a teacher, the students they follow. */
function UserPanel({ user, onChanged, onError, onClose }: {
  user: UserDetail;
  onChanged: (u: UserDetail) => void;
  onError: (e: string) => void;
  onClose: () => void;
}) {
  const [students, setStudents] = useState<UserRow[]>([]);
  const [pick, setPick] = useState("");
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<UserRow[]>([]);

  useEffect(() => {
    if (user.role !== "teacher" || !user.student_ids.length) { setStudents([]); return; }
    adminApi.users({ role: "student", limit: 200 })
      .then((p) => setStudents(p.users.filter((s) => user.student_ids.includes(s.user_id))))
      .catch((e) => onError((e as Error).message));
  }, [user, onError]);

  useEffect(() => {
    if (user.role !== "teacher") return;
    const t = setTimeout(() => {
      adminApi.users({ role: "student", q: search, active: true, limit: 20 })
        .then((p) => setCandidates(p.users.filter((s) => !user.student_ids.includes(s.user_id))))
        .catch((e) => onError((e as Error).message));
    }, 250);
    return () => clearTimeout(t);
  }, [search, user, onError]);

  async function link(studentId: string, linked: boolean) {
    try {
      onChanged(await adminApi.link(user.user_id, studentId, linked));
      setPick("");
    } catch (e) {
      onError((e as Error).message);
    }
  }

  return (
    <Panel title={user.display_name} description={user.email ?? undefined}
      actions={<button type="button" className="btn small ghost" onClick={onClose}>Close</button>}>
      <dl className="kv">
        <dt>Role</dt><dd>{ROLE_LABEL[user.role]}</dd>
        <dt>Status</dt><dd>{user.is_active ? "Active" : "Disabled"}</dd>
        <dt>Answers</dt><dd>{user.attempts.toLocaleString()} ({accuracy(user) ?? "—"}% correct)</dd>
        <dt>Last active</dt><dd>{day(user.last_active)}</dd>
        <dt>Joined</dt><dd>{day(user.created_at)}</dd>
        <dt>Followed by</dt><dd>{user.teacher_ids.length ? `${user.teacher_ids.length} teacher(s)` : "no teacher"}</dd>
        <dt>User id</dt><dd className="mono">{user.user_id}</dd>
      </dl>

      {user.role === "teacher" && (
        <div className="mt-24">
          <h3 className="section-title">Students this teacher follows</h3>
          {students.length ? (
            <ul className="list">
              {students.map((s) => (
                <li key={s.user_id} className="list-row">
                  <div className="row-main">
                    <span className="row-title">{s.display_name}</span>
                    <span className="row-sub">{s.email}</span>
                  </div>
                  <button type="button" className="btn small ghost" onClick={() => link(s.user_id, false)}>Remove</button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="small muted">None yet. The teacher sees only the students listed here.</p>
          )}
          <div className="staff-toolbar mt-8">
            <div className="field grow">
              <label htmlFor="student-search">Add a student</label>
              <input id="student-search" type="search" placeholder="Search students" value={search}
                onChange={(e) => setSearch(e.target.value)} />
            </div>
            <div className="field grow">
              <label htmlFor="student-pick">Student</label>
              <select id="student-pick" value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">Choose…</option>
                {candidates.map((s) => <option key={s.user_id} value={s.user_id}>{s.display_name} · {s.email}</option>)}
              </select>
            </div>
            <button type="button" className="btn accent" disabled={!pick} onClick={() => link(pick, true)}>Add</button>
          </div>
        </div>
      )}
    </Panel>
  );
}
