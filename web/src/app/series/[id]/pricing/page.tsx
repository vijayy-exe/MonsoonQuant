import { BarCompare, type BarCompareDatum } from "@/components/charts/bar-compare";
import { EmptyState } from "@/components/empty-state";
import { Lineage } from "@/components/lineage";
import { SeriesTabs } from "@/components/series-tabs";
import { getValuationsCompare } from "@/lib/api/queries";

export const instant = false;

const METHOD_COLORS: Record<string, string> = {
  burn: "var(--chart-1)",
  dist: "var(--chart-2)",
  conditioned: "var(--chart-3)",
  mpr: "var(--chart-4)",
};

const METHOD_LABELS: Record<string, string> = {
  burn: "Burn (historical)",
  dist: "Distribution (KDE/CV-selected)",
  conditioned: "Forecast-conditioned",
  mpr: "Market price of risk (Q)",
};

export default async function PricingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const compare = await getValuationsCompare(id);

  const builtMethods = ["burn", "dist", "conditioned", "mpr"];
  const present = builtMethods.filter((m) =>
    Object.keys(compare?.data.by_method ?? {}).some((k) => k.startsWith(`${m}/`)),
  );
  const missing = builtMethods.filter((m) => !present.includes(m));

  const bars: BarCompareDatum[] = present.map((m) => {
    const key = Object.keys(compare!.data.by_method).find((k) => k.startsWith(`${m}/`))!;
    const v = compare!.data.by_method[key];
    return {
      label: METHOD_LABELS[m] ?? m,
      value: v.fair_value ?? 0,
      lo: v.lo90,
      hi: v.hi90,
      color: METHOD_COLORS[m] ?? "var(--chart-1)",
    };
  });

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-lg font-semibold">{id}</h1>
      <div className="mt-4">
        <SeriesTabs seriesId={id} active="pricing" />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-foreground">
          Method comparison
          {compare && (
            <span className="ml-2 text-xs font-normal text-muted">
              <Lineage meta={compare.meta} method="valuations/compare">
                as of {compare.data.as_of_date}
              </Lineage>
            </span>
          )}
        </h2>
        <p className="mt-1 text-xs text-muted">
          Fair value with 90% interval, mm of the cumulative deviation rainfall
          index.
        </p>

        {bars.length > 0 ? (
          <div className="mt-6">
            <BarCompare data={bars} unit="mm" />
          </div>
        ) : (
          <div className="mt-6">
            <EmptyState
              title="No valuations yet"
              detail="Pricing hasn't been run for this series."
            />
          </div>
        )}

        {missing.length > 0 && (
          <div className="mt-6 space-y-2">
            {missing.map((m) => (
              <EmptyState
                key={m}
                title={`${METHOD_LABELS[m]} — not yet available`}
                detail={
                  m === "mpr"
                    ? "Blocked on real NCDEX settlement data (bhavcopy fetch is bot-gated) — M6's Wang/Esscher machinery is built and tested, but has nothing real to calibrate against yet."
                    : m === "conditioned"
                      ? "Forecast-conditioned pricing (M8) isn't written to the valuations table yet — it's built and demoed in docs/methods/conditioned.md, just not wired into this endpoint."
                      : "Not computed for this series."
                }
              />
            ))}
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-foreground">Payoff distribution — P vs Q</h2>
        <p className="mt-1 text-xs text-muted">
          Physical (P) measure comes from the distribution-selection engine
          above. The risk-neutral (Q) overlay needs a calibrated market price
          of risk (λ), which needs real settlement prices.
        </p>
        <div className="mt-4">
          <EmptyState
            title="Q-measure overlay not available"
            detail="No real NCDEX settlement data exists yet to calibrate λ against (see docs/methods/mpr.md for the illustrative-settle demo on real P-measure data)."
          />
        </div>
      </section>
    </div>
  );
}
