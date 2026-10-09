"use client";

import { useId, useState } from "react";
import type { Meta } from "@/lib/api/client";

/**
 * SPEC §10: "every number hoverable to reveal its lineage". Wraps any
 * rendered value; on hover/focus shows the envelope's meta (as_of,
 * method, data_version, model_version) rather than hiding provenance
 * behind a separate page.
 */
export function Lineage({
  children,
  meta,
  method,
}: {
  children: React.ReactNode;
  meta: Meta | null | undefined;
  method?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-describedby={open ? panelId : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="cursor-help underline decoration-dotted decoration-muted underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-sm"
      >
        {children}
      </button>
      {open && (
        <span
          id={panelId}
          role="tooltip"
          className="absolute left-1/2 top-full z-20 mt-2 w-56 -translate-x-1/2 rounded-md border border-border bg-surface p-3 text-xs text-muted shadow-lg"
        >
          <span className="block font-medium text-foreground">
            {method ?? "lineage"}
          </span>
          <LineageRow label="as of" value={meta?.as_of ?? "—"} />
          <LineageRow label="data version" value={meta?.data_version ?? "—"} />
          <LineageRow label="model version" value={meta?.model_version ?? "—"} />
          <LineageRow label="spec version" value={meta?.spec_version ?? "—"} />
          {meta?.synthetic && (
            <span className="mt-1 block font-medium text-accent-secondary">
              synthetic
            </span>
          )}
        </span>
      )}
    </span>
  );
}

function LineageRow({ label, value }: { label: string; value: string }) {
  return (
    <span className="mt-0.5 flex justify-between gap-2 first:mt-0">
      <span>{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </span>
  );
}
