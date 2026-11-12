"use client";

/** AI Monkey state lives above the pages (in the root layout), so the chat history survives
 * leaving the screen, and a reply that arrives while the learner is elsewhere can light the
 * badge in the navigation bar.
 *
 * Talk mode (hands-free voice) is a TalkSession (lib/talk). It is ended, releasing the
 * microphone, audio graph, speech, timers and requests, by End Talk, by leaving /monkey, by
 * hiding or unloading the page, and by switching to text chat. It never restarts by itself. */

import { usePathname } from "next/navigation";
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import { api } from "@/lib/api";
import { useLearner } from "@/components/useLearner";
import { browserTalkDeps, replyVoice, talkSupport, ttsLog, type TalkSupport } from "@/lib/talk/browser";
import { TALK_ERRORS, TalkSession, type Latency, type TalkPhase } from "@/lib/talk/session";
import { speakChunks, spokenText, type SpeakHandle } from "@/lib/talk/tts";
import {
  chatBody, DEFAULT_PREFS, parsePrefs, prefsAfterReply, type ChatReply, type MonkeyPrefs,
} from "@/lib/monkeyPrefs";

export const MONKEY_PATH = "/monkey";
const MAX_RECORD_SECONDS = 30;
const MAX_STORED = 100;
const MAX_SENT = 40;

export type MonkeyMessage = {
  id: string; role: "learner" | "monkey"; text: string; latency?: Latency;
  /** Settings the learner's message changed ("Chat: English"), shown under the reply. */
  notice?: string;
};
export type MonkeyMode = "text" | "voice";
export type MicState = "idle" | "recording" | "transcribing";

interface MonkeyContextValue {
  enabled: boolean | null;
  messages: MonkeyMessage[];
  draft: string;
  setDraft: (text: string) => void;
  mode: MonkeyMode;
  setMode: (mode: MonkeyMode) => void;
  pending: boolean;
  speaking: boolean;
  unread: boolean;
  mic: MicState;
  seconds: number;
  error: string | null;
  canSpeak: boolean;
  /** Autoplay refused the reply: show "🔊 Bấm để nghe", which calls unblockAudio(). */
  audioBlocked: boolean;
  unblockAudio: () => void;
  talkPhase: TalkPhase;
  talkSupport: TalkSupport;
  startTalk: () => void;
  endTalk: () => void;
  send: (text: string) => Promise<void>;
  /** How AI Monkey teaches (languages, corrections); kept for the session, sent with each message. */
  prefs: MonkeyPrefs;
  setPrefs: (prefs: MonkeyPrefs) => void;
  startMic: () => Promise<void>;
  stopMic: () => void;
  speak: (text: string) => void;
  stopSpeaking: () => void;
  clear: () => void;
}

const MonkeyContext = createContext<MonkeyContextValue | null>(null);

export function useMonkey(): MonkeyContextValue {
  const value = useContext(MonkeyContext);
  if (!value) throw new Error("useMonkey must be used inside <MonkeyProvider>");
  return value;
}

const newId = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

function readStored(key: string): MonkeyMessage[] {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as MonkeyMessage[]) : [];
  } catch {
    return [];
  }
}


