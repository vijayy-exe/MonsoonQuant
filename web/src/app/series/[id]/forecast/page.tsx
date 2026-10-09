import { LineBand, type LineBandPoint } from "@/components/charts/line-band";
import { EmptyState } from "@/components/empty-state";
import { Lineage } from "@/components/lineage";
import { SeriesTabs } from "@/components/series-tabs";
import { getAnalogYears, getForecast, getIndexPath } from "@/lib/api/queries";

export const instant = false;

export default async function ForecastPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ model?: string }>;
}) {
  const { id } = await params;
  const { model } = await searchParams;
  const [forecast, index] = await Promise.all([getForecast(id), getIndexPath(id)]);

  const modelIds = Array.from(new Set(forecast?.data.rows.map((r) => r.model_id) ?? []));
  const activeModel = model ?? modelIds[0];
  const rows = (forecast?.data.rows ?? []).filter((r) => r.model_id === activeModel);

  const points: LineBandPoint[] = rows.map((r, i) => ({
    x: i,
    y: r.fair_value,
    lo: r.fair_value_lo90,
    hi: r.fair_value_hi90,
    label: r.as_of_date,
  }));

  const observedPoints: LineBandPoint[] | undefined = index?.data.points.length
    ? index.data.points.map((p, i) => ({
        x: (i / (index.data.points.length - 1 || 1)) * (points.length - 1 || 1),
        y: p.official_value ?? p.proxy_value,
        label: p.obs_date,
      }))
    : undefined;

  const analogYears = activeModel === "analog_v1" ? await getAnalogYears(id) : null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-lg font-semibold">{id}</h1>
      <div className="mt-4">
        <SeriesTabs seriesId={id} active="forecast" />
      </div>

      <section className="mt-8">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">
            Forecast — final index fan chart
          </h2>
          {modelIds.length > 0 && (
            <form method="get" className="text-xs">
              <label className="text-muted">
                model{" "}
                <select
                  name="model"
                  defaultValue={activeModel}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
                >
                  {modelIds.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            </form>
          )}
        </div>

        {points.length > 0 ? (
          <div className="mt-6">
            <LineBand
              points={points}
              secondary={observedPoints ? { label: "observed to date", points: observedPoints } : undefined}
              unit="mm"
            />
            <p className="mt-2 text-xs text-muted">
              <Lineage meta={forecast!.meta} method={activeModel}>
                {rows.length} ledger row{rows.length === 1 ? "" : "s"} for {activeModel}
              </Lineage>
              {" — from the hash-chained prediction ledger, SPEC §9's forecast-before-outcome guarantee."}
            </p>
          </div>
        ) : (
          <div className="mt-6">
            <EmptyState
              title="No forecast ledger rows"
              detail="This series' contract has no prediction_ledger rows yet for any model."
            />
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-foreground">Analog years</h2>
        {activeModel !== "analog_v1" ? (
          <p className="mt-2 text-xs text-muted">
            Only applies to the analog_v1 model — switch to it above to see which
            historical seasons it picked.
          </p>
        ) : analogYears ? (
          <div className="mt-4">
            <p className="text-xs text-muted">
              <Lineage meta={analogYears.meta} method="analog_v1 live selection">
                target year {analogYears.data.target_year}, issue date{" "}
                {analogYears.data.issue_date}, k={analogYears.data.k}
              </Lineage>
              {" — a live re-run of the real selection step, nearest first."}
            </p>
            <table className="mt-3 w-full max-w-sm text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="pb-2 pr-4">rank</th>
                  <th className="pb-2 pr-4">analog year</th>
                  <th className="pb-2">distance</th>
                </tr>
              </thead>
              <tbody>
                {analogYears.data.analog_years.map((year, i) => (
                  <tr key={year} className="border-t border-border">
                    <td className="py-1.5 pr-4 text-muted">{i + 1}</td>
                    <td className="py-1.5 pr-4 font-mono">{year}</td>
                    <td className="py-1.5 font-mono text-muted">
                      {analogYears.data.distances[i]?.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4">
            <EmptyState
              title="Analog selection unavailable"
              detail="Couldn't run the live selection for today — most likely a real data gap (e.g. this month's ONI/DMI not published yet, or a rain-grid ingestion gap), not a fabricated result."
            />
          </div>
        )}
      </section>
    </div>
  );
}
