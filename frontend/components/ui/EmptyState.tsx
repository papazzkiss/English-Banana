import Link from "next/link";
import type { ReactNode } from "react";
import { SparklesIcon } from "./Icons";

/** Shown when a list has nothing in it: what happened, and the one thing to do next. */
export function EmptyState({
  icon = <SparklesIcon size={28} />,
  title,
  description,
  actionText,
  actionHref,
  onAction,
  secondary,
  compact = false,
}: {
  icon?: ReactNode;
  title: string;
  description: ReactNode;
  actionText?: string;
  actionHref?: string;
  onAction?: () => void;
  secondary?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`empty${compact ? " compact" : " card"}`}>
      <span className="empty-icon" aria-hidden>{icon}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {(actionText || secondary) && (
        <div className="btn-row center">
          {actionText && actionHref && (
            <Link href={actionHref} className="btn accent">
              {actionText}
            </Link>
          )}
          {actionText && !actionHref && onAction && (
            <button type="button" className="btn accent" onClick={onAction}>
              {actionText}
            </button>
          )}
          {secondary}
        </div>
      )}
    </div>
  );
}
