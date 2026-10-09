export function FreshnessPill({
  source,
  latestDate,
  nRows,
}: {
  source: string;
  latestDate: string | null;
  nRows: number;
}) {
  const empty = nRows === 0;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
        empty ? "border-border text-muted" : "border-border text-foreground"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${empty ? "bg-muted" : "bg-accent"}`}
        aria-hidden
      />
      {source.replace(/_/g, " ")}
      <span className="text-muted">
        {empty ? "no data yet" : `${latestDate} · ${nRows.toLocaleString()} rows`}
      </span>
    </span>
  );
}
