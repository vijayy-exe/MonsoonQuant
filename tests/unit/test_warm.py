from __future__ import annotations

from unittest.mock import patch

import requests

from mq.api.warm import _SERIES_PATHS, REAL_CONTRACTS, REAL_SERIES, warm_cache


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_warm_cache_hits_every_contract_and_series_path_exactly_once() -> None:
    with patch("mq.api.warm.requests.get", return_value=_FakeResponse(200)) as mock_get:
        results = warm_cache(base_url="http://example.test")

    expected_n = len(REAL_CONTRACTS) + len(REAL_SERIES) * len(_SERIES_PATHS)
    assert len(results) == expected_n
    assert mock_get.call_count == expected_n
    assert all(r.status_code == 200 and r.error is None for r in results)


def test_warm_cache_urls_target_the_given_base_url() -> None:
    with patch("mq.api.warm.requests.get", return_value=_FakeResponse(200)):
        results = warm_cache(base_url="http://example.test")

    assert all(r.url.startswith("http://example.test/v1/") for r in results)
    assert any("track-record?contract_code=RAINCHNNAI" in r.url for r in results)
    assert any(f"/series/{REAL_SERIES[0]}/basis" in r.url for r in results)


def test_warm_cache_records_a_request_failure_without_raising() -> None:
    with patch("mq.api.warm.requests.get", side_effect=requests.ConnectionError("refused")):
        results = warm_cache(base_url="http://example.test")

    assert len(results) > 0
    assert all(r.status_code is None and r.error == "refused" for r in results)
