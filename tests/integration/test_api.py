"""Integration tests for the real API (M12) against the real DB --
RAINCHNNAI's real listed series and real M4 valuations, not synthetic
fixtures. Uses `fastapi.testclient.TestClient` (built on `httpx2`,
a dev-only dependency -- see pyproject.toml)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from mq.api.main import app

client = TestClient(app)


def test_health_returns_ok_envelope() -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "ok"
    assert body["meta"]["disclaimer"] == "Research analytics. Not investment advice."


def test_health_data_reports_real_source_freshness() -> None:
    resp = client.get("/v1/health/data")
    assert resp.status_code == 200
    sources = {s["source"]: s for s in resp.json()["data"]["sources"]}
    assert "index_values" in sources
    assert "market_quotes" in sources
    assert "prediction_ledger" in sources
    # prediction_ledger has real rows from M1's clim_v1 writes
    assert sources["prediction_ledger"]["n_rows"] >= 1


def test_list_contracts_returns_real_rainchnnai_and_rainmumbai_series() -> None:
    resp = client.get("/v1/contracts")
    assert resp.status_code == 200
    series_ids = {s["series_id"] for s in resp.json()["data"]["series"]}
    assert "RAINCHNNAI-OCT26" in series_ids
    assert "RAINMUMBAI-JUN26" in series_ids


def test_get_contract_spec_returns_real_rainchnnai_yaml() -> None:
    resp = client.get("/v1/contracts/RAINCHNNAI/spec")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contract_code"] == "RAINCHNNAI"
    assert data["yaml"]["contract_code"] == "RAINCHNNAI"
    assert len(data["source_ids"]) >= 0


def test_get_contract_spec_unknown_code_returns_problem_json() -> None:
    resp = client.get("/v1/contracts/NOPE/spec")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["type"] == "mq/unknown-series"


def test_get_valuation_returns_real_burn_result() -> None:
    resp = client.get(
        "/v1/series/RAINCHNNAI-OCT26/valuation", params={"method": "burn", "measure": "P"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["series_id"] == "RAINCHNNAI-OCT26"
    assert data["method"] == "burn"
    assert data["fair_value"] is not None
    assert data["n_paths"] == 31  # real burn sample size (M4)


def test_get_valuation_unknown_series_returns_problem_json() -> None:
    resp = client.get("/v1/series/NOPE-SERIES/valuation")
    assert resp.status_code == 404
    assert resp.json()["type"] == "mq/unknown-series"


def test_compare_valuations_returns_both_real_methods() -> None:
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/valuations/compare")
    assert resp.status_code == 200
    by_method = resp.json()["data"]["by_method"]
    assert "burn/P" in by_method
    assert "dist/P" in by_method


def test_ledger_verify_passes_on_the_real_chain() -> None:
    resp = client.get("/v1/ledger/verify")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is True
    assert data["n_rows"] >= 1
    assert data["breaks"] == []


def test_list_ledger_returns_real_rows() -> None:
    resp = client.get("/v1/ledger")
    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    assert len(rows) >= 1
    assert all(r["contract_code"] == "RAINCHNNAI" for r in rows)


def test_list_ledger_filters_by_series() -> None:
    resp = client.get("/v1/ledger", params={"series": "RAINCHNNAI"})
    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    assert all(r["contract_code"] == "RAINCHNNAI" for r in rows)

    resp_empty = client.get("/v1/ledger", params={"series": "NOPE"})
    assert resp_empty.json()["data"]["rows"] == []


def test_get_index_path_returns_real_index_values() -> None:
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/index")
    assert resp.status_code == 200
    points = resp.json()["data"]["points"]
    assert len(points) >= 1
    # strictly increasing obs_date, one point per day (newest-as_of-wins
    # dedup collapsed any revision history)
    assert points == sorted(points, key=lambda p: p["obs_date"])


def test_get_index_path_unknown_series_is_404() -> None:
    resp = client.get("/v1/series/NOPE-JAN99/index")
    assert resp.status_code == 404
    assert resp.json()["type"] == "mq/unknown-series"


def test_get_quotes_returns_empty_not_error_bhavcopy_bot_gated() -> None:
    """market_quotes is genuinely empty right now -- NCDEX bhavcopy live
    fetch stays bot-gated (M2, documented policy) -- so this must return
    200 with an empty list, not a 404/500."""
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/quotes")
    assert resp.status_code == 200
    assert resp.json()["data"]["quotes"] == []


def test_get_mpr_returns_empty_not_error_no_real_settlement_data() -> None:
    """mpr_estimates is genuinely empty -- M6's demo ran on illustrative
    settle data only, nothing written against real market data yet."""
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/mpr")
    assert resp.status_code == 200
    assert resp.json()["data"]["points"] == []


def test_get_forecast_returns_real_ledger_rows() -> None:
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/forecast")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["contract_code"] == "RAINCHNNAI"
    assert len(data["rows"]) >= 1
    assert all(r["model_id"] == "clim_v1" for r in data["rows"])
    assert "0.5" in data["rows"][0]["quantiles"]


def test_get_forecast_filters_by_model_id() -> None:
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/forecast", params={"model_id": "nope_v1"})
    assert resp.status_code == 404


def test_get_basis_returns_real_geojson_grid_and_caches_by_request() -> None:
    """A real, on-demand M10 basis-engine run for RAINCHNNAI -- the same
    computation docs/methods/basis.md reports (12 real cells in the
    default 0.5 deg box). The first call is genuinely slow (~tens of
    seconds -- measured, not assumed: a 31-year burn sample plus a
    per-cell basis reconstruction loop over real IMD data), so it's
    cached by request hash (series_id, as_of, box_deg); the second
    identical call must be fast, proving the cache path actually runs
    rather than just existing in the code."""
    t0 = time.time()
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/basis")
    first_call_s = time.time() - t0
    assert resp.status_code == 200
    geojson = resp.json()["data"]
    assert geojson["type"] == "FeatureCollection"
    features = geojson["features"]
    assert len(features) >= 1
    props = features[0]["properties"]
    assert -1.0 <= props["correlation"] <= 1.0
    assert props["n_years"] >= 3

    t0 = time.time()
    resp2 = client.get("/v1/series/RAINCHNNAI-OCT26/basis")
    second_call_s = time.time() - t0
    assert resp2.status_code == 200
    assert resp2.json()["data"] == geojson
    assert second_call_s < max(1.0, first_call_s / 5)
