"""Concept-matching contracts. Semantic truth lives in one registry (Phase 7)."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import AccountingRegime, MatchKind, ResolutionStatus
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.contracts.statement import StatementRow


class ConceptCandidate(BaseModel):
    """A possible metric mapping for a statement row. Not publication truth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    metric_code: str | None = None
    match_kind: MatchKind
    score: float | None = Field(
        default=None,
        description="Diagnostic only. Must not decide publication truth alone.",
    )
    source_concept: str | None = Field(
        default=None,
        description="Matched source label/alias. Distinct from canonical metric_code.",
    )
    matched_alias: str | None = None
    accounting_regime: AccountingRegime | None = Field(
        default=None,
        description="Proven reporting regime only. INSURANCE issuer class is not SLFRS4/17.",
    )
    accounting_regime_status: ResolutionStatus = ResolutionStatus.NOT_APPLICABLE
    evidence: tuple[SourceRef, ...] = ()


class ConceptCandidateProvider(Protocol):
    """Extension point for later embedding models. Downstream contracts stay stable."""

    def candidates(self, row: StatementRow) -> list[ConceptCandidate]: ...
