/** AI Monkey's teaching preferences (bilingual English-Vietnamese tutor).
 *
 * The server decides each reply's languages (banana_english/application/services/
 * language_policy.py); the client only keeps the preferences between turns, like the chat
 * history, and sends them with every message. Natural commands ("từ giờ chỉ nói tiếng Anh")
 * come back as updated preferences in the reply. */

export type LanguageChoice = "auto" | "en" | "vi";
export type CorrectionLevel = "auto" | "off" | "strict";
export type TeachingMode =
  | "auto" | "immersion" | "vietnamese_support" | "bilingual" | "free_chat" | "custom";

export interface MonkeyPrefs {
  mode: TeachingMode;
  conversation_language: LanguageChoice;
  explanation_language: LanguageChoice;
  correction_language: LanguageChoice;
  corrections: CorrectionLevel;
}

export const DEFAULT_PREFS: MonkeyPrefs = {
  mode: "auto",
  conversation_language: "auto",
  explanation_language: "auto",
  correction_language: "auto",
  corrections: "auto",
};

type Languages = Pick<MonkeyPrefs, "conversation_language" | "correction_language" | "explanation_language">;

/** Teaching modes: presets of the three languages (the same table as the server). */
export const MODE_PRESETS: Record<Exclude<TeachingMode, "custom">, Languages> = {
  auto: { conversation_language: "auto", correction_language: "auto", explanation_language: "auto" },
  immersion: { conversation_language: "en", correction_language: "en", explanation_language: "en" },
  vietnamese_support: { conversation_language: "en", correction_language: "vi", explanation_language: "vi" },
  bilingual: { conversation_language: "en", correction_language: "en", explanation_language: "vi" },
  free_chat: { conversation_language: "auto", correction_language: "auto", explanation_language: "auto" },
};

export const MODE_LABELS: Record<TeachingMode, string> = {
  auto: "Auto",
  immersion: "English Immersion",
  vietnamese_support: "Vietnamese Support",
  bilingual: "Bilingual",
  free_chat: "Free Chat",
  custom: "Custom",
};

export const MODE_HINTS: Record<TeachingMode, string> = {
  auto: "Chats in English; explains in the language you ask in.",
  immersion: "Everything in English.",
  vietnamese_support: "Chats in English; corrects and explains in Vietnamese.",
  bilingual: "Chats and corrects in English; explains in Vietnamese.",
  free_chat: "Talks in whatever language you use.",
  custom: "Your own combination below.",
};

export const LANGUAGE_LABELS: Record<LanguageChoice, string> = {
  auto: "Auto",
  en: "English",
  vi: "Tiếng Việt",
};

export const CORRECTION_LABELS: Record<CorrectionLevel, string> = {
  auto: "Gentle (auto)",
  off: "Off",
  strict: "All mistakes",
};

/** Switch to a teaching mode (its preset languages); the correction level is kept. */
export function withMode(prefs: MonkeyPrefs, mode: TeachingMode): MonkeyPrefs {
  if (mode === "custom") return { ...prefs, mode };
  return { ...prefs, ...MODE_PRESETS[mode], mode };
}

/** Change one setting; the mode becomes the preset it now matches, or "custom". */
export function withSetting<K extends keyof Omit<MonkeyPrefs, "mode">>(
  prefs: MonkeyPrefs, key: K, value: MonkeyPrefs[K],
): MonkeyPrefs {
  return normalize({ ...prefs, [key]: value });
}

export function normalize(prefs: MonkeyPrefs): MonkeyPrefs {
  const same = (l: Languages) =>
    l.conversation_language === prefs.conversation_language &&
    l.correction_language === prefs.correction_language &&
    l.explanation_language === prefs.explanation_language;
  if (prefs.mode !== "custom" && same(MODE_PRESETS[prefs.mode])) return prefs;
  const match = (Object.keys(MODE_PRESETS) as (keyof typeof MODE_PRESETS)[])
    .find((m) => same(MODE_PRESETS[m]));
  return { ...prefs, mode: match ?? "custom" };
}

export interface QuickAction {
  id: string;
  label: string;
  apply: (prefs: MonkeyPrefs) => MonkeyPrefs;
  active: (prefs: MonkeyPrefs) => boolean;
}

export const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "explain-vi",
    label: "Explain in Vietnamese",
    apply: (p) => normalize({ ...p, explanation_language: "vi", correction_language: "vi" }),
    active: (p) => p.explanation_language === "vi" && p.correction_language === "vi",
  },
  {
    id: "explain-en",
    label: "Explain in English",
    apply: (p) => normalize({ ...p, explanation_language: "en", correction_language: "en" }),
    active: (p) => p.explanation_language === "en" && p.correction_language === "en" && p.mode !== "immersion",
  },
  {
    id: "english-only",
    label: "English only",
    apply: (p) => withMode(p, "immersion"),
    active: (p) => p.mode === "immersion",
  },
  {
    id: "auto",
    label: "Auto",
    apply: () => ({ ...DEFAULT_PREFS }),
    active: (p) => p.mode === "auto" && p.corrections === "auto",
  },
];

/** One line for the collapsed settings bar. */
export function summary(prefs: MonkeyPrefs): string {
  const parts = [MODE_LABELS[prefs.mode]];
  if (prefs.mode === "custom") {
    parts.push(
      `chat ${LANGUAGE_LABELS[prefs.conversation_language]}`,
      `explain ${LANGUAGE_LABELS[prefs.explanation_language]}`,
    );
  }
  if (prefs.corrections !== "auto") parts.push(`corrections ${CORRECTION_LABELS[prefs.corrections]}`);
  return parts.join(" · ");
}

const isChoice = (v: unknown): v is LanguageChoice => v === "auto" || v === "en" || v === "vi";

/** Stored or server-sent preferences, with anything unknown replaced by the default. */
export function parsePrefs(value: unknown): MonkeyPrefs {
  const v = (value ?? {}) as Partial<Record<keyof MonkeyPrefs, unknown>>;
  const mode = typeof v.mode === "string" && v.mode in MODE_LABELS ? (v.mode as TeachingMode) : "auto";
  const corrections = v.corrections === "off" || v.corrections === "strict" ? v.corrections : "auto";
  return normalize({
    mode,
    conversation_language: isChoice(v.conversation_language) ? v.conversation_language : "auto",
    explanation_language: isChoice(v.explanation_language) ? v.explanation_language : "auto",
    correction_language: isChoice(v.correction_language) ? v.correction_language : "auto",
    corrections,
  });
}

export interface ChatTurn { role: "learner" | "monkey"; text: string }

/** The /monkey/chat body, the same for typed, tap-to-talk and hands-free messages. */
export function chatBody(history: ChatTurn[], prefs: MonkeyPrefs, maxSent = 40) {
  return {
    messages: history.slice(-maxSent).map(({ role, text }) => ({ role, text })),
    preferences: prefs,
  };
}

export interface ChatReply {
  reply: string;
  preferences?: unknown;
  changes?: string[];
}

/** Preferences after a reply: the server's only when the message changed them, so a setting
 * picked while the reply was on its way is not overwritten. */
export function prefsAfterReply(current: MonkeyPrefs, r: ChatReply): MonkeyPrefs {
  return r.changes?.length ? parsePrefs(r.preferences) : current;
}
