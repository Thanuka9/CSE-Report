from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import (
    AdjudicationStatus,
    ComparisonRole,
    EntityScope,
    EvidenceLevel,
    SourcePresence,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.investigation import SourceTruthItem
from cse_financial_etl.v2.diagnostics.t10_score import score_t10_items


def _item(**kwargs: object) -> SourceTruthItem:
    payload = {
        "filing_version_id": "CIC.N0000-2025-12-31",
        "pdf_sha256": "a" * 64,
        "issuer_id": "CIC.N0000",
        "metric_code": "PAT",
        "source_presence": SourcePresence.REPORTED,
        "normalized_value": Decimal("300790000"),
        "entity_scope": EntityScope.COMPANY,
        "period_end": "2025-12-31",
        "duration_months": 3,
        "comparison_role": ComparisonRole.CURRENT,
        "currency": "LKR",
        "scale": Decimal("1000000"),
        "unit_dimension": UnitDimension.MONETARY,
        "page": 2,
        "evidence_level": EvidenceLevel.CELL_EXPLICIT,
        "reviewer_1": "t10-blind-pdf-review",
        "adjudication_status": AdjudicationStatus.REVIEWER_1_COMPLETE,
        "split": "DEV",
        **kwargs,
    }
    return SourceTruthItem.model_validate(payload)


def test_t10_score_matches_value_and_entity() -> None:
    items = [_item()]
    facts = [
        {
            "issuer_id": "CIC.N0000",
            "metric_code": "PAT",
            "normalized_value": "300790000",
            "entity_scope": "COMPANY",
            "duration_months": 3,
        }
    ]
    payload = score_t10_items(items, facts)
    assert payload["tp"] == 1
    assert payload["fn"] == 0
    assert payload["gates"]["G09"]["decision"] == "KEEP"
    assert payload["gates"]["G01"]["decision"] == "KEEP"
    assert payload["gates"]["G02"]["decision"] == "UNTESTED"


def test_t10_score_unlabeled_reported_is_g01_withheld() -> None:
    items = [_item(issuer_id="CTC.N0000", entity_scope=None, metric_code="TOTAL_ASSETS")]
    payload = score_t10_items(items, [])
    assert payload["g01_withheld"] == 1
    assert payload["fn"] == 0
    assert payload["tp"] == 0


def test_t10_score_rejects_invented_entity_on_unlabeled_truth() -> None:
    items = [_item(issuer_id="CTC.N0000", entity_scope=None, metric_code="TOTAL_ASSETS")]
    facts = [
        {
            "issuer_id": "CTC.N0000",
            "metric_code": "TOTAL_ASSETS",
            "normalized_value": "300790000",
            "entity_scope": "COMPANY",
            "duration_months": None,
        }
    ]
    payload = score_t10_items(items, facts)
    assert payload["tp"] == 0
    assert payload["value_or_entity_mismatch"] == 1
