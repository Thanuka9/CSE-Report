from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.orchestration.pipeline import (
    RULE_METRICS,
    build_extract_kwargs,
    stamp_validation_status,
)
from cse_financial_etl.validation.equation_engine import ValidationOutcome, ValidationResult


def _fact(code: str, **overrides: object) -> ExtractedFact:
    payload = dict(
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        period_end=date(2026, 6, 30),
        metric_code=code,
        metric_type="MONETARY_ABSOLUTE",
        raw_text="1",
        raw_value=Decimal("1"),
        normalized_value=Decimal("1"),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line=code,
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
        duration_months=3,
        validation_status="NOT_VALIDATED",
        review_status="REVIEW",
    )
    payload.update(overrides)
    return ExtractedFact(**payload)  # type: ignore[arg-type]


def test_build_extract_kwargs_carries_issuer_and_ocr() -> None:
    class Cfg:
        ocr_enabled = True
        keep_review_diagnostics = True
        auto_approve_threshold = 0.95
        manual_review_threshold = 0.8

    kwargs = build_extract_kwargs(
        app_config=Cfg(),
        issuers={"mbsl": "FINANCE_COMPANY"},
        text_cache_dir=__import__("pathlib").Path("ocr"),
        diagnostics_dir=__import__("pathlib").Path("diag"),
        compile_statements=True,
        run_tunnel_b_always=False,
    )
    assert kwargs["issuers"] == {"mbsl": "FINANCE_COMPANY"}
    assert kwargs["ocr_enabled"] is True
    assert kwargs["compile_statements"] is True


def test_stamp_does_not_vacuously_pass_uncovered_metrics() -> None:
    facts = [
        _fact("PAT", validation_status="NOT_VALIDATED"),
        _fact("TOP_LINE", validation_status="NOT_VALIDATED"),
    ]
    results = [
        ValidationResult("BALANCE_SHEET_IDENTITY", ValidationOutcome.PASS, "ok"),
    ]
    stamped = stamp_validation_status(facts, results)
    by_code = {fact.metric_code: fact for fact in stamped}
    assert by_code["PAT"].validation_status == "NOT_VALIDATED"
    assert by_code["TOP_LINE"].validation_status == "NOT_VALIDATED"


def test_stamp_fails_metrics_covered_by_failed_equation() -> None:
    facts = [_fact("TOTAL_ASSETS"), _fact("TOTAL_EQUITY"), _fact("TOTAL_LIABILITIES")]
    results = [ValidationResult("BALANCE_SHEET_IDENTITY", ValidationOutcome.FAIL, "broken")]
    stamped = stamp_validation_status(facts, results)
    assert {fact.validation_status for fact in stamped} == {"FAILED"}
    assert "TOTAL_ASSETS" in RULE_METRICS["BALANCE_SHEET_IDENTITY"]
