# VERIFY — contract-specification questions (SPEC §3.2)

Status legend: 🔴 open · 🟡 partially answered · 🟢 closed (source cited)

Closed from the official NCDEX documents, registered and hashed in
`specs/sources/`:
- `ncdex_spec_rainchnnai_2026` / `ncdex_spec_rainmumbai_2026` — Contract Specifications
- `ncdex_product_note_rainchnnai_2026` / `ncdex_product_note_rainmumbai_2026` — Product Notes (Exhibit 2: CDR spot methodology)
- `ncdex_launch_circular_rainchnnai_2026` / `ncdex_launch_circular_rainmumbai_2026` — launch circulars

Resolved values are encoded in `specs/contracts/RAINCHNNAI/2026-08-31.yaml`
and `specs/contracts/RAINMUMBAI/2026-05-29.yaml`, which now load **without**
`--allow-draft`.

| # | Question | Status | Answer |
|---|---|---|---|
| V1 | Exact contract codes, listing date, active months/expiries | 🟢 closed | RAINCHNNAI: launched Aug 31, 2026; contract months Sep/Oct/Nov/Dec 2026 (ongoing per launch calendar). RAINMUMBAI: launched May 29, 2026; contract months Jun/Jul/Aug/Sep 2026. (Circulars NCDEX/TRADING-038/2026 Aug 28 2026; Mumbai launch circular) |
| V2 | Stations / grid cells and how combined | 🟢 closed | RAINCHNNAI: Meenambakkam + Nungambakkam, **simple average** (not weighted), for both rainfall and LPA. RAINMUMBAI: Colaba + Santacruz, simple average. (Product Notes, Exhibit 2 §4, §a) |
| V3 | Index definition: cumulative rain vs deviation; mm; period | 🟢 closed | **Cumulative Deviation Rainfall (CDR)**: spot = season-LPA anchor + running sum of daily (actual − LPA) deviation in mm, starting day 1 of the period. RAINCHNNAI period: **Sep 1 – Dec 31**. RAINMUMBAI period: **Jun 1 – Sep 30**. (Product Notes, Exhibit 2 §1, §2d) |
| V4 | LPA source, base period, values | 🟢 closed | IMD climatological normal. RAINCHNNAI base period **1971–2020** (50yr), season-LPA anchor **998.25mm**. RAINMUMBAI base period **1991–2020** (30yr), season-LPA anchor **2206.7mm**. Day-by-day LPA table not yet ingested as data (M3). (Product Notes, Exhibit 2 §1 "Long Period Average") |
| V5 | Data provider for settlement | 🟢 closed | IMD, via an "authenticated API feed." Surface Rainfall Observation (manual, WMO-standard synoptic readings, 8/day) is primary; AWS (15-min) is a transparency/fallback layer. (Product Notes, Exhibit 2 §5) |
| V6 | Contract multiplier / lot / tick / price unit | 🟢 closed | 1mm = Rs.50 (multiplier); tick size 1mm; unit of trading = 1 lot; quotation in mm. Identical for both contracts. (Contract Specifications) |
| V7 | Daily price limits, position limits, order-size caps | 🟢 closed | Max order size 50 lots. DPL: initial 6%, enhanced 3%, aggregate 9% (15-min cooling-off). Position limits: member-wise 4,00,000 lots or 20% of market-wide OI (higher); client-wise 40,000 lots or 5% of market-wide OI (higher). Concentration-margin OI threshold: 1,16,400 lots. Identical for both contracts. (Contract Specifications; launch circulars) |
| V8 | Margin (initial, ELM, special) | 🟢 closed | Minimum initial margin 10%; NCCL risk-based model targets ≥99% VaR with 3-day MPOR on top of that floor. Special/additional margin discretionary on unidirectional moves. (Contract Specifications; Product Notes §"Margin Requirements") |
| V9 | Final settlement procedure and timing | 🟢 closed | Cash settled. FSP = CDR spot value on due/expiry day. Last trading day = business day before the last calendar day of the expiry month; due/expiry day = the following calendar day. T+2 cash settlement. No physical delivery. (Contract Specifications) |
| V10 | Treatment of missing station data | 🟢 closed | AWS data is the fallback when Surface data is delayed/unavailable/discrepant; Exchange may onboard further fallback agencies with notice. (Product Notes, Exhibit 2 §5 "Fallback Mechanism") |
| V11 | Actively traded, suspended, or relaunched | 🟢 closed | Both actively trading: RAINCHNNAI since Aug 31 2026 (SEBI-approved, Circular NCDEX/TRADING-038/2026); RAINMUMBAI since May 29 2026. |
| V12 | Data licensing for NCDEX price data and IMD data | 🔴 open | None of the sourced documents state explicit redistribution/licensing terms for NCDEX price data or the IMD feed NCDEX consumes via its "authenticated API." Governed generally by NCDEX Bye-Laws/Rules/Regulations, not a citable public licence. Treat as **not cleared for redistribution** until resolved — this project only stores and analyzes the data, doesn't republish it. |

**Scope note on V11:** "actively traded" here means *launched and open for
trading* per SEBI/NCDEX circulars — it does not yet confirm actual trading
*volume* (could still be thin, per SPEC §3.1's "thin market" caveat). That's
an M2 data question (ingest NCDEX bhavcopy, look at real volume/OI), not a
VERIFY one.

## Still to do
- Confirm exact station lat/lon against official IMD station metadata
  (currently using commonly-cited public coordinates as an engineering
  placeholder for nearest-grid-cell lookup — doesn't affect any VERIFY
  item, only the M3 index-engine implementation).
- Ingest the actual day-by-day LPA tables (`chennai_lpa.pdf`,
  `mumbai_lpa` equivalent — not yet registered as sources) so
  `LPARef.table_object_key` points to real data rather than `null`.
- V12: either find an explicit licence statement, or treat the
  redistribution question as permanently open and keep all derived
  products research/analytics-only, consistent with SPEC's own
  positioning (§0, "Not trading advice").
