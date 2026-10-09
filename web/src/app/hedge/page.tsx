import { HedgeForm } from "@/components/hedge-form";
import { listContracts } from "@/lib/api/queries";

export const instant = false;

export default async function HedgePage() {
  const series = await listContracts();
  const activeSeries = series.filter((s) => s.status === "active");

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-lg font-semibold">Hedge Lab</h1>
      <p className="mt-1 text-sm text-muted">
        Min-variance and CVaR95 hedge sizing (M9) against a real contract
        index and a real candidate location&apos;s real IMD rainfall.
      </p>
      <div className="mt-4 rounded-md border border-accent-secondary/40 bg-surface-muted p-3 text-xs text-foreground">
        <strong>Synthetic exposure.</strong> The location&apos;s rainfall and
        the contract index are real; the exposure template and its size are
        an illustrative shape, not a calibrated real business — same
        posture as SPEC §7.11&apos;s own case study.
      </div>

      <div className="mt-8">
        <HedgeForm seriesOptions={activeSeries.map((s) => s.series_id)} />
      </div>
    </div>
  );
}
