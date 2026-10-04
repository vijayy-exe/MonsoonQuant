# MonsoonQuant — Full-Fledged Implementation Plan

**Project:** MonsoonQuant  
**Type:** Quantitative finance + weather derivatives research and production platform  
**Target launch:** Mid-January 2027  
**Primary stack:** Python + C++17 + FastAPI + Next.js + PostgreSQL/Parquet + AWS  
**Core objective:** Build an open analytics platform that explains the fair value, risk, and hedge requirements of India's exchange-traded rainfall futures.

---

## 1. Product Definition

### 1.1 One-line product

> **MonsoonQuant prices, forecasts, explains, and hedges India's exchange-traded rainfall futures.**

The platform should answer:

1. What is the current rainfall-futures index?
2. What should the contract be worth under multiple pricing approaches?
3. How uncertain is that fair value?
4. What rainfall/season information is driving the value?
5. What is the market-implied price of rainfall risk?
6. How sensitive is the contract to additional rainfall and time decay?
7. How many futures lots should a weather-exposed business use to hedge?
8. How much residual basis risk remains?
9. Could the same infrastructure design a parametric rain/heat cover?

The project should be positioned as a **research and analytics platform**, not as a trading-advice product.

---

# 2. Why This Project Is Strong

The project combines several layers that should remain visibly separate:

### Quantitative finance
- Derivative payoff modelling
- Risk-neutral / transformed distributions
- Market price of risk
- Monte Carlo simulation
- Greeks
- Minimum-variance hedging
- CVaR optimisation
- Basis risk

### Machine learning
- Probabilistic rainfall forecasting
- Quantile prediction
- Temporal forecasting
- Forecast calibration

### Data engineering
- Climate-data ingestion
- Market-data ingestion
- Historical data versioning
- Daily automated pipelines

### Software engineering
- C++ simulation core
- Python research layer
- Typed REST API
- Production dashboard
- Automated tests
- CI/CD
- Monitoring

### Research
The strongest research question is:

> **How should the market price of rainfall risk be estimated in a newly established rainfall-derivatives market when the available price history is short and trading may be thin?**

The answer must be empirical and uncertainty-aware. Do not claim a definitive market risk premium from a short sample.

---

# 3. Final System Architecture

```text
                 ┌───────────────────────────────┐
                 │         External Data          │
                 │ IMD / ERA5 / ENSO / IOD       │
                 │ NCDEX prices + specifications  │
                 └──────────────┬────────────────┘
                                │
                                ▼
                 ┌───────────────────────────────┐
                 │       Ingestion Layer         │
                 │ validation / deduplication    │
                 │ schema checks / provenance     │
                 └──────────────┬────────────────┘
                                │
                                ▼
                 ┌───────────────────────────────┐
                 │      Data Storage Layer       │
                 │ PostgreSQL + Parquet + S3     │
                 └───────┬───────────────┬───────┘
                         │               │
              ┌──────────▼──────┐ ┌─────▼────────────┐
              │ Index Engine     │ │ Forecast Engine  │
              │ CDR replication  │ │ LightGBM / TFT   │
              └──────────┬──────┘ └─────┬────────────┘
                         │              │
                         └──────┬───────┘
                                ▼
                 ┌───────────────────────────────┐
                 │       Pricing Engine          │
                 │ burn / distribution / MC      │
                 │ C++ simulation + Python API   │
                 └──────────────┬────────────────┘
                                ▼
                 ┌───────────────────────────────┐
                 │       Risk Engine              │
                 │ MPR / Greeks / hedge / basis  │
                 │ CVaR / scenario analysis       │
                 └──────────────┬────────────────┘
                                ▼
                 ┌───────────────────────────────┐
                 │         FastAPI                │
                 └──────────────┬────────────────┘
                                ▼
                 ┌───────────────────────────────┐
                 │      Next.js Dashboard         │
                 │ charts / pricing / risk / API  │
                 └───────────────────────────────┘
```

---

# 4. Repository Structure

