import { PitHistogram } from "@/components/charts/pit-histogram";
import { EmptyState } from "@/components/empty-state";
import { HashChainBadge } from "@/components/hash-chain-badge";
import { Lineage } from "@/components/lineage";
import { getLedgerVerify, getTrackRecord, listLedgerRows } from "@/lib/api/queries";

export const instant = false;

export default async function TrackRecordPage() {
  const [verify, rows, trackRecord] = await Promise.all([
    getLedgerVerify(),
    listLedgerRows(),
    getTrackRecord(),
  ]);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-lg font-semibold">Track Record</h1>
      <p className="mt-1 text-sm text-muted">
        Every forecast is written to a hash-chained, append-only ledger
        before its outcome is known (SPEC §17: no look-ahead). CRPS/
        coverage/PIT below are a live re-run of the real walk-forward
        backtest, not stored numbers — first load can take ~40s, cached
        after.
      </p>

      <section className="mt-8">
        {verify ? (
          <div className="flex items-center gap-3">
            <HashChainBadge valid={verify.data.valid} nRows={verify.data.n_rows} />
            <span className="text-xs text-muted">
              Public ledger-mirror repo not deployed yet (M1 deferred item) —
              no link to show.
            </span>
          </div>
        ) : (
          <EmptyState
            title="Ledger status unavailable"
            detail="The verify endpoint didn't return a result (transient error, e.g. a rate limit) — not the same as a broken chain."
          />
        )}

        {rows && rows.data.rows.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="pb-2 pr-4">contract</th>
                  <th className="pb-2 pr-4">model</th>
                  <th className="pb-2 pr-4">version</th>
                  <th className="pb-2 pr-4">as of</th>
                  <th className="pb-2 pr-4">target</th>
                  <th className="pb-2">row hash</th>
                </tr>
              </thead>
              <tbody>
                {rows.data.rows.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="py-1.5 pr-4 font-mono">{r.contract_code}</td>
                    <td className="py-1.5 pr-4">{r.model_id}</td>
                    <td className="py-1.5 pr-4 text-muted">{r.model_version}</td>
                    <td className="py-1.5 pr-4">{r.as_of_date}</td>
                    <td className="py-1.5 pr-4 text-muted">{r.target}</td>
                    <td className="py-1.5 font-mono text-muted">{r.row_hash.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4">
            <EmptyState title="No ledger rows" detail="Nothing has been written to the prediction ledger yet." />
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-foreground">
          Walk-forward backtest — {trackRecord?.data.contract_code ?? "—"}
        </h2>
        {trackRecord ? (
          <>
            <p className="mt-1 text-xs text-muted">
              <Lineage meta={trackRecord.meta} method="walk_forward_backtest">
                {trackRecord.data.n_training_years} seasons, min train{" "}
                {trackRecord.data.min_train_years} years
              </Lineage>
            </p>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {trackRecord.data.rungs.map((r) => (
                <div key={r.model_id} className="rounded-lg border border-border bg-surface p-4">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-sm font-semibold">{r.model_id}</h3>
                    <span className="font-mono text-xs text-muted">
                      CRPS {r.mean_crps.toFixed(2)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    {r.crpss_vs_baseline != null
                      ? `CRPSS vs climatology: ${(r.crpss_vs_baseline * 100).toFixed(1)}%`
                      : "baseline model"}{" "}
                    · {r.n_predictions} predictions
                  </p>
                  <div className="mt-3">
                    <PitHistogram
                      binEdges={r.pit_histogram.bin_edges}
                      counts={r.pit_histogram.counts}
                    />
                  </div>
                  <ul className="mt-2 flex gap-3 text-xs text-muted">
                    {Object.entries(r.coverage_by_level).map(([level, cov]) => (
                      <li key={level}>
                        {level}: {(cov * 100).toFixed(0)}%
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs text-muted">
              Reported honestly: every newer rung has underperformed plain
              climatology on CRPS at this sample size (n=
              {trackRecord.data.n_training_years} seasons) — see
              docs/methods/forecasting.md.
            </p>
          </>
        ) : (
          <div className="mt-4">
            <EmptyState title="No backtest available" detail="Needs real training rows for this contract." />
          </div>
        )}
      </section>
    </div>
  );
}
