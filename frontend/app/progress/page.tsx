"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, skillLabel } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { ErrorBox } from "@/components/Feedback";
import { ActivityBars, MasteryBars, MasteryLineChart, SERIES, toLineSeries } from "@/components/charts";
import { MODULES, masteryBand } from "@/lib/modules";
import type { ActivityResponse, Cefr, MasteryPoint, MasteryResponse, RoadmapResponse } from "@/lib/types";
import { Roadmap } from "@/components/Roadmap";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile, Panel, Stat } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Segmented } from "@/components/ui/Segmented";
import { CefrBadge, Tag, levelName } from "@/components/ui/Badge";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { AwardIcon, CheckIcon, ClockIcon, FlameIcon } from "@/components/ui/Icons";

const RANGES = [7, 30, 90] as const;

export default function ProgressPage() {
  const { profile } = useLearner();
  const learnerId = profile?.learner_id;
  const [mastery, setMastery] = useState<MasteryResponse | null>(null);
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [road, setRoad] = useState<RoadmapResponse | null>(null);
  const [points, setPoints] = useState<MasteryPoint[]>([]);
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const [slots, setSlots] = useState<Record<string, number>>({});
  const [view, setView] = useState<"chart" | "table">("chart");
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    setError(null);
    try {
      const [m, a, r] = await Promise.all([
        api<MasteryResponse>("/learner/mastery"),
        api<ActivityResponse>("/learner/activity?days=30"),
        api<RoadmapResponse>("/learner/roadmap"),
      ]);
      setMastery(m);
      setActivity(a);
      setRoad(r);
      // Start the chart with the three weakest practised skills.
      setSlots((prev) => {
        if (Object.keys(prev).length) return prev;
        const pick = m.skills
          .filter((s) => s.attempt_count > 0)
          .sort((x, y) => x.effective_mastery - y.effective_mastery)
          .slice(0, 3);
        return Object.fromEntries(pick.map((s, i) => [s.skill_id, i]));
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (learnerId) loadSummary();
  }, [learnerId, loadSummary]);

  useEffect(() => {
    if (!learnerId) return;
    api<{ points: MasteryPoint[] }>(`/learner/mastery-history?days=${days}`)
      .then((h) => setPoints(h.points))
      .catch((e) => setError((e as Error).message));
  }, [learnerId, days]);

  const practised = useMemo(() => mastery?.skills.filter((s) => s.attempt_count > 0) ?? [], [mastery]);

  const modules = useMemo(
    () =>
      MODULES.map((m) => {
        const skills = mastery?.skills.filter((s) => s.module === m.id) ?? [];
        const done = skills.filter((s) => s.attempt_count > 0);
        const avg = done.length ? done.reduce((t, s) => t + s.effective_mastery, 0) / done.length : null;
        return { ...m, skills: skills.length, practised: done.length, avg };
      }),
    [mastery]
  );

  function toggle(id: string) {
    setSlots((prev) => {
      if (id in prev) {
        const { [id]: _removed, ...rest } = prev;
        return rest;
      }
      const used = new Set(Object.values(prev));
      const free = [0, 1, 2].find((s) => !used.has(s));
      return free === undefined ? prev : { ...prev, [id]: free };
    });
  }

  if (!profile) return null;

  const picks = Object.entries(slots).map(([id, slot]) => ({
    id,
    color: SERIES[slot],
    name: mastery?.skills.find((s) => s.skill_id === id)?.skill_name ?? skillLabel(id),
  }));
  const series = toLineSeries(points, picks);
  const threshold = mastery?.weakness_threshold ?? 60;
  const accuracy = profile.total_attempts
    ? Math.round((100 * profile.correct_attempts) / profile.total_attempts)
    : null;
  const activeDays30 = activity?.days.filter((d) => d.attempts > 0).length ?? 0;
  const mastered = practised.filter((s) => s.effective_mastery >= 80).length;

  return (
    <>
      <PageHeader
        title="Your progress"
        description="How each skill is developing, based on every answer you have given."
        meta={
          <>
            <CefrBadge level={profile.current_level} showLabel />
            <span className="muted small">→</span>
            <CefrBadge level={profile.target_level} showLabel />
            <span className="small muted">
              · learning since {new Date(profile.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </span>
          </>
        }
      />

      <ErrorBox error={error} onRetry={loadSummary} />

      <div className="stack">
        <div className="grid cols-4">
          <Stat label="Answers graded" value={profile.total_attempts} icon={<CheckIcon size={16} />} tone="blue">
            {accuracy === null ? "No answers yet" : `${accuracy}% correct`}
          </Stat>
          <Stat label="Current streak" value={<>{activity?.current_streak ?? 0}<small>days</small></>}
            icon={<FlameIcon size={16} />} tone="orange">
            Active {activeDays30} of the last 30 days
          </Stat>
          <Stat label="Skills mastered" value={<>{mastered}<small>/ {mastery?.skills.length ?? 0}</small></>}
            icon={<AwardIcon size={16} />} tone="violet">
            80/100 or higher
          </Stat>
          <Stat label="Goal" value={profile.target_level} icon={<ClockIcon size={16} />} tone="accent">
            {levelName(profile.target_level)}
          </Stat>
        </div>

        <Panel title={`Your path to ${profile.target_level}`}
          description="Each level, what it needs, and how long it takes at your daily goal">
          {road ? <Roadmap road={road} /> : <SkeletonCard lines={3} />}
        </Panel>

        <Panel title="By module" description="Average mastery of the skills you have practised">
          {mastery ? (
            <div className="grid cols-3">
              {modules.map((m) => {
                const band = masteryBand(m.avg, threshold);
                return (
                  <div key={m.id} className="card tinted" style={{ padding: 16 }}>
                    <div className="row" style={{ flexWrap: "nowrap", marginBottom: 12 }}>
                      <IconTile icon={m.icon(18)} tone={m.tone} size="sm" />
                      <strong style={{ flex: 1 }}>{m.label}</strong>
                      <Tag tone={band.tone}>{band.label}</Tag>
                    </div>
                    <ProgressBar value={m.avg ?? 0} label={`${m.label} mastery`} tone={m.tone} showValue
                      valueText={m.avg === null ? "—" : `${Math.round(m.avg)}/100`} />
                    <p className="xsmall muted" style={{ margin: "8px 0 0" }}>
                      {m.practised} of {m.skills} skills practised
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <SkeletonCard lines={3} />
          )}
        </Panel>

        <Panel
          title="Mastery over time"
          description="Pick up to three skills to compare"
          actions={
            <>
              <Segmented label="Time range" size="sm" value={days} onChange={setDays}
                options={RANGES.map((r) => ({ value: r, label: `${r}d` }))} />
              <Segmented label="View" size="sm" value={view} onChange={setView}
                options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />
            </>
          }
        >
          <div className="chip-row" style={{ marginBottom: 14 }} role="group" aria-label="Skills shown (up to 3)">
            {practised.map((s) => {
              const on = s.skill_id in slots;
              return (
                <button key={s.skill_id} type="button" className="chip" aria-pressed={on}
                  onClick={() => toggle(s.skill_id)} disabled={!on && Object.keys(slots).length >= 3}>
                  {on && <span className="swatch" style={{ background: SERIES[slots[s.skill_id]], margin: 0 }} />}
                  {s.skill_name}
                </button>
              );
            })}
          </div>

          {view === "chart" ? (
            <>
              {picks.length > 1 && (
                <div className="legend">
                  {picks.map((p) => (
                    <span key={p.id}>
                      <span className="swatch" style={{ background: p.color }} />
                      {p.name}
                    </span>
                  ))}
                </div>
              )}
              <MasteryLineChart series={series} threshold={threshold} days={days} />
              <p className="xsmall muted" style={{ margin: "6px 0 0" }}>
                One dot per day you practised: your mastery at the end of that day.
              </p>
            </>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Skill</th>
                    <th>Score</th>
                    <th>Mastery</th>
                    <th>From</th>
                  </tr>
                </thead>
                <tbody>
                  {points
                    .filter((p) => p.skill_id in slots)
                    .map((p, i) => (
                      <tr key={i}>
                        <td className="nowrap">{new Date(p.at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</td>
                        <td>{skillLabel(p.skill_id)}</td>
                        <td><Tag tone={p.score >= 70 ? "good" : "bad"}>{p.score.toFixed(0)}</Tag></td>
                        <td className="strong">{p.mastery.toFixed(1)}</td>
                        <td style={{ textTransform: "capitalize" }}>{p.source}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="split">
          <Panel title="Mastery by skill" description="0–100 · mastery fades after 7 days without practice">
            <MasteryBars skills={practised} threshold={threshold} />
            {mastery && mastery.skills.length > practised.length && (
              <NotStarted skills={mastery.skills.filter((s) => !s.attempt_count)} />
            )}
          </Panel>
          <Panel title="Last 30 days" description="Answers per day">
            {activity ? <ActivityBars days={activity.days} /> : <SkeletonCard lines={2} />}
          </Panel>
        </div>
      </div>
    </>
  );
}

/** Skills without an answer yet, grouped by the level that introduces them. */
function NotStarted({ skills }: { skills: MasteryResponse["skills"] }) {
  const levels = Array.from(new Set(skills.map((s) => s.entry_level))).sort() as Cefr[];
  return (
    <div style={{ marginTop: 16 }}>
      <p className="small strong" style={{ margin: "0 0 8px" }}>Not started yet</p>
      <div className="stack tight">
        {levels.map((level) => (
          <div key={level} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 10 }}>
            <CefrBadge level={level} />
            <span className="chip-row">
              {skills.filter((s) => s.entry_level === level).map((s) => (
                <Tag key={s.skill_id}>{s.skill_name}</Tag>
              ))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
