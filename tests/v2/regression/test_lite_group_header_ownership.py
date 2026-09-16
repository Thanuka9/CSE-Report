"""Permanent real-PDF regression: LITE Group header ownership (N02 / F1).

Expects SourceFacts for page-5 Group CURRENT cells once F1 is present
(entity-bearing statement subtitles retained in heading context). Duration=3
is F3 and is intentionally not asserted here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope
from cse_financial_etl.v2.diagnostics.real_filings import resolve_filing_pdf
from cse_financial_etl.v2.document.native_reader import sha256_file
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline, run_pdf_pipeline
from tests.v2.helpers import geometric_document

PDF_RELATIVE = "data/raw/filings/LAXAPANA_PLC/2025-12-31_498_1770114354483.pdf"
PDF_SHA256 = "20151678333c62bbb416d9dfb8bdd2e1def27a181d38fc152be0ffbcdc1845f4"
ISSUER_ID = "LITE.N0000"
FILING_VERSION_ID = "LITE.N0000-2025-12-31"

GROUP_CURRENT = (
    ("TOP_LINE", Decimal("889239000")),
    ("OPERATING_PROFIT", Decimal("156042000")),
    ("PAT", Decimal("79190000")),
)


def _matching_group_current(facts, *, metric_code: str, expected: Decimal):
    return [
        fact
        for fact in facts
        if fact.metric_code == metric_code
        and fact.entity_scope is EntityScope.GROUP
        and fact.normalized_value == expected
        and fact.comparison_role is ComparisonRole.CURRENT
    ]


def test_geometric_group_subtitle_admits_group_source_facts() -> None:
    """Synthetic stand-in for the LITE subtitle shape that F1 must keep."""
    document = geometric_document(
        (
            ((40.0, "Comprehensive Income - Group 31st December 2025"),),
            ((40.0, "For the three months ended 31 December 2025"),),
            ((40.0, "Rs.'000"),),
            ((40.0, "Revenue"), (220.0, "889,239")),
            ((40.0, "Profit from Operating Activities"), (220.0, "156,042")),
            ((40.0, "Net Profit for the Period"), (220.0, "79,190")),
        ),
        title="Statement of Profit or Loss and Other",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id=ISSUER_ID
    )
    for metric_code, expected in GROUP_CURRENT:
        assert _matching_group_current(facts, metric_code=metric_code, expected=expected), (
            f"missing GROUP {metric_code}={expected}"
        )


@pytest.mark.parametrize(
    "metric_code, expected",
    GROUP_CURRENT,
    ids=[metric for metric, _expected in GROUP_CURRENT],
)
def test_lite_real_pdf_group_source_facts(metric_code: str, expected: Decimal) -> None:
    pdf = resolve_filing_pdf(PDF_RELATIVE)
    if pdf is None:
        pytest.skip(f"real filing PDF is not present: {PDF_RELATIVE}")
    assert sha256_file(pdf) == PDF_SHA256, f"unexpected PDF identity for {PDF_RELATIVE}"
    _statements, facts, _derived, _metrics = run_pdf_pipeline(
        pdf,
        issuer_id=ISSUER_ID,
        filing_version_id=FILING_VERSION_ID,
        issuer_name="LAXAPANA PLC",
        issuer_type="GENERAL",
    )
    matches = _matching_group_current(facts, metric_code=metric_code, expected=expected)
    assert matches, (
        f"{ISSUER_ID} {metric_code} GROUP {expected} missing from "
        f"{[(f.entity_scope, str(f.normalized_value), f.comparison_role) for f in facts if f.metric_code == metric_code]}"
    )
