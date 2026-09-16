from __future__ import annotations

from pathlib import Path

import pytest

from cse_financial_etl.v2.contracts.enums import ReleaseMode
from cse_financial_etl.v2.production.workbook_dispatch import (
    publish_for_engine,
    resolve_extraction_engine,
)
from tests.v2.helpers import release_context, source_fact


def test_resolve_engine_defaults_to_v1() -> None:
    assert resolve_extraction_engine(None) == "v1"
    assert resolve_extraction_engine("v1") == "v1"
    assert resolve_extraction_engine("v1", override="v2") == "v2"


def test_v1_dispatch_uses_v1_publisher(tmp_path: Path) -> None:
    target = tmp_path / "v1.xlsx"

    def v1_publisher() -> Path:
        target.write_text("v1", encoding="utf-8")
        return target

    path = publish_for_engine(
        engine="v1",
        destination=tmp_path / "ignored.xlsx",
        v1_publisher=v1_publisher,
    )
    assert path == target
    assert target.read_text(encoding="utf-8") == "v1"


def test_v2_dispatch_requires_release_context(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ReleaseContext"):
        publish_for_engine(
            engine="v2",
            destination=tmp_path / "v2.xlsx",
            source_facts=(source_fact(),),
        )


def test_v2_dispatch_uses_publish_production_workbook(tmp_path: Path) -> None:
    destination = tmp_path / "v2-draft.xlsx"
    path = publish_for_engine(
        engine="v2",
        release=release_context(mode=ReleaseMode.DRAFT),
        source_facts=(source_fact(),),
        destination=destination,
    )
    assert path == destination
    assert destination.is_file()