```text
monsoonquant/
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
│
├── core/
│   ├── include/
│   ├── src/
│   ├── tests/
│   └── bindings/
│
├── data/
│   ├── schemas/
│   └── fixtures/
│
├── pipelines/
│   ├── imd/
│   ├── era5/
│   ├── ncdex/
│   ├── climate/
│   └── orchestration/
│
├── index/
│   ├── cdr.py
│   ├── validation.py
│   └── specs.py
│
├── pricing/
│   ├── burn.py
│   ├── distribution.py
│   ├── simulation.py
│   ├── mpr.py
│   └── calibration.py
│
├── forecasting/
│   ├── features.py
│   ├── lightgbm_model.py
│   ├── tft_model.py
│   ├── calibration.py
│   └── evaluation.py
│
├── risk/
│   ├── greeks.py
│   ├── hedge.py
│   ├── cvar.py
│   ├── basis.py
│   └── scenarios.py
│
├── api/
│   ├── main.py
│   ├── schemas.py
│   └── routes/
│
├── web/
│   ├── app/
│   ├── components/
│   └── lib/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── property/
│   └── golden/
│
├── notebooks/
│   ├── research/
│   └── validation/
│
├── docs/
│   ├── methods/
│   ├── ADRs/
│   └── data_dictionary.md
│
└── infra/
    ├── terraform/
    └── github-actions/
```

---

# 5. Phase 0 — Lock the Financial Specification

**Duration:** 2–3 days

Before writing the pricing engine, freeze the contract specification.

## Tasks

- Obtain and archive official contract specifications.
- Record publication/version date.
- Determine:
  - stations/grid mapping
  - rainfall averaging
  - cumulative deviation calculation
  - long-period average
  - contract month
  - payoff formula
  - tick/lot size
  - settlement procedure
  - order limits
  - expiry
- Create a versioned YAML specification.

Example:

```yaml
contract: RAINCHNNAI
version: "2026-08-31"
location: Chennai
stations:
  - Meenambakkam
  - Nungambakkam
index:
  type: cumulative_deviation
  lpa_source: official_document
payoff:
  unit: INR
lot_size: official_spec
```

### Gate

Do not begin model calibration until the contract specification is independently reproducible from the stored source document.

---

# 6. Phase 1 — Data Infrastructure

**Duration:** Week 1

## 6.1 Market data

Build:

```text
NCDEX downloader
      ↓
raw CSV/PDF
      ↓
schema validation
      ↓
normalised contract table
      ↓
PostgreSQL + Parquet
```

Store:

- date
- contract
- expiry
- settlement price
- volume
- open interest
- source
- ingestion timestamp
- source hash

Never overwrite raw files.

## 6.2 Climate data

Create a common schema:

```text
date
latitude
longitude
rainfall_mm
temperature
humidity
wind
source
version
```

## 6.3 Climate drivers

Add:

- ONI
- IOD/DMI
- recent rainfall anomalies
- seasonal rainfall features

## 6.4 Data-quality checks

Every pipeline must test:

- missing dates
- duplicate dates
- impossible rainfall values
- schema changes
- stale market data
- unexpected contract names
- source-file changes

### Gate

A failed data-quality check must prevent downstream model publication.

---

# 7. Phase 2 — Index Replication Engine

**Duration:** Week 1

Implement the official rainfall index independently.

### Required outputs

For every trading day:

```json
{
  "contract": "RAINCHNNAI",
  "date": "YYYY-MM-DD",
  "proxy_index": 0.0,
  "official_index": null,
  "proxy_error": null,
  "data_version": "..."
}
```

When official values become available:

```text
proxy
official
absolute error
percentage error
```

### Acceptance test

Target:

> Mean absolute proxy error below 5% of LPA, subject to availability and correctness of the underlying proxy data.

Do not hide a poor proxy. A transparent basis/proxy error is itself a useful research result.

---

# 8. Phase 3 — Historical Burn Analysis

**Duration:** Week 2

For every historical rainfall season:

1. Reconstruct the contract index.
2. Calculate the historical payoff.
3. Detrend where methodologically justified.
4. Build the historical payoff distribution.
5. Calculate:
   - mean
   - median
   - standard deviation
   - quantiles
   - skewness
   - tail losses

