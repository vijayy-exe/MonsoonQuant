# MonsoonQuant — one-page summary

**What it is.** An open, auditable quant-research platform for pricing and hedging India's exchange-traded rainfall futures (NCDEX's RAINCHNNAI, RAINMUMBAI). Research analytics, not trading advice.

**Why rainfall futures.** India's monsoon drives agriculture, insurance, and infrastructure risk at a scale few derivative markets address directly. NCDEX's rainfall contracts are new, thin, and under-researched — exactly the setting where a careful, honest quant framework (rather than a black box) has something real to say.

**What's built, end to end, on real data.**
- Real NCDEX contract specs (resolved from official PDFs, not placeholders) and 31 real seasons of IMD 0.25° gridded rainfall (1991-2020 + 2023, zero gaps), plus real ONI/DMI climate indices.
- A **physical-measure pricing stack**: historical burn analysis, a 7-candidate distribution zoo selected by leave-one-out CRPS, and a C++ chain-dependent Monte Carlo simulator (Philox4x32-10, 1,000,000 paths × 92 days in 0.82 seconds — 12x under its own budget, bit-identical across 1/2/4/8 threads).
- A **5-rung probabilistic forecasting ladder** (climatology → ENSO-conditioned → k-NN analog → LightGBM quantile → conformalized), walk-forward backtested against real data — and the honest finding that every added-complexity rung underperforms plain climatology at this sample size (n=31 seasons), reported rather than hidden or retuned.
- A **market-price-of-risk engine** (Wang and Esscher transforms) with bootstrap and Bayesian-pooled confidence intervals, built and tested but still illustrative-only: NCDEX's settlement data (`bhavcopy`) is bot-gated, and this project documents that as policy rather than circumventing it.
- A **risk and hedging layer**: exact-pairing Greeks via common random numbers, min-variance + CVaR95 hedge optimization, a basis-risk grid, and a parametric-cover designer — each with a real case study against real IMD rainfall at a real candidate location (an illustrative exposure, labelled as such throughout).
- A **public REST API** (18/18 SPEC-listed endpoints, zero stubs, rate-limited, OpenAPI-typed) and a **9-page Next.js dashboard** (Lighthouse ≥93/100 on every page, every category) with a MapLibre basis-risk map and a payoff playground.
- A **hash-chained, append-only prediction ledger**: every forecast is written before its outcome is known, so skill claims can't be revised after the fact.

**What's explicitly not done, and why.** NCDEX settlement data and MJO climate data are both bot-gated at the source — not worked around. Cloud deployment (a public URL) hasn't started; everything above runs locally. A handful of real numbers from earlier write-ups didn't reproduce exactly on re-run, and that's reported as a finding (`docs/methods/hedge.md` §6, `docs/methods/parametric.md` §4), not quietly corrected.

**Reproducibility.** `make reproduce` regenerates the preprint's real figures from real local data using the same committed functions the live API calls — no separate "demo" code path.

Full build spec: `docs/SPEC.md`. Current status: `docs/STATUS.md`. Preprint: `paper/preprint.md`.
