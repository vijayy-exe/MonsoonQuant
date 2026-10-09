"""The real daily pipeline orchestration (SPEC §8.1's DAG) -- `mq run
daily` / `make ingest`. Before this, `make ingest` called a CLI command
that didn't exist at all (the same class of gap `make reproduce` had,
fixed in M15) -- this wires together every already-built, real piece
(IMD real-time fetch, ONI/DMI fetch, the index engine, and the 4 newer
forecasting rungs' live ledger write) into one idempotent command.

What this deliberately does NOT do, and why:
- NCDEX bhavcopy fetch: bot-gated (M2, docs/STATUS.md) -- skipped, not
  attempted, every run.
- MJO fetch: BoM bot-gates this network too, and SPEC §3.1 itself calls
  MJO the lowest-priority of the three climate drivers for the NE
  monsoon -- skipped, not attempted.
- `clim_v1`'s own live write: its first real ledger rows (M1) used a
  specific single-station reference cell decided ad hoc in a scratch
  script, never committed to source. Writing new rows here would mean
  guessing that decision -- "never modify ledger rows... without
  asking" (CLAUDE.md) extends to not silently inventing how its
  *future* rows get produced either (the same call M7's live-row work
  already made for the 4 newer rungs). Left alone; revisit explicitly
  if wanted.
- Export to a public git mirror: no GitHub remote exists (explicit,
  standing decision -- see docs/STATUS.md).

Each step is independent and recorded in the returned report rather
than raising -- a DQ-gate failure on one dataset (e.g. a bad IMD fetch)
is logged and the run continues, except where a later step structurally
needs an earlier one's output (index/forecast writing needs a fresh
rain_grid read)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import polars as pl
from sqlalchemy import select

from mq.api.common import (
    BASIS_YEARS,
    load_climate_idx,
    load_combined_rain_grid,
    load_resolved_spec,
)
from mq.db.models import Contract
from mq.db.session import session_scope
from mq.forecasting.live import build_live_forecasts
from mq.index.engine import compute_index
from mq.index.writer import write_index_values
from mq.ledger.writer import write_forecast
from mq.pipelines.climate_idx import fetch_dmi, fetch_oni, write_climate_idx
from mq.pipelines.dq import DQGateFailedError, dq09_proxy_index_jump, persist_results
from mq.pipelines.imd import write_rain_grid_realtime

REAL_CONTRACT_CODES = ["RAINCHNNAI", "RAINMUMBAI"]


@dataclass(frozen=True)
class StepResult:
    name: str
    status: str  # "ok" | "skipped" | "failed"
    detail: str = ""


@dataclass
class DailyRunReport:
    as_of: date
    steps: list[StepResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append(StepResult(name=name, status=status, detail=detail))

    @property
    def ok(self) -> bool:
        return all(s.status != "failed" for s in self.steps)


def _active_series_ids(contract_code: str) -> list[str]:
    with session_scope() as session:
        rows = (
            session.execute(
                select(Contract.series_id).where(
                    Contract.contract_code == contract_code, Contract.status == "active"
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


def run_daily(as_of: date | None = None) -> DailyRunReport:
    """SPEC §8.1's daily DAG, scoped to what's actually real (see module
    docstring)."""
    effective_as_of = as_of or datetime.now(UTC).date()
    report = DailyRunReport(as_of=effective_as_of)

    rain_grid_ok = True
    try:
        write_rain_grid_realtime(effective_as_of, effective_as_of)
        report.add("fetch_imd_realtime", "ok")
    except DQGateFailedError as exc:
        rain_grid_ok = False
        report.add("fetch_imd_realtime", "failed", str(exc))

    try:
        write_climate_idx(
            pl.concat(
                [fetch_oni(release_date=effective_as_of), fetch_dmi(release_date=effective_as_of)]
            )
        )
        report.add("fetch_climate_idx", "ok")
    except DQGateFailedError as exc:
        report.add("fetch_climate_idx", "failed", str(exc))

    report.add("fetch_mjo", "skipped", "BoM bot-gates this network (SPEC §3.1: lowest priority)")
    report.add(
        "fetch_ncdex_bhavcopy", "skipped", "ncdex.com bot-gates this network (docs/STATUS.md M2)"
    )
    report.add(
        "write_clim_v1_live",
        "skipped",
        "reference cell never committed to source; see module docstring",
    )
    report.add("export_to_git", "skipped", "no public GitHub remote configured")

    if not rain_grid_ok:
        report.add(
            "compute_index", "skipped", "fetch_imd_realtime failed, no fresh rain_grid to use"
        )
        report.add("write_live_forecasts", "skipped", "fetch_imd_realtime failed")
        return report

    rain_grid = load_combined_rain_grid(effective_as_of)
    climate_idx = load_climate_idx(effective_as_of)
    data_version = (
        f"imd-1991-2020-full-plus-2023_n{len(BASIS_YEARS)}_asof-{effective_as_of.isoformat()}"
    )

    for contract_code in REAL_CONTRACT_CODES:
        series_ids = _active_series_ids(contract_code)
        if not series_ids:
            report.add(f"compute_index:{contract_code}", "skipped", "no active listed series today")
            report.add(
                f"write_live_forecasts:{contract_code}", "skipped", "no active listed series today"
            )
            continue

        try:
            with session_scope() as session:
                spec = load_resolved_spec(session, series_ids[0], contract_code)
            path = compute_index(spec, rain_grid, effective_as_of)
        except ValueError as exc:
            report.add(f"compute_index:{contract_code}", "failed", str(exc))
            report.add(f"write_live_forecasts:{contract_code}", "skipped", "compute_index failed")
            continue

        jump_check = dq09_proxy_index_jump(
            pl.DataFrame({"deviation_mm": path.daily_deviation_mm}),
            value_col="deviation_mm",
            dataset=f"index_values:{contract_code}",
        )
        persist_results([jump_check])
        write_index_values(path, series_ids=series_ids, data_version=data_version)
        report.add(
            f"compute_index:{contract_code}",
            "ok",
            f"observed_to_date={path.observed_to_date:.1f}mm, DQ09={jump_check.status}",
        )

        try:
            forecasts = build_live_forecasts(
                spec,
                rain_grid,
                climate_idx,
                historical_years=BASIS_YEARS,
                as_of=effective_as_of,
                data_version=data_version,
            )
        except ValueError as exc:
            report.add(f"write_live_forecasts:{contract_code}", "failed", str(exc))
            continue

        written = [write_forecast(f) for f in forecasts]
        n_written = sum(1 for w in written if w is not None)
        report.add(
            f"write_live_forecasts:{contract_code}",
            "ok",
            f"{n_written}/{len(forecasts)} new rows (rest already in ledger today)",
        )

    return report
