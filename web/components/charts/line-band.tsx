"use client";

import { useId, useMemo, useRef, useState } from "react";

export type LineBandPoint = {
  x: number;
  y: number | null;
  lo?: number | null;
  hi?: number | null;
  label: string;
};

/**
 * Line chart with an optional uncertainty band -- reused for the
 * Forecast fan chart and the Risk page's λ-with-CI-ribbon (SPEC §10,
 * pages 3 & 4). One series; a second "observed" line can be overlaid
 * via `secondary`. Hover shows a crosshair + tooltip (dataviz skill:
 * "ship by default" for line/area forms).
 */
export function LineBand({
  points,
  secondary,
  unit,
  seriesColor = "var(--chart-1)",
  secondaryColor = "var(--chart-2)",
  height = 220,
}: {
  points: LineBandPoint[];
  secondary?: { label: string; points: LineBandPoint[] };
  unit: string;
  seriesColor?: string;
  secondaryColor?: string;
  height?: number;
}) {
  const [hoverX, setHoverX] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const gradientId = useId();

  const width = 640;
  const padL = 44;
  const padB = 24;
  const padT = 10;
  const padR = 10;

  const valid = points.filter((p) => p.y != null);
  const allY = [
    ...valid.map((p) => p.y as number),
    ...valid.map((p) => p.lo ?? (p.y as number)),
    ...valid.map((p) => p.hi ?? (p.y as number)),
    ...(secondary?.points.filter((p) => p.y != null).map((p) => p.y as number) ?? []),
  ];
  const yMin = Math.min(...allY);
  const yMax = Math.max(...allY);
  const yPad = (yMax - yMin) * 0.1 || 1;
  const y0 = yMin - yPad;
  const y1 = yMax + yPad;

  const xs = points.map((p) => p.x);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);

  const toX = (x: number) =>
    padL + ((x - xMin) / (xMax - xMin || 1)) * (width - padL - padR);
  const toY = (y: number) =>
    padT + (1 - (y - y0) / (y1 - y0 || 1)) * (height - padT - padB);

  const path = (pts: LineBandPoint[], key: "y" | "lo" | "hi") =>
    pts
      .filter((p) => p[key] != null)
      .map((p, i) => `${i === 0 ? "M" : "L"}${toX(p.x)},${toY(p[key] as number)}`)
      .join(" ");

  const bandPath = useMemo(() => {
    const withBand = points.filter((p) => p.lo != null && p.hi != null);
    if (withBand.length < 2) return "";
    const top = withBand.map((p) => `${toX(p.x)},${toY(p.hi as number)}`).join(" L");
    const bottom = withBand
      .slice()
      .reverse()
      .map((p) => `${toX(p.x)},${toY(p.lo as number)}`)
      .join(" L");
    return `M${top} L${bottom} Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toX/toY are stable per render
  }, [points]);

  const nearest = useMemo(() => {
    if (hoverX == null) return null;
    let best = points[0];
    let bestDist = Infinity;
    for (const p of points) {
      const d = Math.abs(toX(p.x) - hoverX);
      if (d < bestDist) {
        bestDist = d;
        best = p;
      }
    }
    return best;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoverX, points]);

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={`Line chart in ${unit}`}
        onMouseMove={(e) => {
          const rect = svgRef.current?.getBoundingClientRect();
          if (!rect) return;
          const px = ((e.clientX - rect.left) / rect.width) * width;
          setHoverX(px);
        }}
        onMouseLeave={() => setHoverX(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={seriesColor} stopOpacity={0.18} />
            <stop offset="100%" stopColor={seriesColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={t}
            x1={padL}
            x2={width - padR}
            y1={padT + t * (height - padT - padB)}
            y2={padT + t * (height - padT - padB)}
            stroke="var(--chart-grid)"
            strokeWidth={1}
          />
        ))}

        {bandPath && <path d={bandPath} fill={`url(#${gradientId})`} />}
        <path d={path(points, "y")} fill="none" stroke={seriesColor} strokeWidth={2} />
        {secondary && (
          <path
            d={path(secondary.points, "y")}
            fill="none"
            stroke={secondaryColor}
            strokeWidth={2}
            strokeDasharray="4 3"
          />
        )}

        {nearest && (
          <line
            x1={toX(nearest.x)}
            x2={toX(nearest.x)}
            y1={padT}
            y2={height - padB}
            stroke="var(--chart-axis)"
            strokeWidth={1}
            strokeDasharray="2 2"
          />
        )}
      </svg>

      {secondary && (
        <div className="mt-1 flex gap-4 text-xs text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-3"
              style={{ background: seriesColor }}
            />
            series
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-3 border-t-2 border-dashed"
              style={{ borderColor: secondaryColor }}
            />
            {secondary.label}
          </span>
        </div>
      )}

      {nearest && (
        <div className="pointer-events-none absolute left-0 top-0 rounded-md border border-border bg-surface px-2 py-1 text-xs shadow-lg">
          <div className="font-medium text-foreground">{nearest.label}</div>
          {nearest.y != null && (
            <div className="font-mono text-muted">
              {nearest.y.toFixed(1)}
              {unit}
              {nearest.lo != null && nearest.hi != null && (
                <> ({nearest.lo.toFixed(1)}–{nearest.hi.toFixed(1)})</>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
