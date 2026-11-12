/**
 * Read a word or sentence aloud with the same voice as AI Monkey: the server voice (Piper),
 * falling back to the browser's speechSynthesis. Browsers without system voices (Brave or
 * Chromium on Linux) cannot pronounce anything with speechSynthesis alone.
 * Call it from a click or key press, so the browser allows the audio to play.
 */
import { replyVoice } from "@/lib/talk/browser";
import { speakChunks, type SpeakHandle } from "@/lib/talk/tts";

let current: SpeakHandle | null = null;

export function speakWord(text: string): boolean {
  if (typeof window === "undefined" || !text.trim()) return false;
  const voice = replyVoice();
  voice.unlock?.();
  current?.cancel();
  current = speakChunks(voice, text);
  return true;
}
