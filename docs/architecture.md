# Architecture

How MonsoonQuant's real pieces connect, end to end: real external data in, a hash-chained public ledger and a dashboard out. No step in this diagram is a stub — every box is backed by real, tested code (`docs/STATUS.md` tracks exactly which milestone built it).

```mermaid
flowchart TB
    subgraph sources["External data sources (real, as-of bounded)"]
        IMD["IMD 0.25° gridded rainfall<br/>(1991-2020 + 2023, real-time Sep-Oct 2026)"]
        NOAA["NOAA ONI / BoM DMI<br/>(ENSO/IOD climate indices)"]
        NCDEX["NCDEX contract specs<br/>(official PDFs, hashed)"]
        BHAV["NCDEX bhavcopy<br/>(settlement data)"]
    end

    IMD --> DQ["DQ gate (DQ01-10)<br/>mq.pipelines"]
    NOAA --> DQ
    NCDEX --> SPECS["Contract spec registry<br/>mq.specs"]
    BHAV -.blocked: bot-gated.-x MARKET["market_quotes table"]

    DQ --> GRID["rain_grid / climate_idx<br/>Postgres, as-of aware (mq.io)"]
    SPECS --> GRID

    GRID --> INDEX["CDR index engine<br/>mq.index — compute_index"]
    GRID --> BURN["Burn + distribution pricing<br/>mq.pricing — 7 candidates, CRPS-selected"]
    GRID --> SIM["C++ chain simulator<br/>core/ — Philox4x32-10, 1M paths/0.8s"]
    GRID --> FCAST["Forecasting ladder<br/>mq.forecasting — clim/enso/analog/LightGBM/CQR"]

    SIM --> MPR["Market price of risk<br/>mq.mpr — Wang/Esscher"]
    MARKET -.illustrative settle only.-x MPR

    INDEX --> RISK["Risk engines<br/>mq.risk — Greeks, hedge (MV+CVaR), basis, parametric"]
    BURN --> RISK
    FCAST --> RISK

    BURN --> LEDGER
    FCAST --> LEDGER["Prediction ledger<br/>mq.ledger — append-only, SHA-256 hash chain"]

    INDEX --> API["REST API — FastAPI<br/>mq.api — 18/18 /v1 endpoints, rate-limited"]
    BURN --> API
    MPR --> API
    RISK --> API
    FCAST --> API
    LEDGER --> API

    API --> WEB["Dashboard — Next.js<br/>web/ — 9 pages, Lighthouse >=93"]
    API --> CLIENT["Typed TS client<br/>openapi-typescript + openapi-fetch"]
    CLIENT --> WEB
```

## The one hard rule this diagram enforces

Every arrow flows through the **as-of-aware `mq.io` layer** (`mq.io.asof`) — no computation ever reads data past its own `as_of` date. This is what makes the forecasting ladder's walk-forward backtest honest: a model trained for year *y* structurally cannot see year *y*'s own outcome, enforced in code, not by convention.

## Where the real gaps are (not hidden)

- **`bhavcopy` and MJO are bot-gated** at the source (NCDEX, BoM) and deliberately not worked around — this is why `market_quotes` stays empty and the market price of risk (λ) stays illustrative throughout.
- **The prediction ledger is local-only** — it's real and hash-chain-verified, but SPEC's "public ledger-mirror repo" (a separate, publicly-hosted copy for third-party verification) was never deployed.
- **M14 (cloud deployment) is not started** — everything above runs on `localhost`; there's no public dashboard URL yet.

See `docs/STATUS.md` for the full, current breakdown and `docs/DECISIONS.md` for why the bot-gates were left as policy rather than circumvented.
