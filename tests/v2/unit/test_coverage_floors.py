from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from cse_financial_etl.v2.exceptions import UnauthorizedCoverageFloorReduction
from cse_financial_etl.v2.governance.coverage_floors import (
    REQUIRED_GOVERNANCE_FIELDS,
    assert_coverage_floors_not_lowered,
    evaluate_coverage_floors,
    historical_lock_payload,
    load_yaml_mapping,
)
from cse_financial_etl.v2.governance.historical_floors import (
    HISTORICAL_MIN_DRAFT_PUBLISHABLE,
    HISTORICAL_MIN_EXTRACTED_PLUS_DERIVED,
    HISTORICAL_MIN_PUBLISHABLE_BY_METRIC,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _complete_governance(*, path: str, old_value: int, new_value: int) -> dict[str, object]:
    return {
        "path": path,
        "old_value": old_value,
        "new_value": new_value,
        "affected_metrics": ["ALL"],
        "affected_sectors": ["ALL"],
        "reason": "documented incident",
        "incident_id": "INC-TEST",
        "source_snapshot_id": "snap-test",
        "reference_run_id": "ref-test",
        "new_run_id": "new-test",
        "code_sha": "deadbeef",
        "evidence": "fixture",
        "ACKNOWLEDGED_REGRESSION": True,
        "approver": "test-approver",
    }


def test_historical_lock_is_the_accepted_8924_floor() -> None:
    assert HISTORICAL_MIN_DRAFT_PUBLISHABLE == 8924
    assert HISTORICAL_MIN_EXTRACTED_PLUS_DERIVED == 8932
    assert HISTORICAL_MIN_PUBLISHABLE_BY_METRIC["PAT"] == 675


def test_committed_baseline_is_not_below_historical_lock() -> None:
    current = load_yaml_mapping(_repo_root() / "configs" / "coverage_baseline.yml")
    report = assert_coverage_floors_not_lowered(current=current)
    assert report.ok
    assert current["min_draft_publishable"] >= HISTORICAL_MIN_DRAFT_PUBLISHABLE


def test_lowering_draft_floor_to_2394_is_unauthorized() -> None:
    current = deepcopy(historical_lock_payload())
    current["min_draft_publishable"] = 2394
    report = evaluate_coverage_floors(current=current)
    assert not report.ok
    assert any(
        item.path == "min_draft_publishable" and item.new_value == 2394
        for item in report.unauthorized
    )
    with pytest.raises(UnauthorizedCoverageFloorReduction):
        assert_coverage_floors_not_lowered(current=current)


def test_raising_a_floor_is_allowed() -> None:
    current = deepcopy(historical_lock_payload())
    current["min_draft_publishable"] = HISTORICAL_MIN_DRAFT_PUBLISHABLE + 10
    current["min_publishable_by_metric"]["PAT"] = HISTORICAL_MIN_PUBLISHABLE_BY_METRIC["PAT"] + 1
    report = assert_coverage_floors_not_lowered(current=current)
    assert report.ok
    assert report.reductions == ()


def test_relative_pr_reduction_is_unauthorized_even_if_above_historical() -> None:
    previous = deepcopy(historical_lock_payload())
    previous["min_draft_publishable"] = 9000
    current = deepcopy(previous)
    current["min_draft_publishable"] = 8924
    with pytest.raises(UnauthorizedCoverageFloorReduction):
        assert_coverage_floors_not_lowered(current=current, previous=previous)


def test_relative_reduction_from_raised_floor_9100_to_9000_is_unauthorized() -> None:
    previous = deepcopy(historical_lock_payload())
    previous["min_draft_publishable"] = 9100
    current = deepcopy(previous)
    current["min_draft_publishable"] = 9000
    assert 9000 > HISTORICAL_MIN_DRAFT_PUBLISHABLE
    with pytest.raises(UnauthorizedCoverageFloorReduction):
        assert_coverage_floors_not_lowered(current=current, previous=previous)


def test_complete_governance_record_is_required_to_lower() -> None:
    current = deepcopy(historical_lock_payload())
    current["min_draft_publishable"] = 8000
    incomplete = _complete_governance(path="min_draft_publishable", old_value=8924, new_value=8000)
    incomplete.pop("approver")
    report = evaluate_coverage_floors(current=current, governance=incomplete)
    assert not report.ok
    authorized = _complete_governance(path="min_draft_publishable", old_value=8924, new_value=8000)
    assert set(REQUIRED_GOVERNANCE_FIELDS) <= set(authorized)
    report = assert_coverage_floors_not_lowered(current=current, governance=authorized)
    assert report.ok
    assert report.authorized[0].path == "min_draft_publishable"


def test_sector_metric_floor_cannot_be_removed() -> None:
    current = deepcopy(historical_lock_payload())
    del current["min_publishable_by_sector_metric"]["BANK"]["PAT"]
    with pytest.raises(UnauthorizedCoverageFloorReduction):
        assert_coverage_floors_not_lowered(current=current)


def test_timeout_max_cannot_be_raised() -> None:
    current = deepcopy(historical_lock_payload())
    current["max_quarantined_extraction_timeouts"] = 4
    with pytest.raises(UnauthorizedCoverageFloorReduction):
        assert_coverage_floors_not_lowered(current=current)


def test_yaml_roundtrip_of_committed_baseline() -> None:
    path = _repo_root() / "configs" / "coverage_baseline.yml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["min_draft_publishable"] == 8924
