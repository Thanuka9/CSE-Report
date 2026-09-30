from __future__ import annotations

from cse_financial_etl.v2.diagnostics.replay import (
    facts_are_deterministic,
    pipeline_results_are_deterministic,
)
from cse_financial_etl.v2.diagnostics.serialization import source_fact_to_mapping
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from tests.v2.helpers import geometric_document


def _document():
    return geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
            ((40.0, "Profit before tax"), (300.0, "1,500")),
        )
    )


def test_pipeline_is_deterministic_on_fresh_parse() -> None:
    first = run_filing_pipeline(_document(), issuer_id="issuer-1")
    second = run_filing_pipeline(_document(), issuer_id="issuer-1")
    left = tuple(source_fact_to_mapping(fact) for fact in first.source_facts)
    right = tuple(source_fact_to_mapping(fact) for fact in second.source_facts)
    assert facts_are_deterministic(left, right)
    assert pipeline_results_are_deterministic(first, second)
    derived_left = tuple(item.model_dump(mode="json") for item in first.derived_facts)
    derived_right = tuple(item.model_dump(mode="json") for item in second.derived_facts)
    assert derived_left == derived_right
    assert first.source_facts
