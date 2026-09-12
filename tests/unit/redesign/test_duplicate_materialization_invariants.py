"""Regression invariants for duplicate metric materialization.

The pipeline must never choose a financial fact merely because it appeared last in a
list/dict comprehension. Duplicate or conflicting metric materializations are an
ambiguity signal and must fail closed at query, publication, and derivation boundaries.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.facts.publisher import (
    LAYOUT_FALLBACK_QUERY_MISS,
    mark_explicit_layout_fallback,
    publish_from_compiler,
)
from cse_financial_etl.facts.query_engine import QueriedFact, query_target_facts, queried_values
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.transformation.ratios import derive_ratio_facts

PERIOD = date(2026, 6, 30)


def _fact(metric: str, value: str, *, status: str = "EXTRACTED") -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=PERIOD,
        metric_code=metric,
        metric_type=(
            "MONETARY_PER_SHARE"
            if metric in {"EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED", "NAVPS"}
            else "MONETARY_ABSOLUTE"
        ),
        raw_text=value,
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line=metric,
        unit_source_text="Rs.",
        confidence="HIGH",
        status=status,
        raw_label=metric,
        extraction_method="COMPILER_QUERY",
        semantic_model="compiler",
        semantic_confidence=1.0,
        entity_confidence=1.0,
        period_confidence=1.0,
        unit_confidence=1.0,
        column_confidence=1.0,
        validation_confidence=1.0,
        overall_certainty=0.98,
        certainty_band="HIGH",
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
    )


def _entry(entry_id: str, concept: str, value: str, *, score: float = 0.95) -> LedgerEntry:
    return LedgerEntry(
        entry_id=entry_id,
        tunnel="A",
        concept=concept,
        status="accepted",
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        entity="COMPANY",
        period_end=PERIOD.isoformat(),
        duration_months=3,
        comparison_role="CURRENT",
        unit="LKR",
        scale_factor=1,
        page=1,
        bbox="[0,0,1,1]",
        label=concept,
        score=score,
        evidence={
            "semantic_score": 1.0,
            "candidate_origin": "compiler_geometry",
            "statement_region_confidence": 1.0,
        },
    )


def _report() -> dict[str, object]:
    return {
        "filing_sha": "synthetic",
        "tunnel_a": {"statements": 1, "compile_requested": True},
        "tunnel_b": {},
        "resolver_c": {},
    }


def test_duplicate_layout_metric_never_last_write_wins() -> None:
    facts, stats = publish_from_compiler(
        queried=[],
        layout_facts=[_fact("TOP_LINE", "100"), _fact("TOP_LINE", "200")],
        report=_report(),
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=PERIOD,
        required_entity="COMPANY",
    )

    top_line = [fact for fact in facts if fact.metric_code == "TOP_LINE"]
    assert len(top_line) == 1
    assert top_line[0].status == "AMBIGUOUS_CANDIDATES"
    assert top_line[0].normalized_value is None
    assert stats["duplicate_layout_codes"] == ["TOP_LINE"]


def test_explicit_layout_fallback_is_review_evidence_not_publishable_value() -> None:
    source = _fact("PAT", "160")
    fallback = mark_explicit_layout_fallback(
        [source],
        issue_code=LAYOUT_FALLBACK_QUERY_MISS,
        detail="synthetic fallback",
        report=_report(),
    )[0]

    assert fallback.raw_value == Decimal("160")
    assert fallback.normalized_value is None
    assert fallback.status == "EXPLICIT_LAYOUT_FALLBACK_REQUIRED"
    assert fallback.validation_status == "FAILED"
    assert fallback.confidence == "LOW"
    assert fallback.overall_certainty == 0.0
    assert fallback.certainty_band == "NONE"


def test_duplicate_queried_metric_never_last_write_wins() -> None:
    first = QueriedFact("PAT", "PAT", _entry("p1", "PAT", "100"), "EXTRACTED")
    second = QueriedFact("PAT", "PAT", _entry("p2", "PAT", "200"), "EXTRACTED")

    facts, stats = publish_from_compiler(
        queried=[first, second],
        layout_facts=[],
        report=_report(),
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=PERIOD,
        required_entity="COMPANY",
    )

    pat = [fact for fact in facts if fact.metric_code == "PAT"]
    assert len(pat) == 1
    assert pat[0].status == "AMBIGUOUS_CANDIDATES"
    assert pat[0].normalized_value is None
    assert stats["duplicate_query_codes"] == ["PAT"]


def test_queried_values_withholds_duplicate_metric_code() -> None:
    first = QueriedFact("PAT", "PAT", _entry("p1", "PAT", "100"), "EXTRACTED")
    second = QueriedFact("PAT", "PAT", _entry("p2", "PAT", "200"), "EXTRACTED")
    assert queried_values([first, second])["PAT"] is None


def test_query_layer_abstains_if_multiple_accepted_candidates_conflict() -> None:
    ledger = CandidateLedger(
        entries=[
            _entry("p1", "PAT", "100", score=0.99),
            _entry("p2", "PAT", "200", score=0.90),
        ]
    )

    queried = query_target_facts(
        ledger,
        entity="COMPANY",
        period_end=PERIOD,
        target_duration=3,
    )
    pat = next(fact for fact in queried if fact.metric_code == "PAT")
    assert pat.status == "AMBIGUOUS_CANDIDATES"
    assert pat.entry is None
    assert pat.issue == "multiple_accepted_candidates_conflict"


def test_duplicate_ratio_source_metrics_are_withheld_and_derivation_abstains() -> None:
    facts = [
        _fact("PAT", "10"),
        _fact("PAT", "20"),
        _fact("TOTAL_EQUITY", "100"),
        _fact("TOTAL_ASSETS", "300"),
        _fact("TOP_LINE", "50"),
    ]

    result = derive_ratio_facts([(object(), facts)], display_periods=[PERIOD])[0][1]
    pats = [fact for fact in result if fact.metric_code == "PAT"]
    assert len(pats) == 2
    assert all(fact.status == "AMBIGUOUS_CANDIDATES" for fact in pats)
    assert all(fact.normalized_value is None for fact in pats)

    ratios = {fact.metric_code: fact for fact in result if fact.metric_code in {"ROE", "ROA", "NPM"}}
    assert ratios["ROE"].normalized_value is None
    assert ratios["ROA"].normalized_value is None
    assert ratios["NPM"].normalized_value is None
    assert ratios["ROE"].status == "AMBIGUOUS_INPUT"
