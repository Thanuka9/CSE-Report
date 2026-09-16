"""Production workbook routing: V1 default, V2 publish_production_workbook + ReleaseContext."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from cse_financial_etl.config import AppConfig
from cse_financial_etl.reporting.production_workbook import (
    generate_production_workbook,
    resolve_extraction_engine,
)
from cse_financial_etl.v2.contracts.enums import ReleaseMode
from cse_financial_etl.v2.contracts.release import ReleaseContext


def test_resolve_extraction_engine_defaults_to_v1_from_config() -> None:
    config = AppConfig(extraction_engine="v1")
    assert resolve_extraction_engine(config, None) == "v1"
    assert resolve_extraction_engine(config, "v2") == "v2"


def test_v1_workbook_path_uses_generate_excel(tmp_path: Path) -> None:
    config = AppConfig(extraction_engine="v1", release_mode="DRAFT")
    expected = tmp_path / "outputs" / "workbooks" / "v1.xlsx"
    with (
        patch(
            "cse_financial_etl.reporting.production_workbook.generate_excel",
            return_value=expected,
        ) as generate_excel,
        patch(
            "cse_financial_etl.reporting.production_workbook.publish_production_workbook",
        ) as publish,
    ):
        path = generate_production_workbook(
            tmp_path,
            date(2026, 9, 9),
            (date(2026, 6, 30),),
            "run-v1",
            engine="v1",
            app_config=config,
        )
    generate_excel.assert_called_once()
    publish.assert_not_called()
    assert path == expected


def test_v2_workbook_path_calls_publish_with_release_context(tmp_path: Path) -> None:
    config = AppConfig(extraction_engine="v1", release_mode="DRAFT")
    release = ReleaseContext(
        generation_id="run-v2",
        run_id="run-v2",
        mode=ReleaseMode.DRAFT,
        code_sha="deadbeef",
        policy_hash="policy-abc",
        source_snapshot_id="market:abc",
    )
    expected = tmp_path / "outputs" / "workbooks" / "v2.xlsx"
    with (
        patch(
            "cse_financial_etl.reporting.production_workbook.generate_excel",
        ) as generate_excel,
        patch(
            "cse_financial_etl.reporting.production_workbook.build_production_release_context",
            return_value=release,
        ) as build_release,
        patch(
            "cse_financial_etl.reporting.production_workbook.publish_production_workbook",
            return_value=expected,
        ) as publish,
        patch(
            "cse_financial_etl.reporting.production_workbook.load_v2_publication_facts",
            return_value=((), ()),
        ),
    ):
        path = generate_production_workbook(
            tmp_path,
            date(2026, 9, 9),
            (date(2026, 6, 30),),
            "run-v2",
            engine="v2",
            app_config=config,
        )
    generate_excel.assert_not_called()
    build_release.assert_called_once_with(
        tmp_path,
        run_id="run-v2",
        as_of_date=date(2026, 9, 9),
        release_mode="DRAFT",
    )
    publish.assert_called_once()
    kwargs = publish.call_args.kwargs
    assert isinstance(kwargs["release"], ReleaseContext)
    assert kwargs["release"].run_id == "run-v2"
    assert path == expected


def test_invalid_engine_raises() -> None:
    config = AppConfig(extraction_engine="v1")
    with pytest.raises(ValueError, match="v1 or v2"):
        resolve_extraction_engine(config, "v3")
