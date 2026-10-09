import { PayoffPlayground } from "@/components/payoff-playground";
import { getValuationsCompare, listContracts } from "@/lib/api/queries";

export const instant = false;

const GLOSSARY: { term: string; def: string }[] = [
  { term: "CDR index", def: "Cumulative Deviation from the season-LPA — the official rainfall index this contract settles against." },
  { term: "LPA", def: "Long Period Average: the climatological daily/seasonal baseline the index measures deviation from." },
  { term: "Burn analysis", def: "Pricing a contract off the plain historical distribution of past seasonal outcomes, no model fitting." },
  { term: "P-measure / Q-measure", def: "P is the real-world (physical) probability measure; Q is the risk-neutral measure implied by market prices, shifted from P by the market price of risk (λ)." },
  { term: "λ (lambda)", def: "The market price of risk: how far the pricing measure (Q) is shifted from the physical measure (P), estimated via Wang/Esscher transforms calibrated to settlement prices." },
  { term: "CVaR95", def: "Conditional Value-at-Risk at the 95% level — the expected loss in the worst 5% of scenarios, used as the hedge optimiser's risk measure alongside variance." },
  { term: "Basis risk", def: "The gap between a real local exposure's own rainfall and the official index's rainfall at its measurement station(s) — hedges with an index are never perfect because of this gap." },
  { term: "CRPS / CRPSS", def: "Continuous Ranked Probability Score (a proper scoring rule for probabilistic forecasts) and its Skill Score relative to a baseline (climatology)." },
  { term: "Prediction ledger", def: "An append-only, hash-chained log every forecast is written to before its outcome is known, so skill claims can't be revised after the fact." },
];

export default async function LearnPage() {
  const series = await listContracts();
  const active = series.find((s) => s.status === "active");
  const compare = active ? await getValuationsCompare(active.series_id) : null;
  const baseline =
    compare?.data.by_method["dist/P"]?.fair_value ??
    compare?.data.by_method["burn/P"]?.fair_value ??
    900;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-lg font-semibold">Learn</h1>
      <p className="mt-1 text-sm text-muted">
        A parametric-cover payoff playground and a glossary of the terms
        used across this dashboard.
      </p>

      <section className="mt-8">
        <h2 className="text-sm font-semibold text-foreground">Payoff playground</h2>
        <p className="mt-1 text-xs text-muted">
          Same capped-linear formula M11&apos;s parametric-cover designer
          uses (payout = min(limit, slope·max(0, index − trigger))),
          starting from {active?.series_id ?? "a contract"}&apos;s real
          current fair value as the index slider&apos;s baseline.
        </p>
        <div className="mt-4">
          <PayoffPlayground baselineIndex={baseline} />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-semibold text-foreground">Glossary</h2>
        <dl className="mt-4 space-y-4">
          {GLOSSARY.map((g) => (
            <div key={g.term}>
              <dt className="text-sm font-medium text-foreground">{g.term}</dt>
              <dd className="mt-0.5 text-sm text-muted">{g.def}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
