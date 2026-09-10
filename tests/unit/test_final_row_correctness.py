from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from cse_financial_etl.contracts.eligibility import HEADER_CONFLICT, evaluate_eligibility
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry
from cse_financial_etl.transformation.ratios import derive_ratio_facts
from cse_financial_etl.tunnels.common_financial_engine import _column_header_conflicts
from cse_financial_etl.validation.row_safety import (
    inconsistent_scale_metrics,
    per_share_source_is_unsafe,
    ratio_plausibility_issue,
    source_has_numeric_corruption,
)

PERIOD = date(2026, 3, 31)
FLOW = {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT", "EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED"}


def _fact(
    code: str,
    raw: str,
    *,
    scale: int = 1,
    source_line: str | None = None,
) -> ExtractedFact:
    raw_value = Decimal(raw)
    metric_type = "MONETARY_PER_SHARE" if code in {"EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED", "NAVPS"} else "MONETARY_ABSOLUTE"
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=PERIOD,
        metric_code=code,
        metric_type=metric_type,
        raw_text=raw,
        raw_value=raw_value,
        normalized_value=raw_value * Decimal(scale),
        currency="LKR",
        scale_factor=scale,
        entity_scope="COMPANY",
        source_page=2,
        source_line=source_line or code,
        unit_source_text="LKR '000" if scale == 1000 else "LKR",
        confidence="HIGH",
        status="EXTRACTED",
        raw_label=code,
        comparison_role="CURRENT",
        duration_months=3 if code in FLOW else None,
        validation_status="PASSED",
        review_status="REVIEW",
        overall_certainty=0.95,
        certainty_band="HIGH",
    )


def _by_code(facts: list[ExtractedFact]) -> dict[str, ExtractedFact]:
    return {fact.metric_code: fact for fact in facts}


def test_corrupted_current_navps_row_cannot_publish_clean_comparative_token() -> None:
    assert source_has_numeric_corruption("Net assets per share 649..i.1")
    assert per_share_source_is_unsafe("NAVPS", "Net assets per share 649..i.1")
    navps = _fact("NAVPS", "323.36", source_line="Net assets per share 649..i.1")
    [(_, materialized)] = derive_ratio_facts([("filing", [navps])])
    result = _by_code(materialized)["NAVPS"]
    assert result.status == "VALUE_CONTEXT_UNRESOLVED"
    assert result.normalized_value is None
    assert result.validation_status == "FAILED"


def test_missing_leading_numeric_group_is_corruption() -> None:
    assert source_has_numeric_corruption("Profit after taxation ,874 (174.1%)")
    pat = _fact("PAT", "7", scale=1000, source_line="Profit after taxation ,874 (174.1%)")
    [(_, materialized)] = derive_ratio_facts([("filing", [pat])])
    result = _by_code(materialized)["PAT"]
    assert result.status == "VALUE_CONTEXT_UNRESOLVED"
    assert result.normalized_value is None


def test_same_statement_scale_disagreement_fails_closed() -> None:
    source = [
        _fact("TOP_LINE", "1567001", scale=1, source_line="Revenue"),
        _fact("OPERATING_PROFIT", "75556", scale=1, source_line="Operating profit"),
        _fact("PBT", "2240", scale=1, source_line="Profit before tax"),
        _fact("PAT", "2240", scale=1000, source_line="Profit for the period"),
    ]
    unsafe = inconsistent_scale_metrics(
        {fact.metric_code: (fact.normalized_value, fact.scale_factor) for fact in source}
    )
    assert unsafe == {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"}
    [(_, materialized)] = derive_ratio_facts([("filing", source)])
    by_code = _by_code(materialized)
    for code in unsafe:
        assert by_code[code].status == "UNIT_NOT_RESOLVED"
        assert by_code[code].normalized_value is None


def test_cross_statement_scale_contradiction_withholds_implicit_whole_unit_side() -> None:
    source = [
        _fact("PAT", "101538", scale=1000, source_line="Profit for the period"),
        _fact("TOP_LINE", "431908", scale=1000, source_line="Revenue"),
        _fact("TOTAL_ASSETS", "1693291", scale=1, source_line="Total Assets"),
        _fact("TOTAL_EQUITY", "1362625", scale=1, source_line="Total Equity"),
        _fact("TOTAL_LIABILITIES", "330666", scale=1, source_line="Total Liabilities"),
    ]
    [(_, materialized)] = derive_ratio_facts([("filing", source)])
    by_code = _by_code(materialized)
    assert by_code["PAT"].status == "EXTRACTED"
    assert by_code["TOP_LINE"].status == "EXTRACTED"
    for code in ("TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES"):
        assert by_code[code].status == "UNIT_NOT_RESOLVED"
        assert by_code[code].normalized_value is None
    assert by_code["ROA"].status == "INSUFFICIENT_INPUT"
    assert by_code["ROE"].status == "INSUFFICIENT_INPUT"
    assert by_code["DEBT_TO_EQUITY"].status == "INSUFFICIENT_INPUT"


def test_stock_statement_scale_disagreement_fails_closed() -> None:
    source = [
        _fact("TOTAL_EQUITY", "5579461", scale=1),
        _fact("TOTAL_LIABILITIES", "159982", scale=1000),
    ]
    [(_, materialized)] = derive_ratio_facts([("filing", source)])
    by_code = _by_code(materialized)
    assert by_code["TOTAL_EQUITY"].status == "UNIT_NOT_RESOLVED"
    assert by_code["TOTAL_LIABILITIES"].status == "UNIT_NOT_RESOLVED"


def test_extreme_npm_is_reviewed_not_published() -> None:
    assert ratio_plausibility_issue("NPM", Decimal("100")) is None
    assert ratio_plausibility_issue("NPM", Decimal("100.01")) is not None
    source = [_fact("PAT", "101"), _fact("TOP_LINE", "1")]
    [(_, materialized)] = derive_ratio_facts([("filing", source)])
    npm = _by_code(materialized)["NPM"]
    assert npm.status == "IMPLAUSIBLE_DERIVED_RATIO"
    assert npm.normalized_value is None


def test_statement_level_conflict_is_owned_by_matching_column() -> None:
    statement = SimpleNamespace(
        header_conflicts=[
            "PERIOD_END_MISMATCH:c3:2026-03-31!=2026-06-30",
            "PERIOD_END_MISMATCH:c4:2025-03-31!=2026-06-30",
        ]
    )
    assert _column_header_conflicts(statement, "c3") == [
        "PERIOD_END_MISMATCH:c3:2026-03-31!=2026-06-30"
    ]


def test_final_eligibility_blocks_statement_owned_header_conflict() -> None:
    entry = LedgerEntry(
        entry_id="A-1",
        tunnel="A",
        concept="TOP_LINE",
        status="unresolved",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        entity="COMPANY",
        period_end="2026-03-31",
        duration_months=3,
        comparison_role="CURRENT",
        unit="LKR",
        scale_factor=1000,
        page=2,
        bbox="(1,2,3,4)",
        label="Revenue",
        score=1.0,
        reasons=[],
        evidence={
            "dimension": "MONETARY",
            "semantic_score": 1.0,
            "column_id": "c3",
            "header_conflicts": [
                "PERIOD_END_MISMATCH:c3:2025-03-31!=2026-03-31"
            ],
        },
    )
    result = evaluate_eligibility(
        entry,
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-03-31",
        concept="TOP_LINE",
    )
    assert not result.eligible
    assert HEADER_CONFLICT in result.reasons
