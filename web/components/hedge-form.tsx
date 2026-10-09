"use client";

import { useState } from "react";
import { postHedge } from "@/lib/api/queries";
import type { components } from "@/lib/api/types";

type HedgeResponseData = components["schemas"]["HedgeResponseData"];

const TEMPLATES = [
  { value: "delivery_rider", label: "Delivery-rider income loss" },
  { value: "crop_yield", label: "Crop yield loss" },
  { value: "event_cancellation", label: "Event cancellation" },
  { value: "construction_downtime", label: "Construction downtime" },
] as const;

export function HedgeForm({ seriesOptions }: { seriesOptions: string[] }) {
  const [seriesId, setSeriesId] = useState(seriesOptions[0] ?? "");
  const [lat, setLat] = useState(13.0827);
  const [lon, setLon] = useState(80.2707);
  const [template, setTemplate] = useState<(typeof TEMPLATES)[number]["value"]>(
    "delivery_rider",
  );
  const [maxLots, setMaxLots] = useState<string>("5");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HedgeResponseData | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    const res = await postHedge({
      series_id: seriesId,
      location_lat: lat,
      location_lon: lon,
      exposure_template: template,
      alpha: 0.95,
      constraints: {
        max_order_lots: maxLots ? Number(maxLots) : undefined,
        long_allowed: true,
        short_allowed: true,
      },
    });
    setLoading(false);
    if ("problem" in res) {
      setError(res.problem);
    } else {
      setResult(res.data);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="text-xs text-muted">
          series
          <select
            value={seriesId}
            onChange={(e) => setSeriesId(e.target.value)}
            className="mt-1 block w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-foreground"
          >
            {seriesOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-muted">
          exposure template
          <select
            value={template}
            onChange={(e) => setTemplate(e.target.value as typeof template)}
            className="mt-1 block w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-foreground"
          >
            {TEMPLATES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-muted">
          location lat
          <input
            type="number"
            step="0.0001"
            value={lat}
            onChange={(e) => setLat(Number(e.target.value))}
            className="mt-1 block w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-foreground"
          />
        </label>

        <label className="text-xs text-muted">
          location lon
          <input
            type="number"
            step="0.0001"
            value={lon}
            onChange={(e) => setLon(Number(e.target.value))}
            className="mt-1 block w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-foreground"
          />
        </label>

        <label className="text-xs text-muted">
          max order lots (blank = unconstrained)
          <input
            type="number"
            value={maxLots}
            onChange={(e) => setMaxLots(e.target.value)}
            placeholder="unconstrained"
            className="mt-1 block w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-foreground"
          />
        </label>
      </div>

      <button
        type="button"
        onClick={run}
        disabled={loading || !seriesId}
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground disabled:opacity-50"
      >
        {loading ? "optimising…" : "Run optimiser"}
      </button>

      {error && (
        <p className="rounded-md border border-border bg-surface-muted p-3 text-sm text-foreground">
          {error}
        </p>
      )}

      {result && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border bg-surface p-4">
            <h3 className="text-sm font-semibold">Min-variance</h3>
            <dl className="mt-2 space-y-1 text-xs">
              <Row k="lots" v={result.min_variance.lots.toString()} />
              <Row k="hedge effectiveness" v={`${(result.min_variance.hedge_effectiveness * 100).toFixed(1)}%`} />
              <Row k="variance: do nothing" v={result.min_variance.do_nothing_variance.toExponential(3)} />
              <Row k="variance: hedged" v={result.min_variance.residual_variance.toExponential(3)} />
              <Row k="basis contribution" v={result.min_variance.basis_contribution.toFixed(3)} />
            </dl>
          </div>
          <div className="rounded-lg border border-border bg-surface p-4">
            <h3 className="text-sm font-semibold">CVaR95</h3>
            <dl className="mt-2 space-y-1 text-xs">
              <Row k="lots" v={result.cvar95.lots.toString()} />
              <Row k="CVaR95: do nothing" v={result.cvar95.do_nothing_cvar_95.toFixed(1)} />
              <Row k="CVaR95: hedged" v={result.cvar95.cvar_95.toFixed(1)} />
              <Row k="VaR95" v={result.cvar95.var_95.toFixed(1)} />
            </dl>
            {Math.abs(result.cvar95.lots) >= 9000 && (
              <p className="mt-2 text-xs text-accent-secondary">
                Hit the unconstrained fallback cap — this contract&apos;s index
                has been positive in every historical season, so an
                unconstrained CVaR optimum doesn&apos;t exist. Set a lot limit
                above.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-foreground">{v}</span>
    </div>
  );
}
