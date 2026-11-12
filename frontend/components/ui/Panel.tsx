import type { ReactNode } from "react";
import type { Tone } from "@/lib/modules";

/** A card section with a heading row. `flush` removes the inner padding for edge-to-edge lists. */
export function Panel({
  title,
  description,
  actions,
  children,
  className = "",
  flush = false,
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
  id?: string;
}) {
  return (
    <section className={`card${flush ? " flush" : ""} ${className}`} aria-labelledby={id}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <h2 id={id}>{title}</h2>}
            {description && <p className="panel-desc">{description}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** A rounded square holding an icon, tinted with the module's colour. */
export function IconTile({
  icon,
  tone = "neutral",
  size = "md",
}: {
  icon: ReactNode;
  tone?: Tone;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <span className={`icon-tile tone-${tone} ${size}`} aria-hidden>
      {icon}
    </span>
  );
}

/** A key number: value, label and an optional hint or progress line under it. */
export function Stat({
  label,
  value,
  icon,
  tone = "neutral",
  children,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  children?: ReactNode;
}) {
  return (
    <div className="card stat">
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {icon && <IconTile icon={icon} tone={tone} size="sm" />}
      </div>
      <div className="stat-value">{value}</div>
      {children && <div className="stat-foot">{children}</div>}
    </div>
  );
}

/** An inline message box: tips, notices, pending work, success. */
export function Callout({
  tone = "info",
  icon,
  title,
  children,
  action,
  role,
}: {
  tone?: "info" | "good" | "warn" | "bad" | "accent" | "neutral";
  icon?: ReactNode;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  role?: "status" | "alert";
}) {
  return (
    <div className={`callout ${tone}`} role={role}>
      {icon && <span className="callout-icon" aria-hidden>{icon}</span>}
      <div className="callout-body">
        {title && <strong className="callout-title">{title}</strong>}
        {children && <div>{children}</div>}
      </div>
      {action && <div className="callout-action">{action}</div>}
    </div>
  );
}

/** A small activity indicator for buttons and pending states. */
export function Spinner({ size = 16, label }: { size?: number; label?: string }) {
  return (
    <span className="spinner" style={{ width: size, height: size }} role={label ? "status" : undefined}
      aria-label={label} aria-hidden={label ? undefined : true} />
  );
}
