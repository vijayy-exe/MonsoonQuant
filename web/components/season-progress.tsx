export function SeasonProgress({
  periodStart,
  periodEnd,
}: {
  periodStart: string | null;
  periodEnd: string | null;
}) {
  if (!periodStart || !periodEnd) {
    return <p className="text-xs text-muted">season dates not resolved</p>;
  }
  const start = new Date(periodStart).getTime();
  const end = new Date(periodEnd).getTime();
  const now = Date.now();
  const pct = Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100));
  const closed = now > end;

  return (
    <div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-muted">
        {closed
          ? `season closed ${periodEnd}`
          : `${periodStart} → ${periodEnd} · ${pct.toFixed(0)}% elapsed`}
      </p>
    </div>
  );
}
