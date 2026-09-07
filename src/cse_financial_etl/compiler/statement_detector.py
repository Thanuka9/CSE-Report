"""Statement discovery engine wrapper (§9)."""

from __future__ import annotations

from cse_financial_etl.document.document_ir import CanonicalDocumentIR
from cse_financial_etl.document.region_detector import StatementRegion, detect_regions


def detect_statements(document: CanonicalDocumentIR) -> list[StatementRegion]:
    return detect_regions(document)