Dashboard:

```text
Historical payoff distribution
│
├── P5
├── P25
├── Median
├── P75
└── P95
```

This becomes the first fair-value benchmark.

---

# 9. Phase 4 — Index-Distribution Pricing

**Duration:** Week 2

Compare candidate distributions:

- Gamma
- Lognormal
- KDE
- Bootstrap

Use:

- AIC
- out-of-sample log-likelihood
- distributional diagnostics

Do not choose a distribution solely because it visually fits the historical histogram.

### Required experiment

```text
Train years → distribution fit
Validation years → likelihood / pricing error
```

Store every experiment in MLflow or an equivalent experiment registry.

---

# 10. Phase 5 — Stochastic Rainfall Simulator

**Duration:** Week 3

Build the primary simulation engine.

## Wet/dry model

Use a two-state Markov process:

```text
Dry → Dry
Dry → Wet
Wet → Dry
Wet → Wet
```

## Rainfall amount

Conditional on wet day:

- Gamma or mixed exponential
- seasonally varying parameters

## Seasonality

Use Fourier terms or another documented seasonal representation.

## Simulation

Target:

> 1,000,000 paths in under 10 seconds on the deployment benchmark machine.

### C++ responsibilities

- random-number generation
- path simulation
- aggregation
- payoff calculation

### Python responsibilities

- configuration
- orchestration
- analysis
- plotting
- API integration

Use pybind11 between the two.

---

# 11. Phase 6 — Market Price of Risk

**Duration:** Week 4

Use a documented transformation such as Wang or Esscher.

Example Wang transform:

```text
F*(x) = Φ(Φ⁻¹(F(x)) - λ)
```

Estimate λ so model-implied price matches observed settlement.

Track:

```text
contract
date
days-to-expiry
lambda
confidence interval
settlement
model price
```

### Critical research rule

Because the market is new:

- report confidence intervals
- report sample size
- report liquidity
- avoid claiming that λ is a stable structural premium
- update estimates as new observations arrive

The headline research output should be an **early empirical estimate**, not an overconfident universal parameter.

---

# 12. Phase 7 — Probabilistic Rainfall Forecasting

**Duration:** Week 9

Build two models:

### Baseline
LightGBM quantile model.

### Challenger
Temporal Fusion Transformer.

Features:

- recent rainfall
- rainfall anomaly
- ERA5 variables
- ONI
- IOD
- seasonal position

Predict:

> Remaining rainfall distribution.

### Evaluation

Use walk-forward validation only.

Metrics:

- CRPS
- calibration
- coverage
- quantile loss
- skill relative to climatology

Acceptance:

> Positive CRPS skill relative to climatology.

---

# 13. Phase 8 — Forecast-Conditioned Pricing

The forecast model should not replace the stochastic simulator.

Instead:

```text
Observed rainfall
      +
Forecast distribution
      +
Remaining-season simulator
      ↓
Forecast-conditioned payoff distribution
      ↓
Fair-value band
```

As the contract approaches expiry:

> uncertainty should normally shrink, but the system must not force monotonic uncertainty reduction if the data contradict it.

---

# 14. Phase 9 — Rainfall Greeks

Implement finite-difference sensitivities.

### Rainfall delta

```text
Δ = [V(rain + 10mm) - V(rain)] / 10mm
```

### Theta

```text
Θ = V(tomorrow) - V(today)
```

Display:

- current fair value
- delta
- theta
- uncertainty interval

Explain that these are model sensitivities, not necessarily exchange-standard Greeks.

---

# 15. Phase 10 — Hedge Optimiser

Input:

```text
loss exposure L
futures payoff X
```

Minimum-variance hedge:

```text
h* = Cov(L, X) / Var(X)
```

CVaR optimisation:

```text
min_h CVaR95(L - hX)
```

Constraints:

- 50-lot order cap
- margin requirement
- integer lots
- maximum notional

Output:

```json
{
  "recommended_lots_by_model": "...",
  "variance_reduction": "...",
  "cvar_reduction": "...",
  "residual_risk": "...",
  "basis_risk": "..."
}
```

