from __future__ import annotations

from datetime import date
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import EntityScope, FirstFailureStage
from cse_financial_etl.v2.diagnostics.candidate_trace import (
    build_candidate_traces,
    write_candidate_trace,
)
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.resolution.resolver import build_candidates, resolve_source_facts
from tests.v2.helpers import geometric_document


def test_rejected_candidates_remain_in_trace(tmp_path: Path) -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    statements, facts, _derived, _metrics = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        candidate_trace_path=tmp_path / "candidate_trace.parquet",
    )
    candidates = tuple(
        candidate for statement in statements for candidate in build_candidates(statement)
    )
    traces = build_candidate_traces(
        candidates,
        facts,
        statements=statements,
        issuer_id="issuer-1",
        filing_version_id=document.filing_version_id,
    )
    assert traces
    assert len(traces) == len(candidates)
    assert any(not item.source_fact_created for item in traces)
    assert all(item.first_failure_stage is not None for item in traces)
    assert (tmp_path / "candidate_trace.parquet").is_file()


def test_group_candidate_is_traced_when_query_wants_company() -> None:
    document = geometric_document(
        (
            ((40.0, "GROUP"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    statements, facts, _derived, _metrics = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        expected_entity_scope=EntityScope.COMPANY,
        target_period_end=date(2026, 6, 30),
    )
    assert not [fact for fact in facts if fact.metric_code == "PAT"]
    candidates = tuple(
        candidate for statement in statements for candidate in build_candidates(statement)
    )
    traces = build_candidate_traces(
        candidates,
        facts,
        statements=statements,
        issuer_id="issuer-1",
        filing_version_id=document.filing_version_id,
        expected_entity_scope=EntityScope.COMPANY,
    )
    pat_traces = [item for item in traces if item.resolved_metric == "PAT"]
    assert pat_traces
    assert all(item.source_fact_created is False for item in pat_traces)
    assert {item.first_failure_stage for item in pat_traces} == {
        FirstFailureStage.PRODUCTION_SELECTION
    }


def test_empty_trace_parquet_is_writable(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    write_candidate_trace(path, ())
    assert path.is_file()


def test_resolve_and_trace_use_the_same_admission_rule() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    statements, _facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="issuer-1")
    candidates = tuple(
        candidate for statement in statements for candidate in build_candidates(statement)
    )
    resolved = resolve_source_facts(
        candidates, issuer_id="issuer-1", filing_version_id=document.filing_version_id
    )
    traces = build_candidate_traces(
        candidates,
        resolved,
        statements=statements,
        issuer_id="issuer-1",
        filing_version_id=document.filing_version_id,
    )
    created = {item.cell_id for item in traces if item.source_fact_created}
    assert created == {fact.cell_id for fact in resolved}
