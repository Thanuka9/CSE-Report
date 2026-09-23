from __future__ import annotations

from cse_financial_etl.v2.diagnostics.discovery import discover_exact_aliases
from tests.v2.helpers import geometric_document


def test_whole_pdf_discovery_finds_exact_pat_alias_without_publishing() -> None:
    document = geometric_document(
        (
            ((40.0, "Notes to the financial statements"),),
            ((40.0, "Profit for the period"),),
        ),
        title="Notes",
    )
    hits = discover_exact_aliases(document, issuer_id="issuer-1", issuer_type="GENERAL")
    assert any(item["metric_code"] == "PAT" for item in hits)
