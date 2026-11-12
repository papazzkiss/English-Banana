"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useLearner } from "@/components/useLearner";
import { MonkeyAvatar } from "@/components/MonkeyAvatar";
import { MONKEY_PATH, useMonkey } from "@/components/MonkeyProvider";
import { CefrBadge } from "@/components/ui/Badge";
import {
  BarChartIcon, GraduationCapIcon, HomeIcon, LayersIcon, LockIcon, LogOutIcon,
} from "@/components/ui/Icons";
import { ROLE_LABEL, staffLinks } from "@/lib/access";
import { MODULES } from "@/lib/modules";

/** Exam Prep: exam tracks with links to mock tests on STUDY4. */
const EXAM_PREP_PATH = "/exam-prep";

/** The screens a learner lives in: a sidebar on desktop, a header and a bottom tab bar on
 * tablets and phones. The sign-in page ("/") gets only a slim public header. */
export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  if (path === "/") {
    return (
      <>
        <header className="public-header">
          <div className="container">
            <Brand href="/" />
          </div>
        </header>
        <main id="main" className="public-main">
          <div className="container">{children}</div>
        </main>
      </>
    );
  }
  return <SignedInShell path={path}>{children}</SignedInShell>;
}

function Brand({ href }: { href: string }) {
  return (
    <Link href={href} className="brand" aria-label="Banana English home">
      <span className="brand-mark" aria-hidden>🍌</span>
      <span className="brand-name">Banana English</span>
    </Link>
  );
}

function SignedInShell({ path, children }: { path: string; children: ReactNode }) {
  const { profile, signOut } = useLearner({ redirect: false });
  const monkey = useMonkey();
  const onMonkey = path === MONKEY_PATH;
  const monkeyBusy = !onMonkey && (monkey.pending || monkey.speaking || monkey.unread);
  const monkeyStatus = monkey.unread ? "New reply" : monkeyBusy ? "Replying" : "";
  const inPractice = path.startsWith("/practice");
  const inExamPrep = path.startsWith(EXAM_PREP_PATH);
  // Staff screens by role (menu only; the API checks the role on every request).
  const staff = staffLinks(profile?.role);
  const activeStaff = staff
    .filter((l) => path === l.href || path.startsWith(`${l.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href; // /admin/users, not /admin

  const current = (active: boolean) => (active ? ("page" as const) : undefined);

  const monkeyIcon = (
    <span className="nav-icon monkey-icon">
      <MonkeyAvatar mini size={22} />
      {monkeyBusy && <span className="nav-dot" aria-hidden />}
    </span>
  );

  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <aside className="sidebar">
        <Brand href="/dashboard" />
        <nav className="side-nav" aria-label="Main">
          <Link href="/dashboard" className="side-link" aria-current={current(path === "/dashboard")}>
            <HomeIcon size={19} />
            Home
          </Link>
          <Link
            href="/practice"
            className={`side-link${inPractice ? " in-section" : ""}`}
            aria-current={current(path === "/practice")}
          >
            <LayersIcon size={19} />
            Practice
          </Link>
          <ul className="side-sub">
            {MODULES.map((m) => (
              <li key={m.id}>
                <Link href={m.href} className="side-link sub" aria-current={current(path.startsWith(m.href))}>
                  <span className={`sub-dot tone-${m.tone}`} aria-hidden />
                  {m.label}
                </Link>
              </li>
            ))}
          </ul>
          {monkey.enabled && (
            <Link
              href={MONKEY_PATH}
              className="side-link"
              aria-label="AI Monkey"
              aria-describedby="monkey-nav-status"
              aria-current={current(onMonkey)}
            >
              {monkeyIcon}
              AI Monkey
              {monkey.unread && !onMonkey && <span className="nav-badge">New</span>}
            </Link>
          )}
          <Link href={EXAM_PREP_PATH} className="side-link" aria-current={current(inExamPrep)}>
            <GraduationCapIcon size={19} />
            Exam Prep
          </Link>
          <Link href="/progress" className="side-link" aria-current={current(path.startsWith("/progress"))}>
            <BarChartIcon size={19} />
            Progress
          </Link>
          {staff.length > 0 && (
            <>
              <p className="side-heading">{profile?.role === "admin" ? "Administration" : "Teaching"}</p>
              {staff.map((l) => (
                <Link key={l.href} href={l.href} className="side-link" aria-current={current(l.href === activeStaff)}>
                  <LockIcon size={17} />
                  {l.label}
                </Link>
              ))}
            </>
          )}
        </nav>
        <span id="monkey-nav-status" className="sr-only">
          {monkeyStatus}
        </span>

        <div className="side-user">
          {profile ? (
            <>
              <span className="avatar" aria-hidden>
                {profile.display_name.slice(0, 1).toUpperCase()}
              </span>
              <div className="side-user-text">
                <strong>{profile.display_name}</strong>
                <span>
                  {profile.role !== "student" ? `${ROLE_LABEL[profile.role]} · ` : ""}
                  {profile.current_level} → {profile.target_level}
                </span>
              </div>
              <button type="button" className="btn icon ghost" onClick={signOut} aria-label="Sign out" title="Sign out">
                <LogOutIcon size={17} />
              </button>
            </>
          ) : (
            <span className="skeleton" style={{ width: "100%", height: 36 }} aria-hidden />
          )}
        </div>
      </aside>

      <header className="mobile-header">
        <Brand href="/dashboard" />
        {profile && (
          <div className="mobile-user">
            {staff.length > 0 && (
              <Link href={staff[0].href} className="btn icon ghost" aria-label={staff[0].label} title={staff[0].label}>
                <LockIcon size={17} />
              </Link>
            )}
            <CefrBadge level={profile.current_level} />
            <button type="button" className="btn icon ghost" onClick={signOut} aria-label="Sign out" title="Sign out">
              <LogOutIcon size={17} />
            </button>
          </div>
        )}
      </header>

      <main id="main" className="app-main">
        <div className="container">{children}</div>
      </main>

      <nav className="tabbar" aria-label="Main">
        <TabLink href="/dashboard" label="Home" active={path === "/dashboard"} icon={<HomeIcon size={21} />} />
        <TabLink href="/practice" label="Practice" active={inPractice} icon={<LayersIcon size={21} />} />
        {monkey.enabled && (
          <TabLink href={MONKEY_PATH} label="AI Monkey" active={onMonkey} icon={monkeyIcon} />
        )}
        <TabLink href={EXAM_PREP_PATH} label="Exam Prep" active={inExamPrep} icon={<GraduationCapIcon size={21} />} />
        <TabLink href="/progress" label="Progress" active={path.startsWith("/progress")} icon={<BarChartIcon size={21} />} />
      </nav>
    </div>
  );
}

function TabLink({ href, label, icon, active }: { href: string; label: string; icon: ReactNode; active: boolean }) {
  return (
    <Link href={href} className="tab" aria-current={active ? "page" : undefined}>
      {icon}
      <span>{label}</span>
    </Link>
  );
}
