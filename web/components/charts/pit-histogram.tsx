export function PitHistogram({
  binEdges,
  counts,
}: {
  binEdges: number[];
  counts: number[];
}) {
  const max = Math.max(...counts, 1);
  const width = 240;
  const height = 72;
  const barW = width / counts.length;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
        <line x1={0} x2={width} y1={height} y2={height} stroke="var(--chart-axis)" strokeWidth={1} />
        {/* Uniform PIT (well-calibrated) reference line */}
        <line
          x1={0}
          x2={width}
          y1={height - (counts.reduce((a, b) => a + b, 0) / counts.length / max) * height}
          y2={height - (counts.reduce((a, b) => a + b, 0) / counts.length / max) * height}
          stroke="var(--chart-grid)"
          strokeDasharray="3 3"
        />
        {counts.map((c, i) => {
          const h = (c / max) * height;
          return (
            <rect
              key={i}
              x={i * barW + 1}
              y={height - h}
              width={barW - 2}
              height={h}
              fill="var(--chart-1)"
            />
          );
        })}
      </svg>
      <p className="mt-1 text-xs text-muted">
        PIT histogram, {binEdges.length - 1} bins over [0,1] — flat means
        well-calibrated.
      </p>
    </div>
  );
}
