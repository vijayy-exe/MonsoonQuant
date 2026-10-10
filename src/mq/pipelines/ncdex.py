"""NCDEX market-data ingestion — UDiFF Final Bhav Copy (SPEC F02, §6.1
`market_quotes`), scoped to RAINCHNNAI/RAINMUMBAI.

**Live automated download is blocked.** ncdex.com's market-data page is a
JS app whose API (`/api/bhavcopy`) sits behind a fingerprint/bot-detection
challenge (`Fingerprint.start("/__verify/fp", ...)`) — the same category of
block as BoM/MJO (see docs/DECISIONS.md), and not worked around for the
same reason: scripting past an explicit anti-bot control isn't something
to do quietly. A real browser session passes this challenge legitimately
(not available in this environment); until then, this module ingests a
bhavcopy CSV downloaded manually through the website.

Column layout: NCDEX "Consolidated File format for Trading Members",
Final Bhav Copy (UDiFF format with ISO tags), registered as
`ncdex_udiff_bhavcopy_format_2024`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from mq.db.models import MarketQuote, RawFile
from mq.db.session import session_scope
from mq.pipelines.dq import (
    DQCheckResult,
    DQGateFailedError,
    dq02_duplicate_keys,
    dq05_stale_market_data,
    dq06_unknown_contract_code,
    dq10_settle_outside_price_band,
    gate,
    persist_results,
)
from mq.specs.sources import sha256_of

KNOWN_CONTRACT_CODES = {"RAINCHNNAI", "RAINMUMBAI"}

RAW_DIR = Path("data/raw/ncdex/bhavcopy")

# NCDEX UDiFF Final Bhav Copy columns (source: ncdex_udiff_bhavcopy_format_2024, p.8-9).
# "FininstrmActlXpryDt" (lowercase i in "nstrm") is NCDEX's own real
# column name, confirmed against a real downloaded bhavcopy CSV
# (2026-10-11) -- differs from the documented spec's "FinInstrmActlXpryDt"
# casing, not used by to_market_quotes() so harmless either way, kept
# matching the real file rather than the written spec.
BHAVCOPY_SCHEMA: dict[str, pl.DataType] = {
    "TradDt": pl.String(),
    "BizDt": pl.String(),
    "Sgmt": pl.String(),
    "Src": pl.String(),
    "FinInstrmTp": pl.String(),
    "FinInstrmId": pl.Int64(),
    "ISIN": pl.String(),
    "TckrSymb": pl.String(),
    "SctySrs": pl.String(),
    "XpryDt": pl.String(),
    "FininstrmActlXpryDt": pl.String(),
    "StrkPric": pl.Float64(),
    "OptnTp": pl.String(),
    "FinInstrmNm": pl.String(),
    "OpnPric": pl.Float64(),
    "HghPric": pl.Float64(),
    "LwPric": pl.Float64(),
    "ClsPric": pl.Float64(),
    "LastPric": pl.Float64(),
    "PrvsClsgPric": pl.Float64(),
    "UndrlygPric": pl.Float64(),
    "SttlmPric": pl.Float64(),
    "OpnIntrst": pl.Int64(),
    "ChngInOpnIntrst": pl.Int64(),
    "TtlTradgVol": pl.Int64(),
    "TtlTrfVal": pl.Float64(),
    "TtlNbOfTxsExctd": pl.Int64(),
    "SsnId": pl.String(),
    "NewBrdLotQty": pl.Int64(),
    "Rmks": pl.String(),
    "Rsvd1": pl.String(),
    "Rsvd2": pl.String(),
    "Rsvd3": pl.String(),
    "Rsvd4": pl.String(),
}

MARKET_QUOTES_COLUMNS = [
    "series_id",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "settle",
    "volume",
    "open_interest",
]


def parse_bhavcopy(csv_path: Path) -> pl.DataFrame:
    """Parse a UDiFF Final Bhav Copy CSV into the documented 34-column
    schema (all instruments/commodities, not yet filtered)."""
    return pl.read_csv(csv_path, schema_overrides=BHAVCOPY_SCHEMA)


def _series_id(ticker: str, expiry_iso: str) -> str:
    expiry = datetime.strptime(expiry_iso, "%Y-%m-%d").date()
    return f"{ticker}-{expiry.strftime('%b%y').upper()}"


def to_market_quotes(df: pl.DataFrame) -> pl.DataFrame:
    """Filter to RAINCHNNAI/RAINMUMBAI rows and normalise to the
    `market_quotes` schema (SPEC §6.1)."""
    filtered = df.filter(pl.col("TckrSymb").is_in(list(KNOWN_CONTRACT_CODES)))
    if filtered.is_empty():
        empty_schema = {
            "series_id": pl.String(),
            "trade_date": pl.Date(),
            "open": pl.Float64(),
            "high": pl.Float64(),
            "low": pl.Float64(),
            "close": pl.Float64(),
            "settle": pl.Float64(),
            "volume": pl.Int64(),
            "open_interest": pl.Int64(),
        }
        return pl.DataFrame(schema=empty_schema)

    out = filtered.with_columns(
        (
            pl.struct(["TckrSymb", "XpryDt"]).map_elements(
                lambda s: _series_id(s["TckrSymb"], s["XpryDt"]), return_dtype=pl.String()
            )
        ).alias("series_id"),
        pl.col("TradDt").str.strptime(pl.Date, "%Y-%m-%d").alias("trade_date"),
        pl.col("OpnPric").alias("open"),
        pl.col("HghPric").alias("high"),
        pl.col("LwPric").alias("low"),
        pl.col("ClsPric").alias("close"),
        pl.col("SttlmPric").alias("settle"),
        pl.col("TtlTradgVol").alias("volume"),
        pl.col("OpnIntrst").alias("open_interest"),
    )
    return out.select(MARKET_QUOTES_COLUMNS)


def run_market_quotes_dq(
    df: pl.DataFrame, raw_df: pl.DataFrame, *, as_of: date, dataset: str
) -> list[DQCheckResult]:
    results = [
        dq02_duplicate_keys(df, key_cols=["series_id", "trade_date"], dataset=dataset),
        dq05_stale_market_data(df, date_col="trade_date", dataset=dataset, as_of=as_of),
        dq06_unknown_contract_code(
            raw_df, code_col="TckrSymb", dataset=dataset, known_codes=KNOWN_CONTRACT_CODES
        ),
    ]
    if df.height >= 2:
        sorted_df = df.sort(["series_id", "trade_date"])
        with_prev = sorted_df.with_columns(
            pl.col("settle").shift(1).over("series_id").alias("prev_settle")
        )
        with_prev = with_prev.filter(pl.col("prev_settle").is_not_null())
        if with_prev.height > 0:
            results.append(
                dq10_settle_outside_price_band(
                    with_prev, settle_col="settle", prev_settle_col="prev_settle", dataset=dataset
                )
            )
    return results


def write_market_quotes(csv_path: Path, *, as_of: date, raw_dir: Path = RAW_DIR) -> int:
    """Ingest one bhavcopy CSV: hash it immutably, parse, filter to the two
    rainfall contracts, run the DQ gate, and upsert into `market_quotes`.
    Returns the number of rows written. Raises if the gate fails (nothing
    is written in that case, but the DQ results are still persisted)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_of(csv_path)
    stored_path = raw_dir / f"{digest}.csv"
    if not stored_path.exists():
        stored_path.write_bytes(csv_path.read_bytes())

    raw_df = parse_bhavcopy(csv_path)
    quotes = to_market_quotes(raw_df)
    dataset = f"market_quotes:ncdex:{as_of.isoformat()}"

    results = run_market_quotes_dq(quotes, raw_df, as_of=as_of, dataset=dataset)
    persist_results(results)
    if not gate(results):
        raise DQGateFailedError([r for r in results if r.status == "fail"])

    if quotes.is_empty():
        return 0

    now = datetime.now(UTC)
    with session_scope() as session:
        session.merge(
            RawFile(
                sha256=digest,
                source_name="ncdex_bhavcopy",
                url=None,
                fetched_at=now,
                bytes=csv_path.stat().st_size,
                object_key=str(stored_path),
            )
        )
        for row in quotes.iter_rows(named=True):
            session.merge(
                MarketQuote(
                    series_id=row["series_id"],
                    trade_date=row["trade_date"],
                    open=Decimal(str(row["open"])) if row["open"] is not None else None,
                    high=Decimal(str(row["high"])) if row["high"] is not None else None,
                    low=Decimal(str(row["low"])) if row["low"] is not None else None,
                    close=Decimal(str(row["close"])) if row["close"] is not None else None,
                    settle=Decimal(str(row["settle"])) if row["settle"] is not None else None,
                    volume=row["volume"],
                    open_interest=row["open_interest"],
                    raw_sha256=digest,
                    ingested_at=now,
                )
            )
    return quotes.height