export function MonkeyProvider({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const onMonkey = path === MONKEY_PATH;
  const { profile } = useLearner({ redirect: false });
  const learnerId = profile?.learner_id ?? null;
  const storageKey = learnerId ? `banana-monkey:${learnerId}` : null;
  const prefsKey = learnerId ? `banana-monkey-prefs:${learnerId}` : null;

  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [messages, setMessagesState] = useState<MonkeyMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [mode, setModeState] = useState<MonkeyMode>("text");
  const [pending, setPending] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [unread, setUnread] = useState(false);
  const [mic, setMic] = useState<MicState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [canSpeak, setCanSpeak] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [talkPhase, setTalkPhase] = useState<TalkPhase>("off");
  const [support, setSupport] = useState<TalkSupport>("unsupported");
  const [prefs, setPrefsState] = useState<MonkeyPrefs>(DEFAULT_PREFS);

  const messagesRef = useRef(messages);
  const onMonkeyRef = useRef(onMonkey);
  const modeRef = useRef(mode);
  const recorder = useRef<MediaRecorder | null>(null);
  const discard = useRef(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const talk = useRef<TalkSession | null>(null);
  const lastReplyId = useRef<string | null>(null);
  const manualSpeech = useRef<SpeakHandle | null>(null);
  const prefsRef = useRef(prefs);
  const replyNotice = useRef<string | undefined>(undefined);
  onMonkeyRef.current = onMonkey;
  modeRef.current = mode;

  /** Update the history and its ref together, so async callbacks never read a stale list. */
  const setMessages = useCallback((update: (prev: MonkeyMessage[]) => MonkeyMessage[]) => {
    messagesRef.current = update(messagesRef.current);
    setMessagesState(messagesRef.current);
  }, []);

  useEffect(() => {
    api<{ ai_monkey: boolean }>("/features").then((f) => setEnabled(f.ai_monkey))
      .catch(() => setEnabled(false));
    setCanSpeak(typeof Audio !== "undefined"); // replies are spoken by the server voice
    setSupport(talkSupport());
  }, []);

  // One history per learner and browser tab; a different learner never sees it.
  useEffect(() => {
    talk.current?.end();
    messagesRef.current = storageKey ? readStored(storageKey) : [];
    setMessagesState(messagesRef.current);
    setUnread(false);
    setDraft("");
  }, [storageKey]);

  // Teaching preferences: one set per learner and browser tab, like the history.
  useEffect(() => {
    let stored: unknown = null;
    try {
      stored = prefsKey ? JSON.parse(window.sessionStorage.getItem(prefsKey) ?? "null") : null;
    } catch {
      stored = null;
    }
    prefsRef.current = parsePrefs(stored);
    setPrefsState(prefsRef.current);
  }, [prefsKey]);

  const setPrefs = useCallback((next: MonkeyPrefs) => {
    prefsRef.current = next;
    setPrefsState(next);
    if (!prefsKey) return;
    try {
      window.sessionStorage.setItem(prefsKey, JSON.stringify(next));
    } catch {
      // storage blocked: the preferences still apply until the page is closed
    }
  }, [prefsKey]);

  /** Ask for a reply with the current preferences; keep the ones a command in it changed. */
  const askMonkey = useCallback(async (signal?: AbortSignal): Promise<ChatReply> => {
    const r = await api<ChatReply>("/monkey/chat", {
      method: "POST", body: JSON.stringify(chatBody(messagesRef.current, prefsRef.current, MAX_SENT)), signal,
    });
    const next = prefsAfterReply(prefsRef.current, r);
    if (next !== prefsRef.current) setPrefs(next);
    replyNotice.current = r.changes?.length ? r.changes.join(" · ") : undefined;
    return r;
  }, [setPrefs]);

  useEffect(() => {
    if (!storageKey) return;
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify(messages.slice(-MAX_STORED)));
    } catch {
      // storage full or blocked: the in-memory history still works
    }
  }, [messages, storageKey]);

  // --- Talk mode (hands-free) ------------------------------------------------------------

  const getTalk = useCallback((): TalkSession => {
    if (talk.current) return talk.current;
    const deps = browserTalkDeps({
      async transcribe(audio, fileName, signal) {
        const form = new FormData();
        form.append("audio", audio, fileName);
        const r = await api<{ text: string }>("/monkey/transcribe", { method: "POST", body: form, signal });
        return r.text;
      },
      async reply(_text, signal) {
        return (await askMonkey(signal)).reply;
      },
    }, replyVoice());
    talk.current = new TalkSession(deps, {
      onPhase: setTalkPhase,
      onHeard: (text) => {
        setError(null);
        setMessages((prev) => [...prev, { id: newId(), role: "learner", text }]);
      },
      onReply: (text) => {
        const id = newId();
        lastReplyId.current = id;
        const notice = replyNotice.current;
        replyNotice.current = undefined;
        setMessages((prev) => [...prev, { id, role: "monkey", text, notice }]);
      },
      onLatency: (latency) => {
        const id = lastReplyId.current;
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, latency } : m)));
      },
      onError: setError,
      onAudioBlocked: setAudioBlocked,
    });
    return talk.current;
  }, [askMonkey, setMessages]);

  const endTalk = useCallback(() => {
    talk.current?.end();
  }, []);

  const startTalk = useCallback(() => {
    if (support !== "ok") return;
    // Synchronously, inside the click and before any await: unlock audio for later replies.
    replyVoice().unlock?.();
    manualSpeech.current?.cancel();
    setError(null);
    void getTalk().start();
  }, [getTalk, support]);

  const setMode = useCallback((next: MonkeyMode) => {
    setModeState(next);
    if (next === "text") endTalk();
    else startTalk(); // the Talk button is the user gesture that unlocks mic and audio
  }, [endTalk, startTalk]);

  // --- text chat and the manual microphone -----------------------------------------------

  const stopSpeaking = useCallback(() => {
    manualSpeech.current?.cancel();
    manualSpeech.current = null;
    setSpeaking(false);
  }, []);

  /** Read one reply aloud outside Talk mode (🔊 buttons, tap-to-talk mode). */
  const speak = useCallback((text: string) => {
    if (!onMonkeyRef.current || talk.current?.active) return;
    const voice = replyVoice();
    voice.unlock?.(); // usually called from a click: keeps autoplay open
    manualSpeech.current?.cancel();
    const spoken = spokenText(text);
    if (!spoken) return; // Vietnamese only: shown, not spoken (the voice is English)
    const handle = speakChunks(voice, spoken, {
      onStart: () => setSpeaking(true),
      onBlocked: setAudioBlocked,
      log: ttsLog,
    });
    manualSpeech.current = handle;
    void handle.done.then((outcome) => {
      if (manualSpeech.current !== handle) return;
      manualSpeech.current = null;
      setSpeaking(false);
      if (outcome === "failed") setError(TALK_ERRORS.audio);
    });
  }, []);

  const unblockAudio = useCallback(() => {
    replyVoice().unblock?.(); // from the button's click: play what autoplay refused
  }, []);

  const send = useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || pending || talk.current?.active) return;
    setMessages((prev) => [...prev, { id: newId(), role: "learner", text }]);
    setPending(true);
    setError(null);
    try {
      const r = await askMonkey();
      const notice = replyNotice.current;
      replyNotice.current = undefined;
      setMessages((prev) => [...prev, { id: newId(), role: "monkey", text: r.reply, notice }]);
      if (!onMonkeyRef.current) setUnread(true);
      else if (modeRef.current === "voice") speak(r.reply);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }, [askMonkey, pending, setMessages, speak]);

  const stopTimer = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };

  const stopMic = useCallback(() => {
    stopTimer();
    if (recorder.current?.state === "recording") recorder.current.stop();
  }, []);

  const cancelMic = useCallback(() => {
    discard.current = true;
    stopMic();
  }, [stopMic]);

  const transcribe = useCallback(async (audio: Blob) => {
    setMic("transcribing");
    try {
      const form = new FormData();
      form.append("audio", audio, audio.type.includes("ogg") ? "voice.ogg"
        : audio.type.includes("mp4") ? "voice.m4a" : "voice.webm");
      const r = await api<{ text: string }>("/monkey/transcribe", { method: "POST", body: form });
      const heard = r.text.trim();
      if (!heard) {
        setError("I didn't catch that. Please try again, a little louder.");
      } else if (modeRef.current === "voice") {
        setMic("idle");
        await send(heard);
        return;
      } else {
        setDraft((d) => (d ? `${d} ${heard}` : heard));
      }
    } catch (e) {
      setError((e as Error).message);
    }
    setMic("idle");
  }, [send]);

  const startMic = useCallback(async () => {
    if (mic !== "idle" || pending || talk.current?.active) return;
    setError(null);
    stopSpeaking(); // the monkey must not hear itself
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(stream);
      discard.current = false;
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        recorder.current = null;
        if (discard.current || !chunks.length) {
          setMic("idle");
          return;
        }
        transcribe(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
      };
      recorder.current = rec;
      rec.start();
      setSeconds(0);
      setMic("recording");
      timer.current = setInterval(() => {
        setSeconds((s) => {
          if (s + 1 >= MAX_RECORD_SECONDS) stopMic();
          return s + 1;
        });
      }, 1000);
    } catch {
      setError("The microphone is not available. Allow microphone access in your browser.");
      setMic("idle");
    }
  }, [mic, pending, stopMic, stopSpeaking, transcribe]);

  // --- cleanup -------------------------------------------------------------------------------

  // Leaving the screen turns the microphone and speech off; coming back clears the badge.
  useEffect(() => {
    if (onMonkey) {
      setUnread(false);
    } else {
      endTalk();
      cancelMic();
      stopSpeaking();
    }
  }, [onMonkey, cancelMic, endTalk, stopSpeaking]);

  // A hidden tab or an unloading page must not keep the microphone open.
  useEffect(() => {
    const stopAll = () => {
      endTalk();
      cancelMic();
      stopSpeaking();
    };
    // Debounced: a moment of "hidden" (a permission prompt on some phones) must not cut the
    // monkey off mid-sentence; a tab that stays hidden for 0.5 s is really gone.
    let hiddenTimer: number | undefined;
    const onVisibility = () => {
      window.clearTimeout(hiddenTimer);
      if (document.visibilityState !== "hidden") return;
      hiddenTimer = window.setTimeout(() => {
        if (document.visibilityState === "hidden") stopAll();
      }, 500);
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", stopAll);
    return () => {
      window.clearTimeout(hiddenTimer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", stopAll);
      stopAll();
      stopTimer();
    };
  }, [cancelMic, endTalk, stopSpeaking]);

  const clear = useCallback(() => {
    stopSpeaking();
    setMessages(() => []);
    setError(null);
  }, [setMessages, stopSpeaking]);

  const value = useMemo<MonkeyContextValue>(() => ({
    enabled, messages, draft, setDraft, mode, setMode, pending, speaking, unread, mic, seconds,
    error, canSpeak, audioBlocked, unblockAudio, talkPhase, talkSupport: support, startTalk,
    endTalk, send, startMic, stopMic, speak, stopSpeaking, clear, prefs, setPrefs,
  }), [enabled, messages, draft, setMode, mode, pending, speaking, unread, mic, seconds, error,
    canSpeak, audioBlocked, unblockAudio, talkPhase, support, startTalk, endTalk, send,
    startMic, stopMic, speak, stopSpeaking, clear, prefs, setPrefs]);

  return <MonkeyContext.Provider value={value}>{children}</MonkeyContext.Provider>;
}
