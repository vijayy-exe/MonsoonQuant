"use client";

import { useState } from "react";

/**
 * Same formula as `mq.risk.parametric.wet_cover_payout` (payout =
 * min(limit, slope * max(0, index - trigger))) -- re-implemented
 * client-side purely for drag-to-update interactivity, not a
 * different/invented formula.
 */
function wetPayout(index: number, trigger: number, slope: number, limit: number): number {
  return Math.min(limit, slope * Math.max(0, index - trigger));
}

export function PayoffPlayground({ baselineIndex }: { baselineIndex: number }) {
  const [index, setIndex] = useState(Math.round(baselineIndex));
  const [trigger, setTrigger] = useState(Math.round(baselineIndex * 0.9));
  const [slope, setSlope] = useState(20);
  const [limit, setLimit] = useState(50_000);

  const payout = wetPayout(index, trigger, slope, limit);
  const maxIndex = Math.max(baselineIndex * 2, index, trigger) + 200;

  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <Slider label="rainfall index" value={index} min={0} max={maxIndex} step={5} unit="mm" onChange={setIndex} />
        <Slider label="trigger" value={trigger} min={0} max={maxIndex} step={5} unit="mm" onChange={setTrigger} />
        <Slider label="slope" value={slope} min={1} max={300} step={1} unit="" onChange={setSlope} />
        <Slider label="limit" value={limit} min={1000} max={500_000} step={1000} unit="" onChange={setLimit} />
      </div>

      <div className="mt-6 flex items-end gap-8">
        <div>
          <p className="text-xs text-muted">payout</p>
          <p className="font-mono text-2xl">{payout.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
        </div>
        <div className="h-16 flex-1">
          <svg viewBox="0 0 400 64" className="h-full w-full">
            <line x1={0} x2={400} y1={60} y2={60} stroke="var(--chart-axis)" strokeWidth={1} />
            <path
              d={Array.from({ length: 41 }, (_, i) => {
                const x = (i / 40) * maxIndex;
                const y = 60 - (wetPayout(x, trigger, slope, limit) / limit) * 56;
                return `${i === 0 ? "M" : "L"}${(x / maxIndex) * 400},${y}`;
              }).join(" ")}
              fill="none"
              stroke="var(--chart-1)"
              strokeWidth={2}
            />
            <circle
              cx={(index / maxIndex) * 400}
              cy={60 - (payout / limit) * 56}
              r={5}
              fill="var(--chart-2)"
            />
          </svg>
        </div>
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block text-xs text-muted">
      <span className="flex justify-between">
        <span>{label}</span>
        <span className="font-mono text-foreground">
          {value.toLocaleString()}
          {unit}
        </span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-[var(--accent)]"
      />
    </label>
  );
}
