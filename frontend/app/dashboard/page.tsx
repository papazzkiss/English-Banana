"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BANK_HREF, isBankItem, type BankSkill } from "@/lib/bank";
import { MODULE_HREF, api, skillLabel } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import {
  ErrorBox,
  KIND_LABEL,
  RecommendationRow,
  recommendationHref,
  recommendationTitle,
  type SkillNames,
} from "@/components/Feedback";
import { MODULE } from "@/lib/modules";
import type {
  ActivityResponse,
  MasteryResponse,
  Module,
  RecentAttempt,
  Recommendation,
  RoadmapResponse,
  WeakSkill,
} from "@/lib/types";
import { currentMilestone } from "@/components/Roadmap";
import {
  ArrowRightIcon,
  AwardIcon,
  CheckIcon,
  FlameIcon,
  TargetIcon,
  TrendingUpIcon,
} from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile, Panel, Stat } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tag } from "@/components/ui/Badge";

/** Answers per day that count as "done for today". */
const DAILY_GOAL = 10;

interface DashboardData {
  recs: Recommendation[];
  weak: WeakSkill[];
  activity: ActivityResponse;
  recent: RecentAttempt[];
  mastery: MasteryResponse;
  road: RoadmapResponse | null;
}

/** Where to practise an answered item again. */
function attemptHref(a: RecentAttempt): string {
  if (isBankItem(a.item_id) && a.module in BANK_HREF) return BANK_HREF[a.module as BankSkill];
  if (a.module === "grammar" || a.module === "speaking") return MODULE_HREF[a.module](a.item_id);
  if (a.module === "listening") return MODULE_HREF.listening(a.item_id.replace(/\.q\d+$/, ""));
  return MODULE[a.module].href;
}

function greeting(now = new Date()) {
  const h = now.getHours();
  return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function timeAgo(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

export default function Dashboard() {
  const { profile } = useLearner();
  const learnerId = profile?.learner_id;
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [r, w, a, recent, m, road] = await Promise.all([
        api<{ recommendations: Recommendation[] }>("/recommendation/next?n=5"),
        api<{ skills: WeakSkill[] }>("/learner/weak-skills?limit=4"),
        api<ActivityResponse>("/learner/activity?days=7"),
        api<RecentAttempt[]>("/learner/attempts?limit=6"),
        api<MasteryResponse>("/learner/mastery"),
        api<RoadmapResponse>("/learner/roadmap").catch(() => null),
      ]);
      setData({ recs: r.recommendations, weak: w.skills, activity: a, recent, mastery: m, road });
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (learnerId) load();
  }, [learnerId, load]);

  if (!profile) return null;

  const firstName = profile.display_name.split(" ")[0];
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <>
      <PageHeader
        eyebrow={today}
        title={`${greeting()}, ${firstName}`}
        description={
          <>
            You are working from <strong>{profile.current_level}</strong> towards{" "}
            <strong>{profile.target_level}</strong>. Here is what to do next.
          </>
        }
      />

      <ErrorBox error={error} onRetry={load} />

      {!data && !error ? <DashboardSkeleton /> : data && <DashboardBody data={data} accuracy={
        profile.total_attempts ? Math.round((100 * profile.correct_attempts) / profile.total_attempts) : null
      } total={profile.total_attempts} />}
    </>
  );
}

