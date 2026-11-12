"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { notifyLearnerChanged, useLearner } from "@/components/useLearner";
import type { Cefr } from "@/lib/types";
import { ErrorBox } from "@/components/Feedback";
import { ArrowRightIcon, CheckIcon, SpeakingIcon, TargetIcon } from "@/components/ui/Icons";
import { IconTile, Spinner } from "@/components/ui/Panel";
import { Segmented } from "@/components/ui/Segmented";
import { levelName } from "@/components/ui/Badge";

const START_LEVELS: Cefr[] = ["A1", "A2", "B1", "B2"];
const GOAL_LEVELS: Cefr[] = ["A2", "B1", "B2", "C1"];

export default function SignIn() {
  const router = useRouter();
  const { profile, ready } = useLearner({ redirect: false });
  const [mode, setMode] = useState<"register" | "login">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [level, setLevel] = useState<Cefr>("A1");
  const [target, setTarget] = useState<Cefr>("B2");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in: go straight to the app.
  useEffect(() => {
    if (ready && profile) router.replace("/dashboard");
  }, [ready, profile, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        await post("/auth/register", {
          email,
          password,
          display_name: name.trim(),
          current_level: level,
          target_level: target,
          native_language: "vi",
        });
      } else {
        await post("/auth/login", { email, password });
      }
      notifyLearnerChanged();
      router.push("/dashboard");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const register = mode === "register";
  const canSubmit = email.includes("@") && password.length >= (register ? 8 : 1) && (!register || name.trim());

  return (
    <div className="auth">
      <section className="auth-pitch">
        <h1>
          English practice that <mark>adapts to you</mark>.
        </h1>
        <p className="lead">
          Banana English tracks every grammar rule, word and listening skill you practise, and
          plans your next exercise around what you get wrong.
        </p>
        <ul className="features">
          <li>
            <IconTile icon={<TargetIcon size={20} />} tone="violet" />
            <div>
              <strong>A plan built from your mistakes</strong>
              <span>Each answer updates a mastery score per skill, so weak spots come back first.</span>
            </div>
          </li>
          <li>
            <IconTile icon={<CheckIcon size={20} />} tone="green" />
            <div>
              <strong>Feedback on every answer</strong>
              <span>A 0–100 score, the corrected sentence and the rule behind it.</span>
            </div>
          </li>
          <li>
            <IconTile icon={<SpeakingIcon size={20} />} tone="orange" />
            <div>
              <strong>Speak, not just type</strong>
              <span>Record answers, role-play conversations, or talk hands-free with AI Monkey.</span>
            </div>
          </li>
        </ul>
      </section>

      <form className="card auth-card" onSubmit={submit} noValidate>
        <Segmented
          label="Create an account or sign in"
          stretch
          value={mode}
          onChange={(m) => {
            setMode(m);
            setError(null);
          }}
          options={[
            { value: "register", label: "Create account" },
            { value: "login", label: "Sign in" },
          ]}
        />

        <h2>{register ? "Start learning for free" : "Welcome back"}</h2>
        <p className="small muted" style={{ marginBottom: 20 }}>
          {register ? "It takes less than a minute." : "Sign in to continue where you left off."}
        </p>

        {register && (
          <div className="field">
            <label htmlFor="name">Your name</label>
            <input id="name" type="text" required maxLength={80} autoComplete="given-name" value={name}
              onChange={(e) => setName(e.target.value)} placeholder="e.g. Lan" />
          </div>
        )}

        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="email" inputMode="email" value={email}
            onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>

        <div className="field">
          <label htmlFor="password">
            Password {register && <span className="hint">· at least 8 characters</span>}
          </label>
          <input id="password" type="password" required minLength={register ? 8 : 1}
            autoComplete={register ? "new-password" : "current-password"} value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </div>

        {register && (
          <div className="grid cols-2" style={{ gap: 12 }}>
            <div className="field">
              <label htmlFor="level">Your level now</label>
              <select id="level" value={level} onChange={(e) => setLevel(e.target.value as Cefr)}>
                {START_LEVELS.map((l) => (
                  <option key={l} value={l}>{l} · {levelName(l)}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="target">Your goal</label>
              <select id="target" value={target} onChange={(e) => setTarget(e.target.value as Cefr)}>
                {GOAL_LEVELS.map((l) => (
                  <option key={l} value={l}>{l} · {levelName(l)}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        <ErrorBox error={error} />

        <button className="btn accent large block mt-8" type="submit" disabled={busy || !canSubmit}>
          {busy ? <><Spinner /> {register ? "Creating your account…" : "Signing in…"}</> : <>{register ? "Create account" : "Sign in"} <ArrowRightIcon size={18} /></>}
        </button>

        <div className="demo-box">
          <span className="small muted">
            Just looking? <code>demo@banana.local</code> / <code>banana-demo</code>
          </span>
          <button type="button" className="btn small ghost" onClick={() => {
            setEmail("demo@banana.local");
            setPassword("banana-demo");
            setMode("login");
            setError(null);
          }}>
            Use demo account
          </button>
        </div>
      </form>
    </div>
  );
}
