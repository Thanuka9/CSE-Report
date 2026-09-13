"""Build CanonicalStatement objects from detected regions."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.statement import CanonicalStatement
from cse_financial_etl.v2.statements.detector import StatementRegion, detect_statement_regions
from cse_financial_etl.v2.statements.table_reconstructor import reconstruct_statements


def build_statements(document: CanonicalDocument) -> tuple[CanonicalStatement, ...]:
    regions: tuple[StatementRegion, ...] = detect_statement_regions(document)
    return reconstruct_statements(document, regions)
