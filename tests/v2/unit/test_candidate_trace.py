from __future__ import annotations

from datetime import date
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import (
    EntityScope,
    FirstFailureStage,
    ProductionSelectionStatus,
    PublicationStatus,
)
from cse_financial_etl.v2.diagnostics.candidate_trace import (
    build_candidate_traces,
    write_candidate_trace,
)
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.resolution.resolver import resolve_source_facts
from tests.v2.helpers import geometric_document


def test_rejected_candidates_remain_in_trace(tmp_path: Path) -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    result = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        candidate_trace_path=tmp_path / "candidate_trace.parquet",
    )
    assert result.traces
    assert len(result.traces) == len(result.candidates)
    assert [item.candidate_id for item in result.traces] == [
        item.candidate_id for item in result.candidates
    ]
    assert [item.cell_id for item in result.traces] == [
        item.cell_id for item in result.candidates
    ]
    created_ids = {item.source_fact_id for item in result.traces if item.source_fact_created}
    assert created_ids == {fact.fact_id for fact in result.source_facts}
    for trace, candidate in zip(result.traces, result.candidates, strict=True):
        assert trace.entity_scope == candidate.entity_scope
        assert trace.period_end == candidate.period_end
        assert trace.duration_months == candidate.duration_months
        assert trace.comparison_role == candidate.comparison_role
        assert trace.unit_dimension == candidate.unit_dimension
        assert trace.reason_codes == candidate.reason_codes or trace.source_fact_created
        assert trace.page_classification_status is not None or trace.page_classification is None
        assert trace.statement_detection_status
        assert trace.table_detection_status
        assert trace.row_reconstruction_status
        assert trace.concept_alternatives
        alt = trace.concept_alternatives[0]
        assert alt.match_kind
        assert alt.rejection_reason is not None or alt.metric_code
    assert any(not item.source_fact_created for item in result.traces)
    assert all(item.first_failure_stage is not None for item in result.traces)
    assert all(item.concept_alternatives for item in result.traces)
    assert (tmp_path / "candidate_trace.parquet").is_file()


def test_group_source_fact_is_not_selected_for_company_query() -> None:
    document = geometric_document(
        (
            ((40.0, "GROUP"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    result = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        expected_entity_scope=EntityScope.COMPANY,
        target_period_end=date(2026, 6, 30),
    )
    pats = [fact for fact in result.source_facts if fact.metric_code == "PAT"]
    assert pats
    assert all(fact.entity_scope is EntityScope.GROUP for fact in pats)
    assert all(fact.publication_status is PublicationStatus.ELIGIBLE for fact in pats)
    assert result.production_selected_source == ()
    pat_traces = [item for item in result.traces if item.resolved_metric == "PAT"]
    assert pat_traces
    assert all(item.source_fact_created is True for item in pat_traces)
    assert all(item.production_selected is False for item in pat_traces)
    assert {item.production_selection_status for item in pat_traces} == {
        ProductionSelectionStatus.NOT_SELECTED
    }
    assert {item.production_selection_reason for item in pat_traces} == {
        "ENTITY_SCOPE_MISMATCH"
    }
    assert FirstFailureStage.PRODUCTION_SELECTION not in {
        item.first_failure_stage for item in pat_traces
    }


def test_empty_trace_parquet_is_writable(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    write_candidate_trace(path, ())
    assert path.is_file()


def test_resolve_and_trace_use_the_same_in_run_candidates() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    result = run_filing_pipeline(document, issuer_id="issuer-1")
    resolved = resolve_source_facts(
        result.candidates,
        issuer_id="issuer-1",
        filing_version_id=document.filing_version_id,
    )
    traces = build_candidate_traces(
        result.candidates,
        resolved,
        statements=result.statements,
        issuer_id="issuer-1",
        filing_version_id=document.filing_version_id,
    )
    created = {item.cell_id for item in traces if item.source_fact_created}
    assert created == {fact.cell_id for fact in resolved}
    assert len(result.traces) == len(result.candidates)
    assert [item.candidate_id for item in result.traces] == [
        item.candidate_id for item in result.candidates
    ]
    assert result.traces[0].regime is None or isinstance(result.traces[0].regime, str)