function DashboardBody({ data, accuracy, total }: { data: DashboardData; accuracy: number | null; total: number }) {
  const { recs, weak, activity, recent, mastery, road } = data;
  const [top, ...rest] = recs;
  const names = Object.fromEntries(mastery.skills.map((s) => [s.skill_id, s.skill_name]));
  const todayCount = activity.days.at(-1)?.attempts ?? 0;
  const practised = mastery.skills.filter((s) => s.attempt_count > 0);
  const mastered = practised.filter((s) => s.effective_mastery >= 80).length;

  return (
    <div className="stack">
      {top ? <ContinueCard rec={top} names={names} /> : <CaughtUp />}

      {road && <MilestoneStrip road={road} />}

      <div className="grid cols-4">
        <Stat label="Streak" value={<>{activity.current_streak}<small>{activity.current_streak === 1 ? "day" : "days"}</small></>}
          icon={<FlameIcon size={16} />} tone="orange">
          <WeekStrip days={activity.days} />
        </Stat>
        <Stat label="Today" value={<>{todayCount}<small>/ {DAILY_GOAL}</small></>} icon={<TargetIcon size={16} />} tone="accent">
          <ProgressBar value={(100 * todayCount) / DAILY_GOAL} label="Daily goal" size="sm"
            tone={todayCount >= DAILY_GOAL ? "good" : "accent"} />
          <span className="xsmall">{todayCount >= DAILY_GOAL ? "Daily goal reached" : `${DAILY_GOAL - todayCount} more to reach your goal`}</span>
        </Stat>
        <Stat label="Accuracy" value={accuracy === null ? "—" : <>{accuracy}<small>%</small></>} icon={<CheckIcon size={16} />} tone="green">
          {total} answers graded
        </Stat>
        <Stat label="Skills mastered" value={<>{mastered}<small>/ {mastery.skills.length}</small></>} icon={<AwardIcon size={16} />} tone="violet">
          {practised.length} of {mastery.skills.length} skills practised
        </Stat>
      </div>

      <div className="split">
        <Panel title="Up next" description="Picked from your weakest skills and due reviews" flush
          actions={<Link href="/practice" className="btn small ghost">All practice</Link>}>
          {rest.length ? (
            <ul className="list">
              {rest.map((r) => (
                <li key={`${r.skill_id}-${r.priority}`}>
                  <RecommendationRow rec={r} names={names} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact title="Nothing else queued" description="Finish the task above and new suggestions will appear." />
          )}
          <div style={{ height: 8 }} />
        </Panel>

        <Panel title="Focus skills" description={`Below ${mastery.weakness_threshold}/100 mastery`}>
          {weak.length ? (
            <ul className="list">
              {weak.map((w) => (
                <li key={w.skill_id} className="list-row" style={{ display: "block" }}>
                  <div className="row-between" style={{ marginBottom: 6 }}>
                    <span className="row-title">{w.skill_name}</span>
                    <span className="small num strong">{w.effective_mastery.toFixed(0)}</span>
                  </div>
                  <ProgressBar value={w.effective_mastery} label={`${w.skill_name} mastery`} size="sm" tone="orange" />
                  <span className="row-sub mt-8">
                    {MODULE[w.module].label} · {w.attempt_count} answers
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact icon={<CheckIcon size={24} />} title="No weak skills"
              description={`Every skill you have practised is above ${mastery.weakness_threshold}/100.`} />
          )}
        </Panel>
      </div>

      <Panel title="Recent activity" flush
        actions={<Link href="/progress" className="btn small ghost"><TrendingUpIcon size={15} /> Progress</Link>}>
        {recent.length ? (
          <ul className="list">
            {recent.map((a) => {
              const m = MODULE[a.module];
              const tone = a.is_correct === null ? "neutral" : a.is_correct ? "good" : "bad";
              return (
                <li key={a.attempt_id}>
                  <Link href={attemptHref(a)} className="list-row">
                    <IconTile icon={m.icon(17)} tone={m.tone} size="sm" />
                    <span className="row-main">
                      <span className="row-title">
                        {a.parts.length ? m.label : names[a.skill_id] ?? skillLabel(a.skill_id)}
                      </span>
                      <span className="row-sub">“{a.answer || "—"}”</span>
                    </span>
                    <span className="row-end">
                      <span className="xsmall muted nowrap">{timeAgo(a.submitted_at)}</span>
                      {a.parts.length ? (
                        // One spoken answer, graded twice: both scores in one row.
                        a.parts.map((p) => (
                          <Tag key={p.skill_id} tone={p.score >= 70 ? "good" : "bad"}
                            title={names[p.skill_id] ?? skillLabel(p.skill_id)}>
                            {PART_LABEL[p.skill_id] ?? skillLabel(p.skill_id)} {Math.round(p.score)}
                          </Tag>
                        ))
                      ) : (
                        <Tag tone={tone}>{a.score === null ? a.status : `${Math.round(a.score)}`}</Tag>
                      )}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState compact title="No answers yet" description="Your latest answers and their scores will show up here."
            actionText="Start practising" actionHref="/practice" />
        )}
        <div style={{ height: 8 }} />
      </Panel>
    </div>
  );
}

/** Short names for the scores inside one spoken answer. */
const PART_LABEL: Record<string, string> = { "speaking.grammar": "Grammar", "speaking.fluency": "Fluency" };

/** Where the learner is on the A1 → B2 path, in one line; details on Progress. */
function MilestoneStrip({ road }: { road: RoadmapResponse }) {
  const level = currentMilestone(road);
  if (!level) return null;
  const next = road.levels[road.levels.indexOf(level) + 1];
  const share = level.skills.length + level.words_total
    ? (100 * (level.skills_mastered + level.words_started)) / (level.skills.length + level.words_total)
    : 100;
  return (
    <Link href="/progress" className="card interactive milestone">
      <span className="milestone-path" aria-label={`Path: ${road.levels.map((l) => l.level).join(", ")}`}>
        {road.levels.map((l) => (
          <span key={l.level} className="roadmap-level" data-state={l.complete ? "done" : l === level ? "current" : "next"}>
            {l.level}
          </span>
        ))}
      </span>
      <span className="row-main">
        <span className="row-title">
          {level.complete ? `${level.level} complete` : `Working on ${level.level}`}
          {next && !level.complete ? ` · then ${next.level}` : ""}
        </span>
        <span className="row-sub">
          {level.skills_mastered}/{level.skills.length} skills mastered · {level.words_started}/{level.words_total} words
          started · about {Math.max(1, level.weeks_left)} week{level.weeks_left > 1 ? "s" : ""} at {road.daily_goal} answers a day
        </span>
      </span>
      <span style={{ width: 120 }} className="hide-mobile">
        <ProgressBar value={share} label={`${level.level} progress`} size="sm" />
      </span>
      <ArrowRightIcon size={16} className="muted" />
    </Link>
  );
}

/** The single most useful thing to do now. */
function ContinueCard({ rec, names }: { rec: Recommendation; names: SkillNames }) {
  const m = MODULE[rec.module];
  return (
    <section className="card hero" aria-labelledby="continue-title">
      <div className="row-between" style={{ alignItems: "center", gap: 20 }}>
        <div className="row" style={{ flex: "1 1 380px", alignItems: "flex-start", flexWrap: "nowrap", gap: 16 }}>
          <IconTile icon={m.icon(24)} tone={m.tone} size="lg" />
          <div style={{ minWidth: 0 }}>
            <p className="eyebrow" style={{ marginBottom: 4 }}>
              Continue learning · {KIND_LABEL[rec.kind]}
            </p>
            <h2 id="continue-title" style={{ fontSize: "1.3rem", margin: "0 0 4px" }}>
              {recommendationTitle(rec, names)}
            </h2>
            <p className="secondary small" style={{ margin: 0 }}>
              {rec.reason}
            </p>
          </div>
        </div>
        <Link href={recommendationHref(rec)} className="btn large">
          Start <ArrowRightIcon size={18} />
        </Link>
      </div>
    </section>
  );
}

function CaughtUp() {
  return (
    <section className="card hero">
      <div className="row-between">
        <div className="row" style={{ flexWrap: "nowrap", gap: 16 }}>
          <IconTile icon={<CheckIcon size={24} />} tone="green" size="lg" />
          <div>
            <h2 style={{ margin: "0 0 4px" }}>You are all caught up</h2>
            <p className="secondary small" style={{ margin: 0 }}>No reviews are due. Pick any module to keep going.</p>
          </div>
        </div>
        <Link href="/practice" className="btn large">
          Browse practice <ArrowRightIcon size={18} />
        </Link>
      </div>
    </section>
  );
}

/** Last 7 days: a filled dot for each day with at least one answer. */
function WeekStrip({ days }: { days: { date: string; attempts: number }[] }) {
  return (
    <div className="week" aria-label={`Active on ${days.filter((d) => d.attempts).length} of the last 7 days`}>
      {days.map((d, i) => (
        <span key={d.date} className={`week-day${d.attempts ? " on" : ""}${i === days.length - 1 ? " today" : ""}`}
          title={`${d.date}: ${d.attempts} answers`}>
          <i />
          <span>{new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "narrow" })}</span>
        </span>
      ))}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading your dashboard">
      <div className="card hero">
        <div className="row" style={{ gap: 16 }}>
          <Skeleton width={52} height={52} radius={14} />
          <div style={{ flex: 1 }} className="stack tight">
            <Skeleton width="30%" height={12} />
            <Skeleton width="55%" height={22} />
            <Skeleton width="70%" height={14} />
          </div>
        </div>
      </div>
      <div className="grid cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card stat">
            <Skeleton width="50%" height={12} />
            <Skeleton width="40%" height={30} />
            <Skeleton width="80%" height={10} />
          </div>
        ))}
      </div>
      <div className="split">
        <SkeletonCard lines={5} />
        <SkeletonCard lines={4} />
      </div>
    </div>
  );
}

