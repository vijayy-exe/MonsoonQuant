"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
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

const SEQUENTIAL_RAMP = ["#cde2fb", "#6da7ec", "#2a78d6", "#184f95", "#0d366b"];

// MapLibre's own free public demo style -- no API key, no account,
// intended exactly for this (low-traffic, non-production) use. A real
// deployment (M14) would swap this for a provider with an SLA.
const DEMO_STYLE = "https://demotiles.maplibre.org/style.json";

// Real bug found via Lighthouse, not assumed fine: maplibre-gl's
// default worker bootstrapping fails under Next.js/Turbopack's bundler
// ("Worker failed to load" / a 404 served as text/html, confirmed in
// the browser console) and silently falls back to parsing vector tiles
// on the main thread -- which is what actually tanked this page's
// Lighthouse performance score (47), not the WebGL canvas itself. Fix:
// serve the worker bundle as a plain static file and point maplibre at
// it explicitly, once, before any Map is constructed.
maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");

/**
 * SPEC §10 page 6: "MapLibre grid heatmap (corr / effectiveness / tail
 * dependence toggle); click cell → scatter vs index". The scatter-vs-
 * index part stays unbuilt (see the panel copy below) -- /basis
 * returns only aggregate per-cell stats, no raw paired series.
 */
export function BasisGrid({ features }: { features: BasisFeature[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [metricIdx, setMetricIdx] = useState(0);
  const [selected, setSelected] = useState<BasisFeature | null>(null);
  // WebGL init (shader compile, first paint of the demo style's vector
  // tiles) is genuinely expensive on the main thread -- measured via
  // Lighthouse: ~2s of blocking time when it's part of the critical
  // render path. Deferred past the initial paint via requestIdleCallback
  // (SPEC §10's own "skeleton loaders" rule, not a workaround) rather
  // than eaten by first load.
  const [ready, setReady] = useState(false);
  const metric = METRICS[metricIdx];

  const values = features.map((f) => f.properties[metric.key]);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);

  useEffect(() => {
    const idle = (
      window as unknown as {
        requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      }
    ).requestIdleCallback;
    if (idle) {
      const id = idle(() => setReady(true), { timeout: 1000 });
      return () => (window as unknown as { cancelIdleCallback?: (id: number) => void })
        .cancelIdleCallback?.(id);
    }
    const t = setTimeout(() => setReady(true), 200);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!ready || !containerRef.current || features.length === 0) return;

    const lons = features.map((f) => f.geometry.coordinates[0]);
    const lats = features.map((f) => f.geometry.coordinates[1]);
    const centerLon = (Math.min(...lons) + Math.max(...lons)) / 2;
    const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DEMO_STYLE,
      center: [centerLon, centerLat],
      zoom: 8,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(
      new maplibregl.AttributionControl({ compact: true, customAttribution: "MapLibre demo tiles" }),
    );

    map.on("load", () => {
      map.addSource("basis-cells", {
        type: "geojson",
        data: { type: "FeatureCollection", features },
      });
      map.addLayer({
        id: "basis-cells-circle",
        type: "circle",
        source: "basis-cells",
        paint: {
          "circle-radius": 10,
          "circle-color": "#2a78d6",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#fcfcfb",
        },
      });

      map.on("click", "basis-cells-circle", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const clicked = f.geometry as { coordinates: [number, number] };
        const match = features.find(
          (bf) =>
            bf.geometry.coordinates[0] === clicked.coordinates[0] &&
            bf.geometry.coordinates[1] === clicked.coordinates[1],
        );
        if (match) setSelected(match);
      });
      map.on(
        "mouseenter",
        "basis-cells-circle",
        () => (map.getCanvas().style.cursor = "pointer"),
      );
      map.on("mouseleave", "basis-cells-circle", () => (map.getCanvas().style.cursor = ""));
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // Re-init when the underlying data changes, or once `ready` flips
    // true -- not on metric toggle (handled by setPaintProperty below).
  }, [features, ready]);

  // Repaint circle colors when the metric toggle changes, without
  // tearing down the map (keeps pan/zoom position stable).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !map.getLayer("basis-cells-circle")) return;
    map.setPaintProperty("basis-cells-circle", "circle-color", [
      "interpolate",
      ["linear"],
      ["get", metric.key],
      vMin,
      SEQUENTIAL_RAMP[0],
      (vMin + vMax) / 2,
      SEQUENTIAL_RAMP[2],
      vMax,
      SEQUENTIAL_RAMP[4],
    ]);
  }, [metric.key, vMin, vMax]);

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

      <div className="relative mt-4 h-80 w-full overflow-hidden rounded-lg border border-border">
        {!ready && (
          <div className="absolute inset-0 animate-pulse bg-surface-muted" aria-hidden />
        )}
        <div
          ref={containerRef}
          className="h-full w-full"
          role="img"
          aria-label={`Map of ${features.length} basis-risk grid cells, colored by ${metric.label}`}
        />
      </div>

      <div className="mt-2 flex items-center gap-2 text-xs text-muted">
        <span>{metric.label}:</span>
        <span
          className="inline-flex h-3 w-16 rounded-full"
          style={{ background: `linear-gradient(90deg, ${SEQUENTIAL_RAMP.join(",")})` }}
        />
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
