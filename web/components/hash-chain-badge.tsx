/** Status colour used with an icon + label, never hue alone (dataviz skill). */
export function HashChainBadge({ valid, nRows }: { valid: boolean; nRows: number }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
      style={{
        borderColor: valid ? "var(--chart-good)" : "var(--chart-critical)",
        color: valid ? "var(--chart-good)" : "var(--chart-critical)",
      }}
    >
      <span aria-hidden>{valid ? "✓" : "✕"}</span>
      {valid ? "chain verified" : "chain broken"} · {nRows} rows
    </span>
  );
}
