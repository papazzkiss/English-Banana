import type { Tone } from "@/lib/modules";

/** A horizontal 0–100 bar. `label` names it for screen readers (and shows it above the bar
 * together with the value when `showValue` is set). */
export function ProgressBar({
  value,
  label,
  showValue = false,
  tone = "accent",
  size = "md",
  valueText,
}: {
  value: number;
  label: string;
  showValue?: boolean;
  tone?: Tone | "good" | "bad";
  size?: "sm" | "md";
  /** Replaces the "NN%" shown on the right. */
  valueText?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="progress-wrap">
      {showValue && (
        <div className="progress-label">
          <span>{label}</span>
          <span className="num">{valueText ?? `${clamped}%`}</span>
        </div>
      )}
      <div
        className={`progress ${size} tone-${tone}`}
        role="progressbar"
        aria-label={label}
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={valueText}
      >
        <span style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}
