import { LineBand, type LineBandPoint } from "@/components/charts/line-band";
import { EmptyState } from "@/components/empty-state";
import { Lineage } from "@/components/lineage";
import { SeriesTabs } from "@/components/series-tabs";
import { getForecast, getIndexPath } from "@/lib/api/queries";

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
        <div className="mt-4">
          <EmptyState
            title="Not exposed via the API yet"
            detail="analog_v1's chosen k=5 nearest seasons aren't part of /v1/series/{id}/forecast's response shape — only its resulting quantiles are. Would need a new field, not fabricated here."
          />
        </div>
      </section>
    </div>
  );
}
