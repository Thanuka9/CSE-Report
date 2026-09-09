from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.transformation.ratios import derive_ratio_facts

PERIOD = date(2026, 6, 30)
FLOW_CODES = {"PAT", "PBT", "TOP_LINE", "OPERATING_PROFIT", "EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED"}


def _fact(
    code: str,
    value: str,
    *,
    validation: str = "PASSED",
    entity: str = "COMPANY",
    role: str = "CURRENT",
    evidence: dict[str, object] | None = None,
) -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        period_end=PERIOD,
        metric_code=code,
        metric_type="MONETARY_ABSOLUTE",
        raw_text=value,
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        currency="LKR",
        scale_factor=1,
        entity_scope=entity,
        source_page=1,
        source_line=code,
        unit_source_text="LKR",
        confidence="HIGH",
        status="EXTRACTED",
        raw_label=code,
        comparison_role=role,
        duration_months=3 if code in FLOW_CODES else None,
        validation_status=validation,
        review_status="APPROVED",
        overall_certainty=0.95,
        certainty_band="HIGH",
        evidence_json=json.dumps(evidence or {}),
    )


def _by_code(facts: list[ExtractedFact]) -> dict[str, ExtractedFact]:
    return {fact.metric_code: fact for fact in facts}


def test_failed_source_fact_is_withheld_before_ratio_derivation() -> None:
    source = [
        _fact("PAT", "10"),
        _fact("TOTAL_EQUITY", "100", validation="FAILED"),
        _fact("TOTAL_ASSETS", "200"),
        _fact("TOTAL_LIABILITIES", "100"),
        _fact("TOP_LINE", "50"),
    ]
    [(filing, materialized)] = derive_ratio_facts([("filing", source)])
    assert filing == "filing"
    by_code = _by_code(materialized)
    assert by_code["TOTAL_EQUITY"].status == "VALIDATION_FAILED"
    assert by_code["TOTAL_EQUITY"].normalized_value is None
    assert by_code["ROE"].status == "INSUFFICIENT_INPUT"
    assert by_code["DEBT_TO_EQUITY"].status == "INSUFFICIENT_INPUT"


def test_explicit_layout_fallback_is_not_materialized_as_published() -> None:
    fallback = _fact(
        "EPS_BASIC",
        "1.25",
        evidence={"explicit_fallback": "COMPILER_NO_STATEMENTS"},
    )
    [(filing, materialized)] = derive_ratio_facts([("filing", [fallback])])
    assert filing == "filing"
    by_code = _by_code(materialized)
    assert by_code["EPS_BASIC"].status == "EXPLICIT_LAYOUT_FALLBACK_REQUIRED"
    assert by_code["EPS_BASIC"].normalized_value is None


def test_ratio_context_comes_from_compatible_inputs_not_arbitrary_template() -> None:
    source = [
        _fact("NAVPS", "5", role="UNKNOWN"),
        _fact("PAT", "10", entity="BANK"),
        _fact("TOTAL_EQUITY", "100", entity="BANK"),
        _fact("TOTAL_ASSETS", "200", entity="BANK"),
        _fact("TOTAL_LIABILITIES", "100", entity="BANK"),
        _fact("TOP_LINE", "50", entity="BANK"),
    ]
    [(_, materialized)] = derive_ratio_facts([("filing", source)])
    by_code = _by_code(materialized)
    for code in ("DEBT_TO_EQUITY", "ROE", "ROA", "NPM"):
        ratio = by_code[code]
        assert ratio.status == "EXTRACTED_DERIVED"
        assert ratio.entity_scope == "BANK"
        assert ratio.comparison_role == "CURRENT"
        assert ratio.currency is None
        assert ratio.source_page is None
        assert ratio.review_status == "REVIEW"
