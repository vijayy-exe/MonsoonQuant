"""Parser unit tests against static fixtures captured from the real ONI/DMI/
MJO text formats — no live network calls, so these run offline and in CI."""

# ruff: noqa: E501 — fixtures below are verbatim slices of real data lines;
# wrapping them would no longer match what the parsers actually receive.

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from mq.pipelines.climate_idx import fetch_dmi, fetch_mjo, fetch_oni

ONI_FIXTURE = """ SEAS  YR   TOTAL   ANOM
  DJF 1950  25.01  -1.32
  JFM 1950  25.36  -1.20
  JAS 2026  29.12   2.16
"""

DMI_FIXTURE = """ 1870 2026
1870    -0.438    -0.337     0.177    -0.048    -0.480    -0.548    -0.650    -0.522    -0.728    -0.636    -0.401    -0.376
2026     0.123     0.529     0.285     0.279     0.146 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000
-9999
DMI HadISST1.1
Created Sat Jul 25 13:56:30 MDT 2026
"""

MJO_FIXTURE = """ RMM values up to "real time".
 year, month, day, RMM1, RMM2, phase, amplitude.  Missing Value= 1.E36 or 999
        1974           6           1   1.6344700       1.2030400               5   2.0294800      WH04_method
        2024           2          24 -3.14564817E-03  0.12845999               7  0.12849849      Gottschalk10_method
"""


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


def test_fetch_oni_parses_seasons_to_middle_month_dates() -> None:
    with patch("mq.pipelines.climate_idx.requests.get", return_value=_FakeResponse(ONI_FIXTURE)):
        df = fetch_oni(release_date=date(2026, 10, 4))
    assert df.height == 3
    assert df["date"].to_list() == [date(1950, 1, 15), date(1950, 2, 15), date(2026, 8, 15)]
    assert df["value"].to_list() == [-1.32, -1.20, 2.16]
    assert set(df["release_date"].to_list()) == {date(2026, 10, 4)}


def test_fetch_dmi_parses_monthly_grid_and_drops_missing_sentinel() -> None:
    with patch("mq.pipelines.climate_idx.requests.get", return_value=_FakeResponse(DMI_FIXTURE)):
        df = fetch_dmi(release_date=date(2026, 10, 4))
    # 1870 contributes 12 months; 2026 contributes only 5 (rest are -9999 sentinel)
    assert df.height == 17
    assert df.filter(df["date"] == date(1870, 1, 15))["value"].item() == -0.438
    assert df.filter(df["date"] == date(2026, 5, 15))["value"].item() == 0.146
    assert df.filter(df["date"] == date(2026, 6, 15)).height == 0


def test_fetch_mjo_parses_long_format_and_handles_scientific_notation() -> None:
    with patch("mq.pipelines.climate_idx.requests.get", return_value=_FakeResponse(MJO_FIXTURE)):
        df = fetch_mjo(release_date=date(2026, 10, 4))
    # 2 source rows x 4 sub-indices each
    assert df.height == 8
    assert set(df["index"].unique().to_list()) == {
        "mjo_rmm1",
        "mjo_rmm2",
        "mjo_phase",
        "mjo_amplitude",
    }
    rmm1_row = df.filter((df["index"] == "mjo_rmm1") & (df["date"] == date(2024, 2, 24)))
    assert rmm1_row["value"].item() == -3.14564817e-03
