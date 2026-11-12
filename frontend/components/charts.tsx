"use client";

import { useEffect, useMemo, useState } from "react";
import type { MasteryPoint, SkillMastery } from "@/lib/types";

/** Categorical slots 1-3 of the validated reference palette (all-pairs CVD-safe, both modes).
 *  A chart never shows more than three series; colour follows the skill, not its rank. */
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

/** Measured container width via a callback ref, so it also works when the chart element
 *  mounts later (e.g. after data arrives) — SVG text then renders at its true pixel size. */
function useWidth<T extends HTMLElement>(fallback = 640) {
  const [el, setEl] = useState<T | null>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    if (!el) return;
    setWidth(Math.max(280, el.getBoundingClientRect().width));
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return { ref: setEl, width };
}

const fmtDate = (t: number) =>
  new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export interface LineSeries {
  id: string;
  name: string;
  color: string;
  points: { t: number; v: number; score: number }[];
}

const DAY = 86400e3;

/** Noon of the local day `daysAgo` days before today: where a day's point is drawn. */
function dayNoon(daysAgo: number, now = new Date()): number {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysAgo, 12).getTime();
}

/** Mastery (0-100) over the selected range, one line per selected skill, weakness threshold
 *  marked. The x axis always spans the whole range (7/30/90 days ending today), one tick per
 *  date, so a learner with two days of practice sees two points at the right end. */
export function MasteryLineChart({ series, threshold, days }: { series: LineSeries[]; threshold: number; days: number }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 240;
  const m = { top: 12, right: 18, bottom: 28, left: 34 };
  const w = width - m.left - m.right;
  const h = height - m.top - m.bottom;

  // Whole days: from the start of the first day to the end of today.
  const t0 = dayNoon(days - 1) - DAY / 2;
  const t1 = dayNoon(0) + DAY / 2;
  const shown = series.map((s) => ({ ...s, points: s.points.filter((p) => p.t >= t0 && p.t <= t1) }));
  const all = shown.flatMap((s) => s.points.map((p) => p.t));
  if (all.length === 0) {
    return <p className="muted">No answers for these skills in the last {days} days. Practise to see your curve.</p>;
  }
  const x = (t: number) => m.left + ((t - t0) / (t1 - t0)) * w;
  const y = (v: number) => m.top + (1 - v / 100) * h;
  const ticks = [0, 25, 50, 75, 100];
  // One label per date, spaced so they never overlap; today is always labelled.
  const step = Math.max(1, Math.ceil(days / Math.max(2, Math.floor(w / 64))));
  const xTicks: number[] = [];
  for (let d = 0; d < days; d += step) xTicks.push(dayNoon(d));
  const times = Array.from(new Set(all)).sort((a, b) => a - b);

  const valueAt = (s: LineSeries, t: number) => {
    let last: LineSeries["points"][number] | undefined;
    for (const p of s.points) if (p.t <= t) last = p;
    return last;
  };

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * width;
    let best = times[0];
    for (const t of times) if (Math.abs(x(t) - px) < Math.abs(x(best) - px)) best = t;
    setHover(best);
  }

  return (
    <div className="viz" ref={ref}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label={`Mastery over the last ${days} days for the selected skills`}>
        <g className="axis">
          {ticks.map((v) => (
            <g key={v}>
              <line className="gridline" x1={m.left} x2={m.left + w} y1={y(v)} y2={y(v)} />
              <text x={m.left - 8} y={y(v) + 4} textAnchor="end">{v}</text>
            </g>
          ))}
          {xTicks.map((t) => {
            const px = x(t);
            const anchor = px - m.left < 24 ? "start" : m.left + w - px < 24 ? "end" : "middle";
            return (
              <text key={t} x={px} y={height - 8} textAnchor={anchor}>
                {fmtDate(t)}
              </text>
            );
          })}
        </g>
        <line className="threshold" x1={m.left} x2={m.left + w} y1={y(threshold)} y2={y(threshold)} />
        <text className="threshold-label" x={m.left + 4} y={y(threshold) - 5}>weak below {threshold}</text>
        {hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + h} stroke="var(--text-muted)"
                strokeWidth={1} />
        )}
        {shown.map((s) => (
          <g key={s.id}>
            <polyline fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round"
                      strokeLinecap="round"
                      points={s.points.map((p) => `${x(p.t)},${y(p.v)}`).join(" ")} />
            {/* A dot on every day practised, so a single day still shows. */}
            {s.points.map((p) => (
              <circle key={p.t} cx={x(p.t)} cy={y(p.v)} r={hover === p.t ? 5.5 : 4} fill={s.color}
                      stroke="var(--surface-1)" strokeWidth={2} />
            ))}
          </g>
        ))}
        <rect x={m.left} y={m.top} width={w} height={h} fill="transparent"
              onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: Math.max(0, Math.min(x(hover) + 12, width - 200)), top: 8 }}>
          <div className="small muted">{new Date(hover).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} · end of day</div>
          {shown.map((s) => {
            const p = valueAt(s, hover);
            return p ? (
              <div key={s.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <span><span className="legend"><span className="swatch" style={{ background: s.color }} /></span>{s.name}</span>
                <strong>{p.v.toFixed(0)}</strong>
              </div>
            ) : null;
          })}
        </div>
      )}
    </div>
  );
}

