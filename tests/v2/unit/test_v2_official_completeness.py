from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cse_financial_etl.config import AppConfig
from cse_financial_etl.reporting.production_workbook import generate_production_workbook
from cse_financial_etl.v2.contracts.enums import ReviewStatus
from tests.v2.helpers import source_fact


def _baseline(root: Path, floor: int) -> None:
    configs = root / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    (configs / "coverage_baseline.yml").write_text(
        yaml.safe_dump({"min_draft_publishable": floor}),
        encoding="utf-8",
    )


def test_official_v2_workbook_fails_when_approved_native_coverage_is_thin(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path, 2)
    approved = source_fact(review_status=ReviewStatus.APPROVED)
    with pytest.raises(RuntimeError, match="V2_DRAFT_NATIVE_COVERAGE_BELOW_FLOOR"):
        generate_production_workbook(
            tmp_path,
            approved.period_end,
            (approved.period_end,),
            "run-1",
            engine="v2",
            app_config=AppConfig(extraction_engine="v2", release_mode="OFFICIAL"),
            v2_source_facts=(approved,),
            v2_derived_facts=(),
        )


def test_official_v2_workbook_requires_approved_coverage_floor(tmp_path: Path) -> None:
    _baseline(tmp_path, 1)
    pending = source_fact()
    with pytest.raises(RuntimeError, match="V2_OFFICIAL_COVERAGE_BELOW_FLOOR"):
        generate_production_workbook(
            tmp_path,
            pending.period_end,
            (pending.period_end,),
            "run-1",
            engine="v2",
            app_config=AppConfig(extraction_engine="v2", release_mode="OFFICIAL"),
            v2_source_facts=(pending,),
            v2_derived_facts=(),
        )


def test_official_v2_workbook_passes_when_native_approved_floor_is_met(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path, 1)
    approved = source_fact(review_status=ReviewStatus.APPROVED)
    path = generate_production_workbook(
        tmp_path,
        approved.period_end,
        (approved.period_end,),
        "run-1",
        engine="v2",
        app_config=AppConfig(extraction_engine="v2", release_mode="OFFICIAL"),
        v2_source_facts=(approved,),
        v2_derived_facts=(),
    )
    assert path.is_file()
