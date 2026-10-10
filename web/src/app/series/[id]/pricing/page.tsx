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
};

const METHOD_LABELS: Record<string, string> = {
  burn: "Burn (historical)",
  dist: "Distribution (KDE/CV-selected)",
  conditioned: "Forecast-conditioned",
};

const MEASURE_LABELS: Record<string, string> = {
  P: "Physical (P)",
  Q_wang: "Risk-neutral (Wang)",
  Q_esscher: "Risk-neutral (Esscher)",
};

const MEASURE_COLORS: Record<string, string> = {
  P: "var(--chart-1)",
  Q_wang: "var(--chart-3)",
  Q_esscher: "var(--chart-4)",
};

export default async function PricingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const compare = await getValuationsCompare(id);

  const byMethod = compare?.data.by_method ?? {};

  // "Method comparison" is P-measure only -- a method/Q_wang row (e.g.
  // burn/Q_wang) must never be picked up here just because its key
  // starts with "burn/"; measure is matched exactly, not by prefix.
  // "mpr" was never a real `method` value in the valuations table (no
  // row has ever had method="mpr" -- Q-measure prices live under
  // measure="Q_wang"/"Q_esscher" on a real method like "burn") -- it's
  // not one of SPEC's P-measure methods, so it doesn't belong in this
  // list at all; the P-vs-Q section below is the one real place
  // Q-measure status is shown.
  const builtMethods = ["burn", "dist", "conditioned"];
  const present = builtMethods.filter((m) => byMethod[`${m}/P`] != null);
  const missing = builtMethods.filter((m) => !present.includes(m));

  const bars: BarCompareDatum[] = present.map((m) => {
    const v = byMethod[`${m}/P`];
    return {
      label: METHOD_LABELS[m] ?? m,
      value: v.fair_value ?? 0,
      lo: v.lo90,
      hi: v.hi90,
      color: METHOD_COLORS[m] ?? "var(--chart-1)",
    };
  });

  // P vs Q: the first method (if any) with a real Q_wang or Q_esscher
  // row alongside its own P row -- a calibrated lambda/theta exists
  // for that method's payoff sample specifically.
  const qMethod = builtMethods.find(
    (m) => byMethod[`${m}/Q_wang`] != null || byMethod[`${m}/Q_esscher`] != null,
  );
  const pqMeasures = ["P", "Q_wang", "Q_esscher"] as const;
  const pqBars: BarCompareDatum[] = qMethod
    ? pqMeasures
        .filter((measure) => byMethod[`${qMethod}/${measure}`] != null)
        .map((measure) => {
          const v = byMethod[`${qMethod}/${measure}`];
          return {
            label: MEASURE_LABELS[measure],
            value: v.fair_value ?? 0,
            lo: v.lo90,
            hi: v.hi90,
            color: MEASURE_COLORS[measure],
          };
        })
    : [];

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
                  m === "conditioned"
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
        {qMethod ? (
          <>
            <p className="mt-1 text-xs text-muted">
              Physical (P) measure is the {METHOD_LABELS[qMethod]?.toLowerCase() ?? qMethod}{" "}
              sample above. The Q overlays reweight that same sample by a
              market price of risk (λ for Wang, θ for Esscher) calibrated
              against a real NCDEX settlement price —{" "}
              <strong>zero trading volume</strong> on every settlement date
              seen so far (these contracts aren&apos;t actively trading yet,
              per SPEC&apos;s own V11 question): an early, thin-market
              estimate, not a headline market price of risk. See
              docs/methods/mpr.md for the real calibration.
            </p>
            <div className="mt-4">
              <BarCompare data={pqBars} unit="mm" />
            </div>
          </>
        ) : (
          <>
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
          </>
        )}
      </section>
    </div>
  );
}