/** Current mastery per practised skill: one colour (magnitude), threshold rule, weak flag. */
export function MasteryBars({ skills, threshold }: { skills: SkillMastery[]; threshold: number }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<string | null>(null);
  const rows = useMemo(() => [...skills].sort((a, b) => a.effective_mastery - b.effective_mastery),
                       [skills]);
  if (!rows.length) return <p className="muted">No skills practised yet.</p>;
  const labelW = Math.min(170, width * 0.38);
  const flagW = 58;
  const barH = 16;
  const gap = 10;
  const top = 18;
  const w = width - labelW - flagW;
  const height = top + rows.length * (barH + gap);
  const x = (v: number) => labelW + (v / 100) * w;

  return (
    <div className="viz" ref={ref}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Current mastery per skill">
        {[0, 50, 100].map((v) => (
          <g key={v} className="axis">
            <line className="gridline" x1={x(v)} x2={x(v)} y1={top - 4} y2={height} />
            <text x={x(v)} y={10} textAnchor="middle">{v}</text>
          </g>
        ))}
        {rows.map((s, i) => {
          const y0 = top + i * (barH + gap);
          const end = x(s.effective_mastery);
          const r = Math.min(4, end - labelW);
          return (
            <g key={s.skill_id} onPointerEnter={() => setHover(s.skill_id)}
               onPointerLeave={() => setHover(null)}>
              <rect x={0} y={y0 - gap / 2} width={width} height={barH + gap} fill="transparent" />
              <text x={labelW - 8} y={y0 + barH / 2 + 4} textAnchor="end" fontSize={12}
                    fill="var(--text-secondary)">
                {s.skill_name.length > 22 ? s.skill_name.slice(0, 21) + "…" : s.skill_name}
              </text>
              <path fill={hover && hover !== s.skill_id ? "var(--seq-250)" : "var(--series-1)"}
                    d={`M${labelW},${y0} H${end - r} Q${end},${y0} ${end},${y0 + r}
                        V${y0 + barH - r} Q${end},${y0 + barH} ${end - r},${y0 + barH} H${labelW} Z`} />
              {s.is_weak && (
                <text x={width - flagW + 6} y={y0 + barH / 2 + 4} fontSize={11} fontWeight={600}
                      fill="var(--critical-text)">⚠ weak</text>
              )}
            </g>
          );
        })}
        <line className="threshold" x1={x(threshold)} x2={x(threshold)} y1={top - 4} y2={height} />
      </svg>
      {hover && (() => {
        const s = rows.find((r) => r.skill_id === hover)!;
        const i = rows.indexOf(s);
        return (
          <div className="tooltip" style={{ left: Math.min(x(s.effective_mastery) + 8, width - 190),
                                            top: top + i * (barH + gap) + barH }}>
            <strong>{s.skill_name}</strong>
            <div>Mastery {s.effective_mastery.toFixed(0)}/100{s.effective_mastery !== s.mastery &&
              <span className="muted"> (stored {s.mastery.toFixed(0)}, faded)</span>}</div>
            <div className="muted">{s.correct_count}/{s.attempt_count} correct</div>
          </div>
        );
      })()}
    </div>
  );
}

/** Attempts per day (single series); 7 days get weekday labels, longer ranges every 5th date. */
export function ActivityBars({ days }: { days: { date: string; attempts: number }[] }) {
  const { ref, width } = useWidth<HTMLDivElement>(320);
  const height = 120;
  const max = Math.max(1, ...days.map((d) => d.attempts));
  const slot = width / days.length;
  const barW = Math.min(28, slot - 6);
  return (
    <div className="viz" ref={ref}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Answers per day, last ${days.length} days`}>
        <line className="gridline" x1={0} x2={width} y1={height - 18} y2={height - 18} />
        {days.map((d, i) => {
          const hBar = d.attempts ? Math.max(4, ((height - 30) * d.attempts) / max) : 0;
          const cx = slot * i + slot / 2;
          const y0 = height - 18 - hBar;
          return (
            <g key={d.date}>
              <title>{`${d.date}: ${d.attempts} attempts`}</title>
              {hBar > 0 && (
                <path fill="var(--series-1)"
                      d={`M${cx - barW / 2},${height - 18} V${y0 + 4} Q${cx - barW / 2},${y0} ${cx - barW / 2 + 4},${y0}
                          H${cx + barW / 2 - 4} Q${cx + barW / 2},${y0} ${cx + barW / 2},${y0 + 4} V${height - 18} Z`} />
              )}
              {(days.length <= 10 || i % 5 === 0 || i === days.length - 1) && (
                <text x={cx} y={height - 4} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
                  {new Date(d.date + "T00:00:00").toLocaleDateString(undefined,
                    days.length <= 10 ? { weekday: "narrow" } : { day: "numeric", month: "short" })}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** One point per skill per day: the mastery at the end of that day. Per-attempt snapshots are
 *  kept for the table view; at 7-90 day ranges intra-day steps would only draw vertical noise. */
export function toLineSeries(points: MasteryPoint[], picks: { id: string; name: string; color: string }[]): LineSeries[] {
  return picks.map((p) => {
    const byDay = new Map<string, { t: number; v: number; score: number }>();
    for (const pt of points.filter((x) => x.skill_id === p.id)) {
      const d = new Date(pt.at);
      const key = d.toDateString();
      const endOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12).getTime();
      byDay.set(key, { t: endOfDay, v: pt.mastery, score: pt.score });
    }
    return { ...p, points: [...byDay.values()].sort((a, b) => a.t - b.t) };
  });
}
