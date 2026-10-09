"use client";

import { useId, useState } from "react";

export type BarCompareDatum = {
  label: string;
  value: number;
  lo?: number | null;
  hi?: number | null;
  color: string;
};

/**
 * Horizontal bar-with-interval comparison (SPEC §10 page 2: "4-method
 * comparison bar w/ intervals"). Direct-labeled (method names sit on
 * the axis, not in a legend box) since every bar is its own category;
 * an always-rendered table covers the no-color / screen-reader case.
 */
export function BarCompare({
  data,
  unit,
  height = 36,
}: {
  data: BarCompareDatum[];
  unit: string;
  height?: number;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const tableId = useId();

  const lo = Math.min(...data.map((d) => d.lo ?? d.value));
  const hi = Math.max(...data.map((d) => d.hi ?? d.value));
  const pad = (hi - lo) * 0.08 || 1;
  const xMin = lo - pad;
  const xMax = hi + pad;
  const toPct = (v: number) => ((v - xMin) / (xMax - xMin)) * 100;

  return (
    <div>
      <div role="group" aria-describedby={tableId} className="space-y-3">
        {data.map((d, i) => (
          <div
            key={d.label}
            className="group"
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx(null)}
          >
            <div className="flex items-baseline justify-between text-xs">
              <span className="font-medium text-foreground">{d.label}</span>
              <span className="font-mono text-muted">
                {d.value.toFixed(1)}
                {unit}
                {d.lo != null && d.hi != null && (
                  <>
                    {" "}
                    <span className="text-muted">
                      ({d.lo.toFixed(1)}–{d.hi.toFixed(1)})
                    </span>
                  </>
                )}
              </span>
            </div>
            <div
              className="relative mt-1 rounded"
              style={{ height, background: "var(--chart-grid)" }}
            >
              {d.lo != null && d.hi != null && (
                <div
                  className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full opacity-40"
                  style={{
                    left: `${toPct(d.lo)}%`,
                    width: `${toPct(d.hi) - toPct(d.lo)}%`,
                    background: d.color,
                  }}
                />
              )}
              <div
                className="absolute top-1/2 h-4 w-1 -translate-y-1/2 -translate-x-1/2 rounded-full transition-[width]"
                style={{
                  left: `${toPct(d.value)}%`,
                  background: d.color,
                  width: hoverIdx === i ? 6 : 4,
                }}
              />
              {hoverIdx === i && (
                <div
                  className="absolute -top-8 -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-surface px-2 py-1 text-xs shadow-lg"
                  style={{ left: `${toPct(d.value)}%` }}
                >
                  {d.value.toFixed(1)}
                  {unit}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <table id={tableId} className="sr-only">
        <caption>Method comparison, values in {unit}</caption>
        <thead>
          <tr>
            <th>Method</th>
            <th>Fair value</th>
            <th>Low 90%</th>
            <th>High 90%</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.label}>
              <td>{d.label}</td>
              <td>{d.value}</td>
              <td>{d.lo ?? "—"}</td>
              <td>{d.hi ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
