import Link from "next/link";
import { Lineage } from "@/components/lineage";
import { SeasonProgress } from "@/components/season-progress";
import { getIndexPath, getQuotes, getValuationsCompare } from "@/lib/api/queries";
import type { components } from "@/lib/api/types";

type ListedSeries = components["schemas"]["ListedSeriesData"];

function fmtMm(v: number | null | undefined): string {
  return v == null ? "—" : `${v.toFixed(1)}mm`;
}

export async function ContractCard({ series }: { series: ListedSeries }) {
  const [compare, quotes, index] = await Promise.all([
    getValuationsCompare(series.series_id),
    getQuotes(series.series_id).catch(() => null),
    getIndexPath(series.series_id),
  ]);

  const dist =
    compare?.data.by_method?.["dist/P"] ?? compare?.data.by_method?.["burn/P"] ?? null;
  const latestQuote = quotes?.data.quotes?.at(-1) ?? null;
  const latestIndex = index?.data.points?.at(-1) ?? null;

  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-mono text-sm font-semibold">{series.series_id}</h2>
          <p className="text-xs text-muted">
            {series.contract_code} · {series.status ?? "unknown status"}
          </p>
        </div>
        <Link
          href={`/series/${series.series_id}/pricing`}
          className="text-xs text-accent hover:underline"
        >
          pricing →
        </Link>
      </div>

      <div className="mt-4">
        <SeasonProgress periodStart={series.period_start} periodEnd={series.period_end} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <dt className="text-xs text-muted">model fair value</dt>
          <dd className="mt-0.5 font-mono text-lg">
            {dist && compare ? (
              <Lineage meta={compare.meta} method={dist.method}>
                {fmtMm(dist.fair_value)}
              </Lineage>
            ) : (
              <span className="text-muted">pending</span>
            )}
          </dd>
          {dist && (
            <dd className="text-xs text-muted">
              90% band {fmtMm(dist.lo90)} – {fmtMm(dist.hi90)}
            </dd>
          )}
        </div>

        <div>
          <dt className="text-xs text-muted">latest settle</dt>
          <dd className="mt-0.5 font-mono text-lg">
            {latestQuote?.settle != null ? (
              fmtMm(latestQuote.settle)
            ) : (
              <span className="text-muted">no trades yet</span>
            )}
          </dd>
          <dd className="text-xs text-muted">
            {latestQuote
              ? `vol ${latestQuote.volume ?? "—"} · OI ${latestQuote.open_interest ?? "—"}`
              : "NCDEX bhavcopy not yet available"}
          </dd>
        </div>

        <div className="col-span-2">
          <dt className="text-xs text-muted">index — observed to date</dt>
          <dd className="mt-0.5 font-mono text-lg">
            {latestIndex && index ? (
              <Lineage meta={index.meta} method="official CDR index">
                {fmtMm(latestIndex.official_value ?? latestIndex.proxy_value)}
              </Lineage>
            ) : (
              <span className="text-muted">pending</span>
            )}
          </dd>
          {latestIndex && <dd className="text-xs text-muted">as of {latestIndex.obs_date}</dd>}
        </div>
      </dl>
    </div>
  );
}
