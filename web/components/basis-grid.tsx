"use client";

import { useState } from "react";
import type { BasisFeature } from "@/lib/api/queries";

const METRICS = [
  { key: "correlation" as const, label: "correlation", fmt: (v: number) => v.toFixed(2) },
  {
    key: "hedge_effectiveness" as const,
    label: "hedge effectiveness",
    fmt: (v: number) => `${(v * 100).toFixed(0)}%`,
  },
  {
    key: "tail_dependence_upper" as const,
    label: "tail dependence (upper)",
    fmt: (v: number) => v.toFixed(2),
  },
];

/**
 * SPEC §10 page 6 is "MapLibre grid heatmap" with a real basemap; this
 * is a deliberately simpler lon/lat scatter over the same real per-cell
 * stats (no basemap tile source wired up yet -- noted in docs/STATUS.md,
 * not silently substituted). Sequential blue ramp, one hue, light->dark
 * per the dataviz skill's magnitude rule.
 */
export function BasisGrid({ features }: { features: BasisFeature[] }) {
  const [metricIdx, setMetricIdx] = useState(0);
  const [selected, setSelected] = useState<BasisFeature | null>(null);
  const metric = METRICS[metricIdx];

  const lons = features.map((f) => f.geometry.coordinates[0]);
  const lats = features.map((f) => f.geometry.coordinates[1]);
  const lonMin = Math.min(...lons);
  const lonMax = Math.max(...lons);
  const latMin = Math.min(...lats);
  const latMax = Math.max(...lats);
  const width = 480;
  const height = 320;
  const pad = 30;

  const toX = (lon: number) =>
    pad + ((lon - lonMin) / (lonMax - lonMin || 1)) * (width - 2 * pad);
  const toY = (lat: number) =>
    height - pad - ((lat - latMin) / (latMax - latMin || 1)) * (height - 2 * pad);

  const values = features.map((f) => f.properties[metric.key]);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);
  const colorFor = (v: number) => {
    const t = (v - vMin) / (vMax - vMin || 1);
    const stops = ["#cde2fb", "#3987e5", "#0d366b"];
    const idx = t < 0.5 ? 0 : t < 1 ? 1 : 2;
    return stops[Math.min(idx, 2)];
  };

  return (
    <div>
      <div className="flex gap-2">
        {METRICS.map((m, i) => (
          <button
            key={m.key}
            type="button"
            onClick={() => setMetricIdx(i)}
            className={`rounded-full border px-3 py-1 text-xs ${
              i === metricIdx
                ? "border-accent bg-accent text-accent-foreground"
                : "border-border text-muted hover:text-foreground"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="mt-4 w-full rounded-lg border border-border bg-surface">
        {features.map((f, i) => {
          const [lon, lat] = f.geometry.coordinates;
          return (
            <circle
              key={i}
              cx={toX(lon)}
              cy={toY(lat)}
              r={10}
              fill={colorFor(f.properties[metric.key])}
              stroke={selected === f ? "var(--foreground)" : "var(--chart-grid)"}
              strokeWidth={selected === f ? 2 : 1}
              className="cursor-pointer"
              onClick={() => setSelected(f)}
            />
          );
        })}
      </svg>

      <div className="mt-2 flex items-center gap-2 text-xs text-muted">
        <span>{metric.label}:</span>
        <span className="inline-flex h-3 w-16 rounded-full" style={{ background: "linear-gradient(90deg,#cde2fb,#3987e5,#0d366b)" }} />
        <span>
          {metric.fmt(vMin)} – {metric.fmt(vMax)}
        </span>
      </div>

      {selected ? (
        <div className="mt-4 rounded-lg border border-border bg-surface p-4 text-sm">
          <p className="font-mono text-xs text-muted">
            {selected.geometry.coordinates[1].toFixed(3)}, {selected.geometry.coordinates[0].toFixed(3)}
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
            <Row k="correlation" v={selected.properties.correlation.toFixed(3)} />
            <Row k="RMSE" v={selected.properties.rmse.toFixed(1)} />
            <Row k="Kendall τ" v={selected.properties.kendall_tau.toFixed(3)} />
            <Row k="hedge effectiveness" v={`${(selected.properties.hedge_effectiveness * 100).toFixed(1)}%`} />
            <Row k="hedge ratio" v={selected.properties.hedge_ratio.toFixed(3)} />
            <Row k="tail dep. (upper)" v={selected.properties.tail_dependence_upper.toFixed(3)} />
            <Row k="tail dep. (lower)" v={selected.properties.tail_dependence_lower.toFixed(3)} />
            <Row k="n years" v={selected.properties.n_years.toString()} />
          </dl>
          <p className="mt-2 text-xs text-muted">
            A per-year scatter against the official index isn&apos;t in this
            endpoint&apos;s response (only aggregate stats are) — not shown
            rather than fabricated.
          </p>
        </div>
      ) : (
        <p className="mt-4 text-xs text-muted">Click a cell for its real per-cell stats.</p>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-foreground">{v}</span>
    </div>
  );
}
