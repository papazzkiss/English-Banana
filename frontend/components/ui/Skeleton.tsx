/** Grey placeholders shaped like the content that is loading. */
export function Skeleton({
  width = "100%",
  height = 16,
  radius,
}: {
  width?: string | number;
  height?: string | number;
  radius?: string | number;
}) {
  return <span className="skeleton" style={{ width, height, borderRadius: radius }} aria-hidden />;
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card skeleton-card" aria-hidden>
      <div className="row-between">
        <Skeleton width="50%" height={22} />
        <Skeleton width={56} height={22} radius={99} />
      </div>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={`${92 - i * 14}%`} />
      ))}
    </div>
  );
}

export function SkeletonGrid({ count = 4, columns = 2 }: { count?: number; columns?: 2 | 3 | 4 }) {
  return (
    <div className={`grid cols-${columns}`} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

/** A full-width loading block for detail screens (instead of an empty page). */
export function LoadingScreen({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-screen" aria-busy="true">
      <span className="sr-only" role="status">{label}</span>
      <Skeleton width={120} height={14} />
      <Skeleton width="60%" height={34} />
      <Skeleton width="40%" height={16} />
      <SkeletonCard lines={4} />
    </div>
  );
}
