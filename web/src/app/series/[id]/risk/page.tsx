import { LineBand, type LineBandPoint } from "@/components/charts/line-band";
import { EmptyState } from "@/components/empty-state";
import { Lineage } from "@/components/lineage";
import { SeriesTabs } from "@/components/series-tabs";
import { getGreeks, getMpr, getValuationsCompare } from "@/lib/api/queries";
import type { components } from "@/lib/api/types";

export const instant = false;

type GreekResultData = components["schemas"]["GreekResultData"];

function GreekTile({ label, result }: { label: string; result: GreekResultData | null }) {
  if (!result) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <p className="text-xs text-muted">{label}</p>
        <p className="mt-1 text-sm text-muted">n/a — season over</p>
      </div>
    );
  }
  const sePct = result.se_fraction * 100;
  const meetsBar = sePct < 5;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 font-mono text-xl">{result.value.toFixed(4)}</p>
      <p className="mt-1 text-xs text-muted">
        SE {result.se.toFixed(4)} ({sePct.toFixed(0)}%
        {meetsBar ? "" : ", above the <5% bar"}) · {result.pairing} pairing
      </p>
    </div>
  );
}

export default async function RiskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [greeks, mpr, compare] = await Promise.all([
    getGreeks(id),
    getMpr(id),
    getValuationsCompare(id),
  ]);

  const baseline =
    compare?.data.by_method["dist/P"]?.fair_value ??
    compare?.data.by_method["burn/P"]?.fair_value ??
    null;

  const curve: LineBandPoint[] =
    greeks && baseline != null
      ? Array.from({ length: 21 }, (_, i) => {
          const dx = -100 + i * 10;
          const d = greeks.data.delta.value;
          const g = greeks.data.gamma.value;
          return { x: dx, y: baseline + d * dx + 0.5 * g * dx * dx, label: `${dx >= 0 ? "+" : ""}${dx}mm` };
        })
      : [];

  // Wang (lambda) and Esscher (theta) are two different calibrated
  // parameters, not two observations of the same series -- plotting
  // them on one undifferentiated line would silently zigzag between
  // them at every shared as_of_date. Wang is SPEC's primary (with its
  // own CI band); Esscher overlays as a dashed secondary, the same
  // pattern the Forecast page already uses for "observed to date" --
  // giving SPEC's own named "Wang vs Esscher consistency" research
  // output a real, visible comparison instead of losing one transform.
  const toLambdaPoint = (p: NonNullable<typeof mpr>["data"]["points"][number]): LineBandPoint => ({
    x: new Date(p.as_of_date).getTime(),
    y: p.lambda_,
    lo: p.ci_lo,
    hi: p.ci_hi,
    label: p.as_of_date,
  });
  const wangPoints: LineBandPoint[] = (mpr?.data.points ?? [])
    .filter((p) => p.transform === "wang" && p.lambda_ != null)
    .map(toLambdaPoint);
  const esscherPoints: LineBandPoint[] = (mpr?.data.points ?? [])
    .filter((p) => p.transform === "esscher" && p.lambda_ != null)
    .map(toLambdaPoint);
  const lambdaPoints = wangPoints;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-lg font-semibold">{id}</h1>
      <div className="mt-4">
        <SeriesTabs seriesId={id} active="risk" />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-foreground">Greeks</h2>
        {greeks ? (
          <>
            <p className="mt-1 text-xs text-muted">
              <Lineage meta={greeks.meta} method={`fitted chain model, n_paths=${greeks.data.n_paths}`}>
                observed_to_date {greeks.data.observed_to_date.toFixed(1)}mm, start {greeks.data.start_date}
              </Lineage>
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <GreekTile label="delta" result={greeks.data.delta} />
              <GreekTile label="gamma" result={greeks.data.gamma} />
              <GreekTile label="theta (no-rain day)" result={greeks.data.theta_no_rain_day} />
              <GreekTile label="theta (climatological day)" result={greeks.data.theta_climatological_day} />
            </div>
          </>
        ) : (
          <div className="mt-4">
            <EmptyState title="Greeks unavailable" detail="This series' season may already be over, or it has no index value to default observed_to_date from." />
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-foreground">Value vs. rain</h2>
        <p className="mt-1 text-xs text-muted">
          Local quadratic approximation from the real delta/gamma above
          (fair value + delta·Δrain + ½·gamma·Δrain²) around the current
          observed-to-date point — not a full repricing curve across the
          whole range.
        </p>
        {curve.length > 0 ? (
          <div className="mt-4">
            <LineBand points={curve} unit="mm" />
          </div>
        ) : (
          <div className="mt-4">
            <EmptyState title="No baseline fair value" detail="Needs both Greeks and a valuation for this series." />
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-foreground">λ — market price of risk</h2>
        {lambdaPoints.length > 0 ? (
          <>
            <p className="mt-1 text-xs text-muted">
              Solid line + band: Wang λ (90% bootstrap CI). Dashed: Esscher θ,
              the same calibration on the same real settlement prices — SPEC&apos;s
              own cross-check between the two transforms. Every point so far
              is calibrated against a <strong>zero-volume</strong> settlement
              (these contracts aren&apos;t actively trading yet): an early
              estimate, not a headline market price of risk.
            </p>
            <div className="mt-4">
              <LineBand
                points={lambdaPoints}
                unit=""
                secondary={esscherPoints.length > 0 ? { label: "Esscher θ", points: esscherPoints } : undefined}
              />
            </div>
          </>
        ) : (
          <div className="mt-4">
            <EmptyState
              title="No real λ calibration yet"
              detail="M6's Wang/Esscher machinery is built and tested against real P-measure data (docs/methods/mpr.md), but this series has no real NCDEX settlement price to calibrate against yet (bhavcopy fetch is bot-gated for live download; a manually-downloaded bhavcopy unblocks it per-series, see docs/DECISIONS.md)."
            />
          </div>
        )}
      </section>
    </div>
  );
}
