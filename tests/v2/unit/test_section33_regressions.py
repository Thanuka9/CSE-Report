from __future__ import annotations

import pytest

from cse_financial_etl.v2.contracts.enums import EntityScope, PublicationStatus, ValidationStatus
from cse_financial_etl.v2.diagnostics.real_filings import (
    load_gold_lock,
    load_real_filing_cases,
    resolve_filing_pdf,
)
from cse_financial_etl.v2.governance.historical_floors import HISTORICAL_MIN_DRAFT_PUBLISHABLE
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline, run_pdf_pipeline
from tests.v2.helpers import geometric_document

NAMED_REGRESSION_PDFS = (
    (
        "ABAN.N0000",
        "data/raw/filings/ABANS_ELECTRICALS_PLC/2026-06-30_642_1786615449693.06.2026.pdf",
    ),
    (
        "CDB.N0000",
        "data/raw/filings/CITIZENS_DEVELOPMENT_BUSINESS_FINANCE_PLC/2026-06-30_981_1785924600634.pdf",
    ),
    (
        "CRL.N0000",
        "data/raw/filings/SOFTLOGIC_FINANCE_PLC/2026-06-30_863_1786010214601.pdf",
    ),
    (
        "AAIC.N0000",
        "data/raw/filings/SOFTLOGIC_LIFE_INSURANCE_PLC/2026-06-30_364_1786443015903. Interim Financial Statements - For the_Period ended 30 June 2026-CSE.pdf",
    ),
)


def _published(facts):
    return [
        fact
        for fact in facts
        if fact.publication_status is not PublicationStatus.WITHHELD
        and fact.validation_status is not ValidationStatus.FAILED
    ]


def test_abans_like_turnover_does_not_invent_company() -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Turnover"), (300.0, "12,345")),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="ABAN.N0000")
    assert _published(facts) == []


def test_unlabeled_finance_issuer_name_does_not_invent_company() -> None:
    document = geometric_document(
        (
            ((40.0, "Lanka Credit and Business Finance PLC"),),
            ((40.0, "Quarter ended 30 June 2026"),),
            ((40.0, "Rs."),),
            ((40.0, "Profit for the period"), (300.0, "12,345")),
        ),
        title="Income statement",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="LCBF.N0000")
    assert _published(facts) == []


def test_cdb_like_finance_page_does_not_invent_company() -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 30-Jun-26"),),
            ((40.0, "Rs 000"),),
            ((40.0, "Income"), (300.0, "8,100")),
            ((40.0, "Profit for the period"), (300.0, "758")),
        ),
        title="Income statement",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="CDB.N0000")
    assert _published(facts) == []


def test_softlogic_like_rs_000_wins_over_eps_per_share() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs 000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
            ((40.0, "Basic earnings per share"), (300.0, "1.25")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="CRL.N0000")
    published = _published(facts)
    pat = next(fact for fact in published if fact.metric_code == "PAT")
    assert pat.normalized_value == pat.raw_value * 1000
    assert pat.entity_scope is EntityScope.COMPANY


@pytest.mark.parametrize("issuer_id, relative", NAMED_REGRESSION_PDFS)
def test_named_cse_pdfs_do_not_invent_company_without_heading(
    issuer_id: str, relative: str
) -> None:
    pdf = resolve_filing_pdf(relative)
    if pdf is None:
        pytest.skip(f"real filing PDF is not present: {relative}")
    statements, facts, _derived, _metrics = run_pdf_pipeline(
        pdf,
        issuer_id=issuer_id,
        filing_version_id=issuer_id,
    )
    company_columns = [
        column
        for statement in statements
        for column in statement.columns
        if column.entity_scope is EntityScope.COMPANY
    ]
    published_company = [
        fact for fact in _published(facts) if fact.entity_scope is EntityScope.COMPANY
    ]
    if not company_columns:
        assert published_company == []


def test_known_timeout_identities_stay_out_of_v2_gold_and_floor_holds() -> None:
    lock = load_gold_lock()
    assert lock.known_timeout_symbols == ("SDF.N0000", "RENU.N0000")
    assert HISTORICAL_MIN_DRAFT_PUBLISHABLE == 8924
    scoring = load_real_filing_cases(limit=40, locked=True)
    regression = load_real_filing_cases(limit=10, locked=True, include_regression=True)
    assert all(case.issuer_id not in lock.known_timeout_symbols for case in (*scoring, *regression))
