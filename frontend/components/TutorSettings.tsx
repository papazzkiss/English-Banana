"use client";

import { useId, useState } from "react";
import { GlobeIcon } from "@/components/ui/Icons";
import {
  CORRECTION_LABELS, LANGUAGE_LABELS, MODE_HINTS, MODE_LABELS, QUICK_ACTIONS, summary,
  withMode, withSetting, type CorrectionLevel, type LanguageChoice, type MonkeyPrefs,
  type TeachingMode,
} from "@/lib/monkeyPrefs";

/** AI Monkey's teaching languages: one summary line with quick actions, and the full settings
 * behind a "Settings" button. Changes apply to the next message, without a reload. */
export function TutorSettings({ prefs, onChange }: { prefs: MonkeyPrefs; onChange: (p: MonkeyPrefs) => void }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const panel = `${id}-panel`;

  const languageSelect = (
    key: "conversation_language" | "explanation_language" | "correction_language",
    label: string,
  ) => (
    <div className="tutor-field">
      <label htmlFor={`${id}-${key}`}>{label}</label>
      <select
        id={`${id}-${key}`}
        value={prefs[key]}
        onChange={(e) => onChange(withSetting(prefs, key, e.target.value as LanguageChoice))}
      >
        {(Object.keys(LANGUAGE_LABELS) as LanguageChoice[]).map((l) => (
          <option key={l} value={l}>{LANGUAGE_LABELS[l]}</option>
        ))}
      </select>
    </div>
  );

  return (
    <section className="card tutor-settings" aria-label="Tutor language settings">
      <div className="tutor-bar">
        <span className="tutor-title">
          <GlobeIcon size={16} /> Tutor language
        </span>
        <span className="tutor-summary" aria-live="polite">{summary(prefs)}</span>
        <button
          type="button"
          className="btn small ghost tutor-toggle"
          aria-expanded={open}
          aria-controls={panel}
          onClick={() => setOpen((o) => !o)}
        >
          Settings <span aria-hidden>{open ? "▴" : "▾"}</span>
        </button>
      </div>

      <div className="chip-row tutor-quick" role="group" aria-label="Quick language actions">
        {QUICK_ACTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            className="chip"
            aria-pressed={a.active(prefs)}
            onClick={() => onChange(a.apply(prefs))}
          >
            {a.label}
          </button>
        ))}
      </div>

      {open && (
        <div id={panel} className="tutor-panel">
          <div className="tutor-grid">
            <div className="tutor-field">
              <label htmlFor={`${id}-mode`}>Mode</label>
              <select
                id={`${id}-mode`}
                value={prefs.mode}
                onChange={(e) => onChange(withMode(prefs, e.target.value as TeachingMode))}
              >
                {(Object.keys(MODE_LABELS) as TeachingMode[]).map((m) => (
                  <option key={m} value={m} disabled={m === "custom" && prefs.mode !== "custom"}>
                    {MODE_LABELS[m]}
                  </option>
                ))}
              </select>
            </div>
            {languageSelect("conversation_language", "Language")}
            {languageSelect("explanation_language", "Explanation")}
            {languageSelect("correction_language", "Correction")}
            <div className="tutor-field">
              <label htmlFor={`${id}-corrections`}>Corrections</label>
              <select
                id={`${id}-corrections`}
                value={prefs.corrections}
                onChange={(e) => onChange(withSetting(prefs, "corrections", e.target.value as CorrectionLevel))}
              >
                {(Object.keys(CORRECTION_LABELS) as CorrectionLevel[]).map((c) => (
                  <option key={c} value={c}>{CORRECTION_LABELS[c]}</option>
                ))}
              </select>
            </div>
          </div>
          <p className="small muted tutor-note">
            <strong>{MODE_LABELS[prefs.mode]}:</strong> {MODE_HINTS[prefs.mode]} You can also just
            tell Monkey, e.g. “Từ giờ giải thích bằng tiếng Việt” or “Don’t correct me”. Vietnamese
            is shown as text: the voice speaks English, and voice input understands English.
          </p>
        </div>
      )}
    </section>
  );
}
