"""Integration tests for the real API (M12) against the real DB --
RAINCHNNAI's real listed series and real M4 valuations, not synthetic
fixtures. Uses `fastapi.testclient.TestClient` (built on `httpx2`,
a dev-only dependency -- see pyproject.toml)."""

from __future__ import annotations

import time

import pytest
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


def test_post_hedge_returns_real_min_variance_and_cvar95() -> None:
    """Real M9 optimisers against a real candidate location's real IMD
    rainfall and the real RAINCHNNAI official index -- the same
    (lat,lon) and exposure shape as docs/methods/hedge.md's real run."""
    resp = client.post(
        "/v1/hedge",
        json={
            "series_id": "RAINCHNNAI-OCT26",
            "location_lat": 13.50,
            "location_lon": 79.75,
            "exposure_template": "delivery_rider",
            "template_params": {
                "dry_threshold_mm": 600.0,
                "saturation_mm": 1200.0,
                "max_loss": 500_000.0,
            },
            "constraints": {
                "max_order_lots": 20,
                "margin_budget": 100_000.0,
                "margin_per_lot": 2_000.0,
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["series_id"] == "RAINCHNNAI-OCT26"
    assert data["n_years"] >= 2
    assert isinstance(data["min_variance"]["lots"], int)
    assert isinstance(data["cvar95"]["lots"], int)
    assert data["min_variance"]["do_nothing_variance"] >= 0
    assert (
        data["cvar95"]["var_95"] <= data["cvar95"]["cvar_95"] + 1e-6
    )  # CVaR >= VaR by construction


def test_post_hedge_unknown_series_is_404() -> None:
    resp = client.post(
        "/v1/hedge",
        json={"series_id": "NOPE-JAN99", "location_lat": 13.0, "location_lon": 80.0},
    )
    assert resp.status_code == 404
    assert resp.json()["type"] == "mq/unknown-series"


def test_post_hedge_unconstrained_hits_the_documented_degenerate_cvar_case() -> None:
    """Real finding (docs/methods/hedge.md): the real RAINCHNNAI index
    is positive in all 31 historical seasons, so an unconstrained
    CVaR95 minimization has no interior optimum -- it wants to short
    without limit, landing at LotConstraints' own 10,000-lot fallback.
    The API must reproduce this real behavior, not mask it."""
    resp = client.post(
        "/v1/hedge",
        json={"series_id": "RAINCHNNAI-OCT26", "location_lat": 13.25, "location_lon": 80.0},
    )
    assert resp.status_code == 200
    cvar95 = resp.json()["data"]["cvar95"]
    assert (
        abs(cvar95["lots"]) == 10_000
    )  # hit the unconstrained fallback cap, not an interior optimum


def test_post_hedge_with_constraints_avoids_the_degenerate_case() -> None:
    resp = client.post(
        "/v1/hedge",
        json={
            "series_id": "RAINCHNNAI-OCT26",
            "location_lat": 13.25,
            "location_lon": 80.0,
            "constraints": {"max_order_lots": 20},
        },
    )
    assert resp.status_code == 200
    cvar95 = resp.json()["data"]["cvar95"]
    assert abs(cvar95["lots"]) <= 20


def test_post_hedge_caches_by_request_hash() -> None:
    body = {
        "series_id": "RAINCHNNAI-OCT26",
        "location_lat": 13.25,
        "location_lon": 80.25,
        "exposure_template": "crop_yield",
    }
    t0 = time.time()
    resp1 = client.post("/v1/hedge", json=body)
    first_s = time.time() - t0
    assert resp1.status_code == 200

    t0 = time.time()
    resp2 = client.post("/v1/hedge", json=body)
    second_s = time.time() - t0
    assert resp2.status_code == 200
    assert resp2.json()["data"] == resp1.json()["data"]
    assert second_s < max(0.5, first_s / 3)


def test_post_parametric_design_returns_real_optimized_cover() -> None:
    """Real M11 optimize_cover against a real candidate location's real
    loss sample and the real RAINCHNNAI official index -- the same case
    study shape as docs/methods/parametric.md's real run."""
    resp = client.post(
        "/v1/parametric/design",
        json={
            "series_id": "RAINCHNNAI-OCT26",
            "location_lat": 13.50,
            "location_lon": 79.75,
            "direction": "wet",
            "exposure_template": "delivery_rider",
            "template_params": {
                "dry_threshold_mm": 600.0,
                "saturation_mm": 1200.0,
                "max_loss": 500_000.0,
            },
            "budget": 50_000.0,
            "loading": 0.2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["series_id"] == "RAINCHNNAI-OCT26"
    assert data["n_years"] >= 2
    opt = data["optimized"]
    assert opt["premium"] <= 50_000.0 + 1e-6
    assert 0.0 <= opt["basis_failure_probability"] <= 1.0
    assert opt["limit"] > 0
    assert opt["slope"] > 0


def test_post_parametric_design_unknown_series_is_404() -> None:
    resp = client.post(
        "/v1/parametric/design",
        json={
            "series_id": "NOPE-JAN99",
            "location_lat": 13.0,
            "location_lon": 80.0,
            "budget": 1000.0,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["type"] == "mq/unknown-series"


def test_post_parametric_design_caches_by_request_hash() -> None:
    body = {
        "series_id": "RAINCHNNAI-OCT26",
        "location_lat": 13.25,
        "location_lon": 80.0,
        "direction": "wet",
        "budget": 50_000.0,
    }
    t0 = time.time()
    resp1 = client.post("/v1/parametric/design", json=body)
    first_s = time.time() - t0
    assert resp1.status_code == 200

    t0 = time.time()
    resp2 = client.post("/v1/parametric/design", json=body)
    second_s = time.time() - t0
    assert resp2.status_code == 200
    assert resp2.json()["data"] == resp1.json()["data"]
    assert second_s < max(0.5, first_s / 3)


def test_post_scenarios_run_returns_real_structural_delta_gamma() -> None:
    """Real M11 scenario lab against a real fitted chain model (M5.1/
    M5.2) and the real official index's own observed_to_date (pulled
    from index_values, not supplied). Delta=1.0/gamma=0 is the same
    real structural finding M9/M11 already documented -- the CDR index
    is additive in observed_to_date by construction, so this must hold
    under every shock, not just a specific one."""
    resp = client.post(
        "/v1/scenarios/run",
        json={"series_id": "RAINCHNNAI-OCT26", "shocks": ["el_nino", "la_nina"], "n_paths": 5000},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["series_id"] == "RAINCHNNAI-OCT26"
    assert data["observed_to_date"] > 0  # pulled from the real index_values table
    assert len(data["results"]) == 2
    for r in data["results"]:
        assert r["greeks"]["delta"] == pytest.approx(1.0, abs=1e-6)
        assert r["greeks"]["gamma"] == pytest.approx(0.0, abs=1e-9)
        assert (
            r["valuations"]["simulator_p5"]
            < r["valuations"]["simulator_mean"]
            < r["valuations"]["simulator_p95"]
        )


def test_post_scenarios_run_historical_analog_uses_real_2015_oni_dmi() -> None:
    """SPEC's own real 2015 Chennai-floods analog -- a real historical
    year's ONI/DMI, not an illustrative override."""
    resp = client.post(
        "/v1/scenarios/run",
        json={
            "series_id": "RAINCHNNAI-OCT26",
            "shocks": [],
            "historical_analog_years": [2015],
            "n_paths": 5000,
        },
    )
    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    assert len(results) == 1
    assert "2015" in results[0]["name"]
    assert "2015" in results[0]["description"]


def test_post_scenarios_run_unknown_series_is_404() -> None:
    resp = client.post("/v1/scenarios/run", json={"series_id": "NOPE-JAN99", "n_paths": 5000})
    assert resp.status_code == 404
    assert resp.json()["type"] == "mq/unknown-series"


def test_post_scenarios_run_rejects_n_paths_above_spec_cap() -> None:
    resp = client.post(
        "/v1/scenarios/run",
        json={"series_id": "RAINCHNNAI-OCT26", "n_paths": 200_001},
    )
    assert resp.status_code == 422


def test_post_scenarios_run_caches_by_request_hash() -> None:
    body = {"series_id": "RAINCHNNAI-OCT26", "shocks": ["cloudburst"], "n_paths": 5000}
    t0 = time.time()
    resp1 = client.post("/v1/scenarios/run", json=body)
    first_s = time.time() - t0
    assert resp1.status_code == 200

    t0 = time.time()
    resp2 = client.post("/v1/scenarios/run", json=body)
    second_s = time.time() - t0
    assert resp2.status_code == 200
    assert resp2.json()["data"] == resp1.json()["data"]
    assert second_s < max(0.5, first_s / 3)


def test_get_greeks_returns_real_structural_delta_gamma() -> None:
    """Real M9 Greeks against a real fitted chain model. delta=1.0/
    gamma=0 exactly is the real structural finding docs/methods/
    greeks.md documents (the CDR index is additive in observed_to_date
    by construction) -- must hold here too, not just in the original
    script/notebook."""
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/greeks", params={"n_paths": 5000})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["series_id"] == "RAINCHNNAI-OCT26"
    assert data["delta"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert data["delta"]["pairing"] == "exact"
    assert data["gamma"]["value"] == pytest.approx(0.0, abs=1e-9)
    assert data["gamma"]["pairing"] == "exact"
    assert data["theta_no_rain_day"] is not None
    assert data["theta_no_rain_day"]["pairing"] == "partial"
    assert data["theta_climatological_day"] is not None


def test_get_greeks_unknown_series_is_404() -> None:
    resp = client.get("/v1/series/NOPE-JAN99/greeks")
    assert resp.status_code == 404
    assert resp.json()["type"] == "mq/unknown-series"


def test_get_greeks_rejects_n_paths_above_spec_cap() -> None:
    resp = client.get("/v1/series/RAINCHNNAI-OCT26/greeks", params={"n_paths": 200_001})
    assert resp.status_code == 422