For the public product, label these as **model-generated hedge quantities**, not personalised financial advice.

---

# 16. Phase 11 — Basis-Risk Analysis

For every grid cell in the city:

```text
local rainfall
      vs
contract index
```

Calculate:

- correlation
- RMSE
- tail mismatch
- seasonal mismatch

Produce:

> Basis-risk heatmap.

This is especially important because a weather derivative indexed to a station/grid may not perfectly hedge an individual business's local rainfall.

---

# 17. Phase 12 — Parametric Cover Designer

Inputs:

- exposure
- maximum premium/budget
- target protection period

Optimise:

- trigger
- exit/maximum payout
- payout slope

Objective:

> Minimise probability of loss without payout at the specified budget.

Case study:

> Chennai delivery-rider rainfall exposure hedged using RAINCHNNAI.

Keep the case study synthetic unless real exposure data is legitimately available.

---

# 18. Phase 13 — API

Core endpoints:

```text
GET  /health
GET  /contracts
GET  /index/{contract}
GET  /price/{contract}
GET  /greeks/{contract}
GET  /mpr/{contract}
GET  /forecast/{contract}
POST /hedge
POST /parametric/design
GET  /basis/{contract}
GET  /scenarios/{contract}
```

Every endpoint should have:

- Pydantic request/response schema
- OpenAPI documentation
- validation
- structured error messages
- model/data version
- timestamp

Example response:

```json
{
  "contract": "RAINCHNNAI",
  "fair_value": 1234.5,
  "lower_90": 1020.1,
  "upper_90": 1450.2,
  "model": "forecast_conditioned_v1",
  "data_version": "2026-12-15",
  "model_version": "v1.2.0"
}
```

---

# 19. Phase 14 — Dashboard

## Page 1 — Market Overview

Show:

- contract
- latest settlement
- volume
- open interest
- fair-value band
- premium/discount to model

## Page 2 — Pricing

Show:

- burn price
- distribution price
- stochastic price
- forecast-conditioned price

## Page 3 — Risk

Show:

- rainfall delta
- theta
- MPR
- payoff distribution

## Page 4 — Hedge

Interactive:

```text
Exposure
↓
Hedge model
↓
Lots
↓
Variance reduction
↓
Residual basis risk
```

## Page 5 — Research

Expose:

- methodology
- data sources
- assumptions
- limitations
- model versions

The methods page is a major part of the credibility of the project.

---

# 20. Phase 15 — Alerts

Implement only after the core system works.

Alerts:

```text
Fair-value divergence
Large forecast change
Extreme rainfall forecast
Pipeline failure
Model/data update
```

Channels:

- email
- Telegram

---

# 21. Testing Strategy

## Unit tests

Test:

- index formula
- payoff
- distribution fitting
- MPR transformation
- Greeks
- hedge formula
- CVaR
- basis calculations

## Golden tests

Create known examples where:

```text
input → expected index
input → expected payoff
input → expected fair value
```

## Property tests

Examples:

```text
No rainfall input should not produce negative rainfall.
More positive rainfall should affect the index consistently with the contract definition.
Hedge optimisation should not claim variance reduction when the calculated variance increased.
```

## Integration tests

```text
Data → model → API → dashboard
```

## Performance test

Benchmark:

> 1M simulation paths.

---

# 22. Quality Standards

Minimum engineering bar:

- Python typing
- mypy
- ruff
- clang-format
- pytest
- Hypothesis
- GitHub Actions
- Docker
- dependency scanning
- structured logs
- Sentry
- no secrets in source
- versioned data
- reproducible environments

Target:

> ≥80% coverage for pricing/risk engines.

---

# 23. Deployment

Suggested architecture:

```text
Vercel
  ↓
Next.js
  ↓
FastAPI
  ↓
AWS ECS / Render
  ↓
PostgreSQL
  +
S3/Parquet
```

Scheduled jobs:

```text
EventBridge
    ↓
Lambda / worker
    ↓
data ingestion
    ↓
models
    ↓
database
    ↓
dashboard
```

