# VERIFY — open contract-specification questions (SPEC §3.2)

Must be closed from **official NCDEX/IMD sources** in M1 — do not invent any
answer. Each row is closed by quoting the source, page and exact clause
below, once the source PDF/document has been registered via
`specs/sources/*.yaml` and hashed into `specs/sources/raw/`.

Status legend: 🔴 open · 🟡 partially answered · 🟢 closed (source cited)

| # | Question | Why it matters | Status | Source / clause |
|---|---|---|---|---|
| V1 | Exact contract codes, listing date, active months/expiries | Contract calendar | 🔴 open | — |
| V2 | Stations / grid cells and how they are combined (mean? weighted?) | Index engine | 🔴 open | — |
| V3 | Index definition: cumulative rain vs cumulative deviation; mm vs % of LPA; daily or period | Payoff | 🔴 open | — |
| V4 | LPA source, base period and values per day/period | Index engine | 🔴 open | — |
| V5 | Data provider for settlement (IMD? which product? revision policy) | Proxy vs official | 🔴 open | — |
| V6 | Contract multiplier / lot size / tick size / price unit | Lots, P&L | 🔴 open | — |
| V7 | Daily price limits, position limits, order-size caps | Hedge constraints | 🔴 open | — |
| V8 | Margin (initial, ELM, special) | Hedge constraints | 🔴 open | — |
| V9 | Final settlement procedure and timing | Expiry handling | 🔴 open | — |
| V10 | Treatment of missing station data | Index robustness | 🔴 open | — |
| V11 | Whether products are actively traded, suspended or relaunched | Scope / fallbacks | 🔴 open | — |
| V12 | Data licensing for NCDEX price data and IMD data | Public redistribution | 🔴 open | — |

If V11 shows the contracts are not trading, switch to **Fallback Mode B**
(SPEC §14/§17 in the implementation plan) — shadow-price against the
official spec, keep everything else.

## Next action (M1.1–M1.2)

1. Download the official NCDEX contract specification PDFs for RAINCHNNAI
   and RAINMUMBAI (and any amendments) — place them for registration via
   `mq sources add <pdf>` once that command exists.
2. Register each in `specs/sources/*.yaml` with SHA-256, publisher, URL,
   published/effective dates.
3. Close V1–V12 one at a time, quoting page + clause here.
4. Build DRAFT `ContractSpec` YAMLs in `specs/contracts/{RAINCHNNAI,RAINMUMBAI}/`
   with `TODO_VERIFY` placeholders for anything still open; the loader
   rejects unresolved VERIFY fields unless `--allow-draft`.
