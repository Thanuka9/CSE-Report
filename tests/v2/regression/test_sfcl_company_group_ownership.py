"""Permanent real-PDF regression: SFCL Company/Group column ownership (N03).

After N03 truth correction, holdout TOP_LINE/PAT are COMPANY column values.
GROUP sibling CURRENT cells are asserted when V2 extracts GROUP facts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope
from cse_financial_etl.v2.diagnostics.real_filings import resolve_filing_pdf
from cse_financial_etl.v2.document.native_reader import sha256_file
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline

PDF_RELATIVE = (
    "data/raw/filings/SENKADAGALA_FINANCE_COMPANY_PLC/2025-12-31_441_1770976920300.pdf"
)
PDF_SHA256 = "3095172f49c02bacff501b3b320e5e2a60ac8d321361a298ede007f13d6f4285"
ISSUER_ID = "SFCL.N0000"
FILING_VERSION_ID = "SFCL.N0000-2025-12-31"

COMPANY_CURRENT = (
    ("TOP_LINE", Decimal("2572716568")),
    ("PAT", Decimal("344406148")),
)
GROUP_SIBLINGS = (
    ("TOP_LINE", Decimal("2664529998")),
    ("PAT", Decimal("390951093")),
)


def _resolve_sfcl_pdf():
    pdf = resolve_filing_pdf(PDF_RELATIVE)
    if pdf is None:
        pytest.skip(f"real filing PDF is not present: {PDF_RELATIVE}")
    assert sha256_file(pdf) == PDF_SHA256, f"unexpected PDF identity for {PDF_RELATIVE}"
    return pdf


def _run_sfcl():
    return run_pdf_pipeline(
        _resolve_sfcl_pdf(),
        issuer_id=ISSUER_ID,
        filing_version_id=FILING_VERSION_ID,
        issuer_name="SENKADAGALA FINANCE COMPANY PLC",
        issuer_type="FINANCE_COMPANY",
    )


def _matching_facts(facts, *, metric_code: str, entity: EntityScope, expected: Decimal):
    return [
        fact
        for fact in facts
        if fact.metric_code == metric_code
        and fact.entity_scope is entity
        and fact.normalized_value == expected
        and fact.comparison_role is ComparisonRole.CURRENT
    ]


@pytest.mark.parametrize(
    "metric_code, expected",
    COMPANY_CURRENT,
    ids=[metric for metric, _expected in COMPANY_CURRENT],
)
def test_sfcl_company_current_source_facts(metric_code: str, expected: Decimal) -> None:
    _statements, facts, _derived, _metrics = _run_sfcl()
    matches = _matching_facts(
        facts, metric_code=metric_code, entity=EntityScope.COMPANY, expected=expected
    )
    assert matches, (
        f"{ISSUER_ID} {metric_code} COMPANY {expected} missing from "
        f"{[(f.entity_scope, str(f.normalized_value)) for f in facts if f.metric_code == metric_code]}"
    )


@pytest.mark.parametrize(
    "metric_code, expected",
    GROUP_SIBLINGS,
    ids=[metric for metric, _expected in GROUP_SIBLINGS],
)
def test_sfcl_group_sibling_current_source_facts(metric_code: str, expected: Decimal) -> None:
    _statements, facts, _derived, _metrics = _run_sfcl()
    group_current = [
        fact
        for fact in facts
        if fact.metric_code == metric_code
        and fact.entity_scope is EntityScope.GROUP
        and fact.comparison_role is ComparisonRole.CURRENT
    ]
    if not group_current:
        pytest.skip(f"V2 did not extract GROUP {metric_code} CURRENT SourceFacts")
    matches = _matching_facts(
        facts, metric_code=metric_code, entity=EntityScope.GROUP, expected=expected
    )
    assert matches, (
        f"{ISSUER_ID} {metric_code} GROUP sibling {expected} missing from "
        f"{[str(f.normalized_value) for f in group_current]}"
    )
