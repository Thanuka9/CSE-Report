"""V1 source-observation challenger contract tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cse_financial_etl.v2.challenger.models import V1SourceObservation
from cse_financial_etl.v2.challenger.observation_union import (
    observations_to_discovery_candidates,
    union_candidates,
)
from cse_financial_etl.v2.challenger.v1_source_observations import collect_v1_source_observations
from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import MatchKind, ResolutionStatus
from cse_financial_etl.v2.contracts.facts import FactCandidate
from cse_financial_etl.v2.contracts.provenance import SourceRef


def _ref(**kwargs: object) -> SourceRef:
    base = dict(
        filing_id="TEST",
        filing_version_id="TEST-2025-12-31",
        source_sha256="a" * 64,
        page_number=1,
        bbox=(10.0, 20.0, 30.0, 40.0),
        raw_text="100",
        parser_name="v1_physical_table_reconstructor",
        parser_version="1",
    )
    base.update(kwargs)
    return SourceRef(**base)  # type: ignore[arg-type]


def test_observation_is_discovery_only_until_v2_admits() -> None:
    obs = V1SourceObservation(
        observation_id="t1",
        source_ref=_ref(),
        table_id="p0001-t00",
        row_index=1,
        col_index=2,
        row_label="Profit for the period",
        raw_text="100",
        raw_value=Decimal("100"),
        publishable=False,
        reason_codes=("DISCOVERY_ONLY", "V1_PHYSICAL_OBSERVATION"),
    )
    assert obs.discovery_only is True
    assert obs.publishable is False


def test_changes_in_equity_hint_does_not_resolve_pat() -> None:
    obs = V1SourceObservation(
        observation_id="cie1",
        source_ref=_ref(raw_text="Profit for the period | 100"),
        statement_hint="CHANGES_IN_EQUITY",
        table_id="p0002-t00",
        row_index=3,
        col_index=1,
        row_label="Profit for the period",
        raw_text="100",
        raw_value=Decimal("100"),
        publishable=False,
        reason_codes=("DISCOVERY_ONLY",),
    )
    cands = observations_to_discovery_candidates((obs,))
    assert len(cands) == 1
    assert cands[0].concept is not None
    assert cands[0].concept.metric_code is None
    assert cands[0].entity_status is ResolutionStatus.UNRESOLVED
    assert "DISCOVERY_ONLY" in cands[0].reason_codes


def test_union_dedupes_identical_source_identity() -> None:
    shared = FactCandidate(
        candidate_id="a",
        statement_id="s",
        cell_id="c",
        row_id="r",
        column_id="col",
        concept=ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN),
        raw_value=Decimal("1"),
        source_ref=_ref(),
    )
    twin = shared.model_copy(update={"candidate_id": "b"})
    other = shared.model_copy(
        update={
            "candidate_id": "c",
            "raw_value": Decimal("2"),
            "source_ref": _ref(bbox=(1.0, 2.0, 3.0, 4.0)),
        }
    )
    merged = union_candidates((shared,), (twin, other))
    assert len(merged) == 2


def test_collect_v1_observations_from_holdout_pdf_when_present() -> None:
    root = Path(__file__).resolve().parents[3]
    # Prefer any local PDF under data/raw/filings for a smoke path.
    pdfs = sorted((root / "data" / "raw" / "filings").rglob("*.pdf"))
    if not pdfs:
        pytest.skip("no local filings PDFs")
    pdf = pdfs[0]
    observations = collect_v1_source_observations(
        pdf, filing_version_id="smoke-fv", filing_id="smoke"
    )
    assert isinstance(observations, tuple)
    # Must never mark publishable from the physical reader alone.
    assert all(not obs.publishable for obs in observations)
    assert all(obs.source_ref.source_sha256 for obs in observations)
    assert all(obs.source_ref.bbox is not None for obs in observations)
