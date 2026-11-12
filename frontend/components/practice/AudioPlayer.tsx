"use client";

import { useRef, useState } from "react";
import { PauseIcon, PlayIcon, RotateCcwIcon } from "@/components/ui/Icons";
import { Segmented } from "@/components/ui/Segmented";

const SPEEDS = [0.75, 1, 1.25];

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** A lesson's audio: play/pause, back 5 s, seek, speed. Space toggles playback while the
 * player has focus. */
export function AudioPlayer({ src, fallbackDuration }: { src: string; fallbackDuration: number }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(fallbackDuration);
  const [speed, setSpeed] = useState(1);
  const [plays, setPlays] = useState(0);

  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) a.play().catch(() => undefined);
    else a.pause();
  };

  return (
    <div
      className="player"
      onKeyDown={(e) => {
        if (e.code === "Space" && (e.target as HTMLElement).tagName !== "BUTTON") {
          e.preventDefault();
          toggle();
        }
      }}
    >
      <audio
        ref={audio}
        src={src}
        preload="metadata"
        onPlay={() => {
          setPlaying(true);
          setPlays((n) => n + (time < 0.5 ? 1 : 0));
        }}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || fallbackDuration)}
      />
      <div className="player-row">
        <button type="button" className="btn play-btn" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <PauseIcon size={20} /> : <PlayIcon size={20} style={{ marginLeft: 2 }} />}
        </button>
        <button
          type="button"
          className="btn icon ghost"
          onClick={() => audio.current && (audio.current.currentTime = Math.max(0, audio.current.currentTime - 5))}
          aria-label="Back 5 seconds"
          title="Back 5 seconds"
        >
          <RotateCcwIcon size={18} />
        </button>
        <input
          type="range"
          className="scrubber"
          min={0}
          max={duration || 1}
          step={0.1}
          value={time}
          aria-label="Position"
          aria-valuetext={`${clock(time)} of ${clock(duration)}`}
          onChange={(e) => {
            const t = Number(e.target.value);
            setTime(t);
            if (audio.current) audio.current.currentTime = t;
          }}
        />
        <span className="time">
          {clock(time)} / {clock(duration)}
        </span>
        <Segmented
          label="Playback speed"
          size="sm"
          value={speed}
          onChange={(v) => {
            setSpeed(v);
            if (audio.current) audio.current.playbackRate = v;
          }}
          options={SPEEDS.map((s) => ({ value: s, label: `${s}×` }))}
        />
      </div>
      {plays > 1 && <p className="xsmall muted" style={{ margin: "8px 0 0" }}>Played {plays} times</p>}
    </div>
  );
}
