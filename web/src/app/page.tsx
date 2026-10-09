import { ContractCard } from "@/components/contract-card";
import { FreshnessPill } from "@/components/freshness-pill";
import { getDataFreshness, listContracts } from "@/lib/api/queries";

// Every number on this page comes live from the API at request time
// (SPEC §17: "engines own every number") -- never statically prerendered.
export const instant = false;

export default async function OverviewPage() {
  const [series, freshness] = await Promise.all([listContracts(), getDataFreshness()]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-lg font-semibold">Overview</h1>
        <div className="flex flex-wrap gap-2">
          {freshness.data.sources.map((s) => (
            <FreshnessPill
              key={s.source}
              source={s.source}
              latestDate={s.latest_date}
              nRows={s.n_rows}
            />
          ))}
        </div>
      </div>

      {series.length === 0 ? (
        <p className="mt-8 text-sm text-muted">No contracts registered yet.</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {series.map((s) => (
            <ContractCard key={s.series_id} series={s} />
          ))}
        </div>
      )}
    </div>
  );
}
