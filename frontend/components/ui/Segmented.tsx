"use client";

import type { ReactNode } from "react";

/** A row of toggle buttons where exactly one is on: view switches, filters, speeds.
 * Each option is a real button with aria-pressed, so it works with keyboard and screen readers. */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  size = "md",
  stretch = false,
}: {
  label: string;
  options: { value: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
  stretch?: boolean;
}) {
  return (
    <div className={`segmented ${size}${stretch ? " stretch" : ""}`} role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count !== undefined && <span className="seg-count">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
