import Link from "next/link";
import type { ReactNode } from "react";
import { ChevronLeftIcon } from "./Icons";

/** The top of every screen: optional back link, eyebrow, title, one-line description,
 * meta chips under the title and actions on the right (stacked below on phones). */
export function PageHeader({
  title,
  description,
  eyebrow,
  back,
  meta,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  back?: { href: string; label: string } | { onClick: () => void; label: string };
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      {back &&
        ("href" in back ? (
          <Link href={back.href} className="back-link">
            <ChevronLeftIcon size={16} />
            {back.label}
          </Link>
        ) : (
          <button type="button" className="back-link" onClick={back.onClick}>
            <ChevronLeftIcon size={16} />
            {back.label}
          </button>
        ))}
      <div className="page-head-row">
        <div className="page-head-text">
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h1>{title}</h1>
          {description && <p className="page-desc">{description}</p>}
          {meta && <div className="chip-row page-meta">{meta}</div>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
    </header>
  );
}
