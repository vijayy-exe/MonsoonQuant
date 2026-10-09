import { BasisGrid } from "@/components/basis-grid";
import { EmptyState } from "@/components/empty-state";
import { Lineage } from "@/components/lineage";
import { getBasis, listContracts } from "@/lib/api/queries";

export const instant = false;

export default async function BasisPage({
  searchParams,
}: {
  searchParams: Promise<{ series?: string }>;
}) {
  const { series: seriesParam } = await searchParams;
  const allSeries = await listContracts();
  const activeSeries = allSeries.filter((s) => s.status === "active");
  const seriesId = seriesParam ?? activeSeries[0]?.series_id;
  const basis = seriesId ? await getBasis(seriesId) : null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Basis Map</h1>
        {activeSeries.length > 0 && (
          <form method="get" className="text-xs">
            <label className="text-muted">
              series{" "}
              <select
                name="series"
                defaultValue={seriesId}
                className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
              >
                {activeSeries.map((s) => (
                  <option key={s.series_id} value={s.series_id}>
                    {s.series_id}
                  </option>
                ))}
              </select>
            </label>
          </form>
        )}
      </div>
      <p className="mt-1 text-sm text-muted">
        Correlation, hedge effectiveness and tail dependence between the
        official index and real IMD rainfall at each nearby grid cell
        (M10). A real on-demand run, cached by request — first load can
        take a few seconds.
      </p>

      {basis && basis.data.features.length > 0 ? (
        <div className="mt-6">
          <p className="text-xs text-muted">
            <Lineage meta={basis.meta} method="basis engine">
              {basis.data.features.length} real IMD grid cells
            </Lineage>
          </p>
          <div className="mt-3">
            <BasisGrid features={basis.data.features} />
          </div>
        </div>
      ) : (
        <div className="mt-6">
          <EmptyState title="No basis data" detail="Couldn't compute basis cells for this series." />
        </div>
      )}
    </div>
  );
}
