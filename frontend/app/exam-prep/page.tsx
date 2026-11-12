"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useLearner } from "@/components/useLearner";
import { PageHeader } from "@/components/ui/PageHeader";
import { IconTile } from "@/components/ui/Panel";
import { CefrBadge, Tag } from "@/components/ui/Badge";
import {
  ArrowRightIcon,
  BookOpenIcon,
  BriefcaseIcon,
  CheckIcon,
  ClockIcon,
  ExternalLinkIcon,
  GraduationCapIcon,
  LayersIcon,
  SparklesIcon,
  TrendingUpIcon,
} from "@/components/ui/Icons";
import {
  EXAM_TRACKS,
  EXTERNAL_LINK,
  STUDY4_TEST_LIBRARY,
  suggestedTracks,
  type ExamTrack,
  type ExamTrackId,
} from "@/lib/examPrep";
import { MODULE } from "@/lib/modules";

const TRACK_ICON: Record<ExamTrackId, (size: number) => ReactNode> = {
  ielts: (s) => <GraduationCapIcon size={s} />,
  toeic: (s) => <BriefcaseIcon size={s} />,
  basic: (s) => <BookOpenIcon size={s} />,
};

/** Exam Prep: choose an exam, practise its skills here, take mock tests on STUDY4. */
export default function ExamPrepPage() {
  const { profile } = useLearner();
  if (!profile) return null;
  const suggested = suggestedTracks(profile.current_level);

  return (
    <>
      <PageHeader
        eyebrow="Mock tests"
        title="Exam Prep"
        description="Pick the exam you are aiming for. Build its skills here, then sit a real mock test on STUDY4."
        meta={
          <>
            <CefrBadge level={profile.current_level} showLabel />
            <Tag>Target {profile.target_level}</Tag>
          </>
        }
      />

      <Study4Feature />

      <div className="section-title">
        <h2 id="exam-tracks">Choose your exam</h2>
        <span className="small muted hide-mobile">STUDY4 opens in a new tab</span>
      </div>
      <div className="exam-grid" role="list" aria-labelledby="exam-tracks">
        {EXAM_TRACKS.map((t) => (
          <ExamCard key={t.id} track={t} suggested={suggested.includes(t.id)} level={profile.current_level} />
        ))}
      </div>

      <div className="section-title">
        <h2 id="exam-steps">How to prepare</h2>
      </div>
      <ol className="exam-steps" aria-labelledby="exam-steps">
        <Step n={1} icon={<LayersIcon size={18} />} title="Build the skills">
          Short daily sessions in <Link href="/practice">Practice</Link>: vocabulary, grammar,
          listening and speaking, all graded.
        </Step>
        <Step n={2} icon={<ClockIcon size={18} />} title="Take a timed mock test">
          Sit a full test on STUDY4 under exam timing to see where you really stand.
        </Step>
        <Step n={3} icon={<TrendingUpIcon size={18} />} title="Fix what it shows">
          Come back and work on the weak spots. <Link href="/progress">Progress</Link> tracks every
          skill.
        </Step>
      </ol>

      <p className="exam-note small muted">
        STUDY4 is an independent website, not part of Banana English. We only link to it: nothing
        from STUDY4 is copied or stored here, and its own terms and prices apply.
      </p>
    </>
  );
}

function Study4Feature() {
  return (
    <section className="card exam-hero" aria-labelledby="study4-title">
      <div className="exam-hero-text">
        <p className="eyebrow">STUDY4 · Mock test library</p>
        <h2 id="study4-title">Want to try a real exam paper?</h2>
        <p className="secondary">
          Practise full IELTS and TOEIC mock tests on STUDY4, timed like the real thing, then bring
          the results back here.
        </p>
        <ul className="exam-checks">
          {["Full-length tests", "Real exam timing", "IELTS and TOEIC"].map((x) => (
            <li key={x}>
              <CheckIcon size={15} /> {x}
            </li>
          ))}
        </ul>
        <a
          href={STUDY4_TEST_LIBRARY}
          {...EXTERNAL_LINK}
          className="btn accent large"
          aria-label="Open the STUDY4 mock test library (opens in a new tab)"
        >
          Open the STUDY4 test library <ExternalLinkIcon size={17} />
        </a>
      </div>
      <MockSheet />
    </section>
  );
}

/** Decoration: an answer sheet with a timer, so the card reads as "exam" at a glance. */
function MockSheet() {
  const rows = [1, 2, 3, 4];
  return (
    <div className="exam-sheet" aria-hidden>
      <div className="exam-sheet-head">
        <span>Mock test</span>
        <span className="exam-timer">
          <ClockIcon size={13} /> 120:00
        </span>
      </div>
      {rows.map((r) => (
        <div key={r} className="exam-sheet-row">
          <span className="exam-q">{r}</span>
          {["A", "B", "C", "D"].map((o, i) => (
            <span key={o} className={`exam-bubble${(r + i) % 4 === 1 ? " on" : ""}`}>
              {o}
            </span>
          ))}
        </div>
      ))}
      <div className="exam-sheet-foot">
        <span className="exam-bar">
          <span style={{ width: "62%" }} />
        </span>
        <span>62%</span>
      </div>
    </div>
  );
}

function ExamCard({ track: t, suggested, level }: { track: ExamTrack; suggested: boolean; level: string }) {
  const titleId = `exam-${t.id}`;
  return (
    <article className={`card exam-card tone-${t.tone}`} role="listitem" aria-labelledby={titleId}>
      <div className="row-between" style={{ alignItems: "flex-start" }}>
        <IconTile icon={TRACK_ICON[t.id](24)} tone={t.tone} size="lg" />
        {suggested && (
          <Tag tone="accent" title={`Matches your current level (${level})`}>
            <SparklesIcon size={12} /> Suits your level
          </Tag>
        )}
      </div>

      <div>
        <h3 id={titleId} className="exam-name">
          {t.name}
        </h3>
        <p className="small muted exam-sub">{t.subtitle}</p>
        <p className="small secondary exam-blurb">{t.blurb}</p>
      </div>

      <ul className="exam-facts" aria-label="Format">
        {t.facts.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>

      <div>
        <p className="exam-label">Skills</p>
        <ul className="chip-row exam-list">
          {t.skills.map((s) => (
            <li key={s}>
              <Tag tone={t.tone}>{s}</Tag>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="exam-label">Practise here first</p>
        <ul className="chip-row exam-list">
          {t.practiseHere.map((id) => {
            const m = MODULE[id];
            return (
              <li key={id}>
                <Link href={m.href} className="chip exam-module">
                  {m.icon(13)}
                  {m.label}
                  <ArrowRightIcon size={12} />
                </Link>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="card-foot exam-foot">
        <a
          href={t.url}
          {...EXTERNAL_LINK}
          className="btn block"
          aria-label={`Practise on STUDY4: ${t.destination} (opens in a new tab)`}
        >
          Practise on STUDY4 <ExternalLinkIcon size={16} />
        </a>
      </div>
    </article>
  );
}

function Step({ n, icon, title, children }: { n: number; icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <li className="card exam-step">
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <span className="exam-step-n" aria-hidden>
          {n}
        </span>
        <IconTile icon={icon} size="sm" />
      </div>
      <h3>{title}</h3>
      <p className="small secondary">{children}</p>
    </li>
  );
}
