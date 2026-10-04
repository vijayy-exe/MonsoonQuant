"""SQLAlchemy ORM models for the core tables defined in SPEC §6.1.

These are metadata/ledger/valuation tables only — bulk time-series (gridded
rain, features) live in Parquet+DuckDB per §6.2, not here.
"""

from __future__ import annotations

import uuid
from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ARRAY, BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date_ | None] = mapped_column(Date)
    effective_at: Mapped[date_ | None] = mapped_column(Date)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    licence: Mapped[str | None] = mapped_column(Text)


class RawFile(Base):
    __tablename__ = "raw_files"

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)


class ContractSpecRow(Base):
    __tablename__ = "contract_specs"

    contract_code: Mapped[str] = mapped_column(Text, primary_key=True)
    spec_version: Mapped[str] = mapped_column(Text, primary_key=True)
    yaml: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)


class Contract(Base):
    __tablename__ = "contracts"

    series_id: Mapped[str] = mapped_column(Text, primary_key=True)
    contract_code: Mapped[str | None] = mapped_column(Text)
    spec_version: Mapped[str | None] = mapped_column(Text)
    period_start: Mapped[date_ | None] = mapped_column(Date)
    period_end: Mapped[date_ | None] = mapped_column(Date)
    expiry: Mapped[date_ | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(Text)


class MarketQuote(Base):
    __tablename__ = "market_quotes"

    series_id: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_date: Mapped[date_] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric)
    high: Mapped[Decimal | None] = mapped_column(Numeric)
    low: Mapped[Decimal | None] = mapped_column(Numeric)
    close: Mapped[Decimal | None] = mapped_column(Numeric)
    settle: Mapped[Decimal | None] = mapped_column(Numeric)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    open_interest: Mapped[int | None] = mapped_column(BigInteger)
    raw_sha256: Mapped[str | None] = mapped_column(Text, ForeignKey("raw_files.sha256"))
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexValue(Base):
    __tablename__ = "index_values"

    series_id: Mapped[str] = mapped_column(Text, primary_key=True)
    obs_date: Mapped[date_] = mapped_column(Date, primary_key=True)
    as_of_date: Mapped[date_] = mapped_column(Date, primary_key=True)
    proxy_value: Mapped[Decimal | None] = mapped_column(Numeric)
    official_value: Mapped[Decimal | None] = mapped_column(Numeric)
    abs_error: Mapped[Decimal | None] = mapped_column(Numeric)
    pct_lpa_error: Mapped[Decimal | None] = mapped_column(Numeric)
    data_version: Mapped[str | None] = mapped_column(Text)


class ModelRun(Base):
    __tablename__ = "model_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    data_version: Mapped[str | None] = mapped_column(Text)
    spec_version: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    git_sha: Mapped[str | None] = mapped_column(Text)
    mlflow_run: Mapped[str | None] = mapped_column(Text)


class Valuation(Base):
    __tablename__ = "valuations"

    series_id: Mapped[str] = mapped_column(Text, primary_key=True)
    as_of_date: Mapped[date_] = mapped_column(Date, primary_key=True)
    method: Mapped[str] = mapped_column(Text, primary_key=True)
    measure: Mapped[str] = mapped_column(Text, primary_key=True)
    fair_value: Mapped[Decimal | None] = mapped_column(Numeric)
    lo90: Mapped[Decimal | None] = mapped_column(Numeric)
    hi90: Mapped[Decimal | None] = mapped_column(Numeric)
    n_paths: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_runs.run_id")
    )


class MPREstimate(Base):
    __tablename__ = "mpr_estimates"

    series_id: Mapped[str] = mapped_column(Text, primary_key=True)
    as_of_date: Mapped[date_] = mapped_column(Date, primary_key=True)
    transform: Mapped[str] = mapped_column(Text, primary_key=True)
    lambda_: Mapped[Decimal | None] = mapped_column("lambda", Numeric)
    ci_lo: Mapped[Decimal | None] = mapped_column(Numeric)
    ci_hi: Mapped[Decimal | None] = mapped_column(Numeric)
    method_ci: Mapped[str | None] = mapped_column(Text)
    days_to_expiry: Mapped[int | None] = mapped_column(Integer)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    open_interest: Mapped[int | None] = mapped_column(BigInteger)
    n_obs: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_runs.run_id")
    )


class DQResult(Base):
    __tablename__ = "dq_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    check_id: Mapped[str | None] = mapped_column(Text)
    dataset: Mapped[str | None] = mapped_column(Text)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PredictionLedgerRow(Base):
    """Append-only, hash-chained forecast record (SPEC §2.1).

    UPDATE/DELETE on this table are blocked at the database level by a
    trigger installed in the same migration that creates it — see
    migrations/versions/0001_initial_schema.py.
    """

    __tablename__ = "prediction_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_date: Mapped[date_] = mapped_column(Date, nullable=False)
    contract_code: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    data_version: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    quantiles: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fair_value: Mapped[Decimal | None] = mapped_column(Numeric)
    fair_value_lo90: Mapped[Decimal | None] = mapped_column(Numeric)
    fair_value_hi90: Mapped[Decimal | None] = mapped_column(Numeric)
    payload_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
