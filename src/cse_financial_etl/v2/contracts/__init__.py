"""V2 cross-module contracts. Nothing here imports extraction or V1 production code."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.concepts import ConceptCandidate, ConceptCandidateProvider
from cse_financial_etl.v2.contracts.diagnostics import DiagnosticStatuses
from cse_financial_etl.v2.contracts.document import (
    CanonicalDocument,
    CanonicalLine,
    CanonicalPage,
    CanonicalToken,
)
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    ExtractionMode,
    FactKind,
    PublicationStatus,
    ReleaseMode,
    ResolutionStatus,
    ReviewStatus,
    StatementType,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, FactCandidate, SourceFact
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.contracts.release import ReleaseContext, require_release_context
from cse_financial_etl.v2.contracts.statement import (
    CanonicalStatement,
    StatementCell,
    StatementColumn,
    StatementRow,
)

__all__ = [
    "CanonicalDocument",
    "CanonicalLine",
    "CanonicalPage",
    "CanonicalStatement",
    "CanonicalToken",
    "ComparisonRole",
    "ConceptCandidate",
    "ConceptCandidateProvider",
    "DerivedFact",
    "DiagnosticStatuses",
    "EntityScope",
    "ExtractionMode",
    "FactCandidate",
    "FactKind",
    "PublicationStatus",
    "ReleaseContext",
    "ReleaseMode",
    "ResolutionStatus",
    "ReviewStatus",
    "SourceFact",
    "SourceRef",
    "StatementCell",
    "StatementColumn",
    "StatementRow",
    "StatementType",
    "UnitDimension",
    "ValidationStatus",
    "require_release_context",
]
