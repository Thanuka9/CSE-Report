from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import DisagreementClass, EntityScope
from cse_financial_etl.v2.diagnostics.issue_ledger import build_issue_ledger
from tests.v2.helpers import source_fact


def test_v1_only_is_reference_disagreement_not_truth() -> None:
    v1 = [
        {
            "metric_code": "PAT",
            "entity_scope": "COMPANY",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "normalized_value": "1234000",
            "comparison_role": "CURRENT",
            "source_page": 1,
        }
    ]
    rows = build_issue_ledger(
        pdf_sha="a" * 64,
        issuer="JKH.N0000",
        sector="HOLDING",
        v1_rows=v1,
        v2_facts=(),
    )
    assert len(rows) == 1
    assert rows[0].disagreement_class is DisagreementClass.REFERENCE_ONLY_DISAGREEMENT
    assert rows[0].source_truth_status == "NOT_ADJUDICATED"


def test_matching_values_are_agreement() -> None:
    fact = source_fact(entity_scope=EntityScope.COMPANY)
    v1 = [
        {
            "metric_code": "PAT",
            "entity_scope": "COMPANY",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "normalized_value": "1234000",
            "comparison_role": "CURRENT",
            "source_page": 1,
        }
    ]
    rows = build_issue_ledger(
        pdf_sha="a" * 64,
        issuer="issuer-1",
        sector="GENERAL",
        v1_rows=v1,
        v2_facts=(fact,),
    )
    assert rows[0].disagreement_class is DisagreementClass.AGREEMENT