Target running cost:

> Keep the initial system within a small personal-project budget using free tiers/small instances where practical.

---

# 24. Exact 15-Week Build Schedule

| Week | Deliverable | Gate |
|---|---|---|
| 1 | Contract specification + ingestion + index | Daily data pipeline |
| 2 | Burn + distribution pricing | Two independent prices |
| 3 | C++ stochastic simulator | 1M paths benchmark |
| 4 | MPR calibration | First research note |
| 5 | Data quality + research dashboard | Reproducible pipeline |
| 6 | Forecast features + baseline | Walk-forward setup |
| 7 | Forecast challenger + calibration | CRPS comparison |
| 8 | Buffer / research validation | No new feature unless needed |
| 9 | Forecast-conditioned pricing | Fair-value interval |
| 10 | Greeks + hedge optimiser | Hedge case study |
| 11 | Basis-risk engine | Heatmap |
| 12 | Live Chennai-season evaluation | Out-of-sample results |
| 13 | Parametric designer + API | Public API |
| 14 | Production dashboard + alerts | Public deployment |
| 15 | Methods paper + demo + documentation | Launch |

---

# 25. Launch Checklist

## Research

- [ ] Contract specification archived
- [ ] Index replication validated
- [ ] Historical burn analysis
- [ ] Distribution comparison
- [ ] 1M-path stochastic engine
- [ ] MPR estimate with uncertainty
- [ ] Forecast benchmark
- [ ] Forecast-conditioned price
- [ ] Greeks
- [ ] Hedge optimisation
- [ ] Basis-risk analysis
- [ ] Live out-of-sample evaluation

## Engineering

- [ ] API deployed
- [ ] Dashboard deployed
- [ ] Automated ingestion
- [ ] Automated tests
- [ ] CI/CD
- [ ] Monitoring
- [ ] Data versioning
- [ ] Model versioning
- [ ] Documentation

## Research publication

- [ ] Methods document
- [ ] Reproducibility instructions
- [ ] Limitations section
- [ ] Preprint draft
- [ ] Results tables
- [ ] Figures

---

# 26. Final Portfolio Evidence

At launch, capture these exact artifacts:

1. Public dashboard.
2. GitHub repository.
3. Architecture diagram.
4. API documentation.
5. 1M-path performance benchmark.
6. MPR research figure.
7. Forecast-vs-climatology evaluation.
8. Hedge-effectiveness case study.
9. Basis-risk heatmap.
10. Methods paper/preprint.
11. 2-minute demo video.
12. One-page technical project summary.

The strongest CV evidence should use actual measured numbers rather than planned numbers.

Example structure:

> Built an open quantitative analytics platform for India's rainfall futures, combining stochastic rainfall simulation, derivative pricing, probabilistic forecasting, market-price-of-risk estimation, and CVaR hedge optimisation; validated the system on live out-of-sample contracts.

Only insert numerical claims after they have actually been measured.

---

# 27. Non-Negotiable Principles

1. **The pricing engine, not the LLM, owns financial calculations.**
2. **Every published number has a data/model version.**
3. **No backtest leakage.**
4. **Walk-forward evaluation for forecasting.**
5. **Uncertainty is shown rather than hidden.**
6. **Thin-market limitations are explicit.**
7. **Synthetic exposure is clearly labelled synthetic.**
8. **Research claims are proportional to sample size.**
9. **The public dashboard explains methodology.**
10. **The product should remain reproducible from a clean checkout.**

---

# 28. Definition of Done

MonsoonQuant is complete when a new user can:

```text
Open website
    ↓
Select RAINCHNNAI / RAINMUMBAI
    ↓
See current index + market price
    ↓
See multiple model fair values
    ↓
Understand the uncertainty
    ↓
Inspect forecast and rainfall sensitivities
    ↓
Run a synthetic exposure through the hedge optimiser
    ↓
See variance/CVaR reduction and basis risk
    ↓
Read the exact methodology and data provenance
    ↓
Reproduce the core research from GitHub
```

The final result should look like a **small quant research platform**, not a collection of notebooks.
