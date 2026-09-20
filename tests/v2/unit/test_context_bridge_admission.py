"""Unit tests for V1→V2 header context bridge admission."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cse_financial_etl.v2.challenger.observation_union import (
    observations_to_discovery_candidates,
    union_candidates,
)
from cse_financial_etl.v2.challenger.v1_source_observations import collect_v1_source_observations
from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    MatchKind,
    ResolutionStatus,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.facts import FactCandidate
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts
from cse_financial_etl.v2.resolution.resolver import source_admission_failure
from cse_financial_etl.v2.taxonomy.registry import load_registry


def _ref(**kwargs: object) -> SourceRef:
    base = dict(
        filing_id="TEST",
        filing_version_id="TEST-2025-12-31",
        source_sha256="a" * 64,
        page_number=1,
        bbox=(10.0, 20.0, 30.0, 40.0),
        raw_text="100",
        parser_name="v1_physical_table_reconstructor",
        parser_version="2",
    )
    base.update(kwargs)
    return SourceRef(**base)  # type: ignore[arg-type]


def _cand(**kwargs: object) -> FactCandidate:
    base = dict(
        candidate_id="a",
        statement_id="s",
        cell_id="c",
        row_id="r",
        column_id="col",
        concept=ConceptCandidate(metric_code="TOP_LINE", match_kind=MatchKind.EXACT_ALIAS),
        concept_status=ResolutionStatus.RESOLVED,
        entity_scope=EntityScope.GROUP,
        entity_status=ResolutionStatus.RESOLVED,
        period_end=date(2025, 12, 31),
        period_status=ResolutionStatus.RESOLVED,
        duration_months=3,
        duration_status=ResolutionStatus.RESOLVED,
        comparison_role=ComparisonRole.CURRENT,
        comparison_status=ResolutionStatus.RESOLVED,
        currency="LKR",
        monetary_scale=Decimal("1000"),
        unit_dimension=UnitDimension.MONETARY,
        unit_status=ResolutionStatus.RESOLVED,
        raw_value=Decimal("731203"),
        source_ref=_ref(),
        reason_codes=(),
    )
    base.update(kwargs)
    return FactCandidate(**base)  # type: ignore[arg-type]


def test_union_prefers_bridged_duration_over_v2() -> None:
    v2 = _cand(
        candidate_id="v2",
        duration_months=3,
        reason_codes=("V2_NATIVE",),
        source_ref=_ref(bbox=(100.0, 100.0, 120.0, 110.0), raw_text="2,049,000"),
        raw_value=Decimal("2049000"),
    )
    v1 = _cand(
        candidate_id="v1",
        duration_months=None,
        duration_status=ResolutionStatus.UNRESOLVED,
        reason_codes=("CONTEXT_BRIDGED_SOURCE_OWNED", "FLOW_DURATION_UNRESOLVED_OR_CUMULATIVE"),
        source_ref=_ref(bbox=(100.05, 100.02, 120.01, 110.0), raw_text="2,049,000"),
        raw_value=Decimal("2049000"),
    )
    merged = union_candidates((v2,), (v1,))
    assert len(merged) == 1
    assert merged[0].candidate_id == "v1"
    assert merged[0].duration_months is None


def test_union_keeps_distinct_bboxes_despite_duplicate_candidate_id() -> None:
    """Note glyph and amount can share V2 cell_id; both must survive union."""

    note = _cand(
        candidate_id="same-id",
        raw_value=Decimal("4"),
        source_ref=_ref(bbox=(217.0, 106.5, 220.4, 113.2), raw_text="4"),
        reason_codes=("V2_NATIVE",),
    )
    amount = _cand(
        candidate_id="same-id",
        raw_value=Decimal("2956681101"),
        source_ref=_ref(bbox=(256.3, 106.7, 294.9, 113.4), raw_text="2,956,681,101"),
        reason_codes=("V2_NATIVE",),
    )
    merged = union_candidates((note, amount), ())
    values = {c.raw_value for c in merged}
    assert values == {Decimal("4"), Decimal("2956681101")}


def test_unanimous_table_entity_and_period_fill() -> None:
    from cse_financial_etl.v2.challenger.context_bridge import _apply_unanimous_table_header_context
    from cse_financial_etl.v2.challenger.models import V1SourceObservation

    shared = dict(
        reader_id="t",
        reader_version="2",
        statement_hint="INCOME_STATEMENT",
        table_id="t0",
        row_index=0,
        publishable=False,
        evidence_notes=(),
    )
    filled = V1SourceObservation(
        observation_id="a",
        source_ref=_ref(bbox=(10.0, 10.0, 20.0, 20.0), raw_text="100"),
        col_index=2,
        row_label="Revenue",
        raw_text="100",
        raw_value=Decimal("100"),
        entity_scope=EntityScope.GROUP,
        period_end=date(2025, 12, 31),
        comparison_role=ComparisonRole.CURRENT,
        unit_dimension=UnitDimension.MONETARY,
        reason_codes=("CONTEXT_BRIDGED_SOURCE_OWNED",),
        **shared,
    )
    silent = V1SourceObservation(
        observation_id="b",
        source_ref=_ref(bbox=(30.0, 10.0, 40.0, 20.0), raw_text="200"),
        col_index=3,
        row_label="Revenue",
        raw_text="200",
        raw_value=Decimal("200"),
        entity_scope=None,
        period_end=None,
        comparison_role=ComparisonRole.COMPARATIVE,
        unit_dimension=UnitDimension.MONETARY,
        reason_codes=("DISCOVERY_ONLY",),
        **shared,
    )
    out = _apply_unanimous_table_header_context([filled, silent])
    assert out[1].entity_scope is EntityScope.GROUP
    assert out[1].period_end == date(2025, 12, 31)
    assert "ENTITY_FROM_TABLE_HEADER_UNANIMOUS" in out[1].reason_codes
    assert "PERIOD_FROM_TABLE_HEADER_UNANIMOUS" in out[1].reason_codes
    assert "CONTEXT_BRIDGED_SOURCE_OWNED" in out[1].reason_codes


def test_note_index_and_share_count_rejected_from_discovery() -> None:
    from cse_financial_etl.v2.challenger.models import V1SourceObservation
    from cse_financial_etl.v2.challenger.observation_union import (
        looks_like_note_index,
        looks_like_share_count_not_eps,
        observations_to_discovery_candidates,
    )

    assert looks_like_note_index(raw_text="4", raw_value=Decimal("4"))
    assert looks_like_share_count_not_eps(metric_code="EPS_BASIC", raw_value=Decimal("17577000"))
    assert not looks_like_share_count_not_eps(metric_code="EPS_BASIC", raw_value=Decimal("0.22"))

    note_obs = V1SourceObservation(
        observation_id="n1",
        reader_id="t",
        reader_version="2",
        source_ref=_ref(raw_text="4", bbox=(1.0, 1.0, 2.0, 2.0)),
        statement_hint="INCOME_STATEMENT",
        table_id="t0",
        row_index=0,
        col_index=1,
        row_label="Revenue from contracts with customers",
        raw_text="4",
        raw_value=Decimal("4"),
        publishable=False,
        reason_codes=("DISCOVERY_ONLY",),
        evidence_notes=(),
    )
    share_obs = V1SourceObservation(
        observation_id="n2",
        reader_id="t",
        reader_version="2",
        source_ref=_ref(raw_text="earnings per share | 17,577,000", bbox=(3.0, 3.0, 4.0, 4.0)),
        statement_hint="INCOME_STATEMENT",
        table_id="t0",
        row_index=1,
        col_index=1,
        row_label="earnings per share",
        raw_text="17,577,000",
        raw_value=Decimal("17577000"),
        publishable=False,
        reason_codes=("DISCOVERY_ONLY",),
        evidence_notes=(),
    )
    cands = observations_to_discovery_candidates((note_obs, share_obs))
    assert all(c.concept.metric_code is None for c in cands)


def test_acl_plastics_bridged_topline_reaches_draft_selection() -> None:
    root = Path(__file__).resolve().parents[3]
    cohort_path = root / "reports/v1_v2_same_input/same_input_2026-09-09/pinned_cohort.json"
    if not cohort_path.is_file():
        pytest.skip("pinned cohort missing")
    import json

    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    item = next(
        (
            f
            for f in cohort["filings"]
            if f["issuer_dir"] == "ACL_PLASTICS_PLC" and f["period_end"] == "2025-12-31"
        ),
        None,
    )
    if item is None or not Path(item["abs_path"]).is_file():
        pytest.skip("ACL PLASTICS PDF missing")

    pdf = Path(item["abs_path"])
    observations = collect_v1_source_observations(
        pdf, filing_version_id="test", filing_id="APLA.N0000"
    )
    revenue = [
        o
        for o in observations
        if o.row_label.startswith("Revenue from contracts") and o.duration_months == 3
    ]
    assert revenue, "expected quarter revenue observation with duration 3"
    assert all(o.entity_scope is EntityScope.GROUP or o.entity_scope is EntityScope.COMPANY for o in revenue)

    cands = observations_to_discovery_candidates(tuple(revenue[:1]))
    assert source_admission_failure(cands[0], registry=load_registry()) is None

    v2 = run_pdf_pipeline(
        pdf,
        issuer_id="APLA.N0000",
        filing_version_id="v2-only",
        issuer_name="ACL PLASTICS PLC",
        v1_source_observations=False,
    )
    assisted = run_pdf_pipeline(
        pdf,
        issuer_id="APLA.N0000",
        filing_version_id="assisted",
        issuer_name="ACL PLASTICS PLC",
        v1_source_observations=True,
    )
    sel_v2 = select_pipeline_facts(
        v2.source_facts, period_end=date(2025, 12, 31), expected_entity=EntityScope.GROUP
    )
    sel_as = select_pipeline_facts(
        assisted.source_facts, period_end=date(2025, 12, 31), expected_entity=EntityScope.GROUP
    )
    assert not any(f.metric_code == "TOP_LINE" for f in sel_v2)
    top = [f for f in sel_as if f.metric_code == "TOP_LINE"]
    assert len(top) == 1
    assert top[0].normalized_value == Decimal("731203000")
    assert top[0].duration_months == 3
