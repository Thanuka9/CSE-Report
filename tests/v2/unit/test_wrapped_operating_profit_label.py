"""Wrapped income-statement labels and bank OP-before-VAT ownership."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.statements.table_reconstructor import _merged_label
from tests.v2.helpers import geometric_document


def test_merged_label_joins_incomplete_pending_wrap() -> None:
    pending = "Profit before value added tax (VAT) & social security"
    cont = "contribution Levy (SSCL) on financial services"
    merged = _merged_label(pending, cont)
    assert merged.startswith("Profit before value added tax")
    assert "contribution Levy (SSCL) on financial services" in merged


def test_merged_label_joins_lowercase_continuation() -> None:
    assert (
        _merged_label("Profit before taxation", "from continuing operations")
        == "Profit before taxation from continuing operations"
    )


def test_merged_label_does_not_glue_new_account_row() -> None:
    assert _merged_label("Profit before tax", "VAT on financial services") == (
        "VAT on financial services"
    )


def test_bank_profit_before_vat_sscl_is_operating_profit_q4() -> None:
    """Bank Q4 OP may be the pre-VAT/SSCL line when that is the reported source concept."""

    document = geometric_document(
        (
            ((180.0, "Bank"), (320.0, "Bank"), (460.0, "Group"), (600.0, "Group")),
            (
                (40.0, "For the year / quarter ended 31 December"),
                (180.0, "2025"),
                (240.0, "2024"),
                (300.0, "2025"),
                (360.0, "2024"),
                (460.0, "2025"),
                (520.0, "2024"),
                (600.0, "2025"),
                (660.0, "2024"),
            ),
            ((40.0, "LKR '000"),),
            (
                (40.0, "Results from operating activities"),
                (180.0, "1,840,423"),
                (240.0, "1,208,195"),
                (300.0, "733,950"),
                (360.0, "425,172"),
                (460.0, "2,192,487"),
                (520.0, "1,370,105"),
                (600.0, "831,298"),
                (660.0, "487,590"),
            ),
            ((40.0, "Profit before value added tax (VAT) & social security"),),
            (
                (40.0, "contribution Levy (SSCL) on financial services"),
                (180.0, "1,927,075"),
                (240.0, "1,206,724"),
                (300.0, "748,922"),
                (360.0, "433,689"),
                (460.0, "2,192,487"),
                (520.0, "1,370,105"),
                (600.0, "831,298"),
                (660.0, "487,590"),
            ),
        ),
        title="Statement of Profit or Loss",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="SYNTH.N0000", issuer_type="BANK"
    )
    hits = [
        f
        for f in facts
        if f.metric_code == "OPERATING_PROFIT"
        and f.entity_scope is EntityScope.BANK
        and f.normalized_value == Decimal("748922000")
        and f.duration_months == 3
        and f.comparison_role is ComparisonRole.CURRENT
    ]
    assert hits, (
        "Wrapped Profit-before-VAT/SSCL Bank Q4 must resolve as OPERATING_PROFIT; "
        f"got {[ (f.entity_scope, str(f.normalized_value), f.duration_months) for f in facts if f.metric_code=='OPERATING_PROFIT']}"
    )
