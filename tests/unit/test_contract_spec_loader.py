from pathlib import Path

import pytest
import yaml

from mq.specs.loader import (
    DraftSpecRejectedError,
    find_pending_fields,
    is_draft,
    load_contract_spec,
)

DRAFT_RAINCHNNAI = Path("specs/contracts/RAINCHNNAI/2026-10-04-draft.yaml")


def _resolved_spec_dict() -> dict:
    return {
        "contract_code": "RAINCHNNAI",
        "spec_version": "2026-10-04",
        "stations": [
            {
                "station_id": "43279",
                "name": "Meenambakkam",
                "lat": 12.99,
                "lon": 80.18,
                "weight": 1.0,
            }
        ],
        "index": {
            "kind": "cumulative_rain_mm",
            "aggregation": "mean",
            "lpa": {
                "source_id": "imd_lpa_chennai",
                "base_period_start_year": 1971,
                "base_period_end_year": 2020,
            },
            "period_start": {"month": 10, "day": 1},
            "period_end": {"month": 12, "day": 31},
            "missing_data_rule": "carry forward last observed value",
        },
        "multiplier_inr_per_point": "5000",
        "tick_size": "0.1",
        "lot_size": 1,
        "max_order_lots": 50,
        "position_limit_lots": 500,
        "margin_pct": "10",
        "settlement": {"method": "cash vs official index", "timing": "T+1 after period end"},
        "source_ids": ["ncdex_spec_rainchnnai_2026"],
    }


def test_draft_yaml_fixture_exists_and_is_all_pending() -> None:
    assert DRAFT_RAINCHNNAI.exists()
    spec = load_contract_spec(DRAFT_RAINCHNNAI, allow_draft=True)
    assert is_draft(spec)


def test_draft_yaml_rejected_without_allow_draft() -> None:
    with pytest.raises(DraftSpecRejectedError) as excinfo:
        load_contract_spec(DRAFT_RAINCHNNAI, allow_draft=False)
    assert "stations" in str(excinfo.value)


def test_resolved_spec_is_not_draft(tmp_path: Path) -> None:
    f = tmp_path / "resolved.yaml"
    f.write_text(yaml.safe_dump(_resolved_spec_dict()))
    spec = load_contract_spec(f, allow_draft=False)  # must not raise
    assert not is_draft(spec)
    assert spec.contract_code == "RAINCHNNAI"


def test_partially_resolved_spec_reports_only_remaining_pending_fields(tmp_path: Path) -> None:
    data = _resolved_spec_dict()
    data["settlement"] = "TODO_VERIFY"
    f = tmp_path / "partial.yaml"
    f.write_text(yaml.safe_dump(data))

    with pytest.raises(DraftSpecRejectedError) as excinfo:
        load_contract_spec(f, allow_draft=False)
    assert excinfo.value.pending_fields == ["settlement"]

    spec = load_contract_spec(f, allow_draft=True)
    assert find_pending_fields(spec.model_dump(mode="json")) == ["settlement"]
