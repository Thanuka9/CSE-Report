"""Source and derived fact contracts. Derived facts must never masquerade as source."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import (
    AccountingRegime,
    ComparisonRole,
    EntityScope,
    FactKind,
    PublicationStatus,
    ResolutionStatus,
    ReviewStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.exceptions import MissingProvenanceError


class FactCandidate(BaseModel):
    """Fully contextualized cell/row/column candidate before deterministic resolution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    candidate_id: str
    statement_id: str
    cell_id: str
    row_id: str
    column_id: str
    concept: ConceptCandidate | None = None
    concept_alternatives: tuple[ConceptCandidate, ...] = ()
    concept_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    entity_scope: EntityScope | None = None
    entity_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    period_end: date | None = None
    period_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    duration_months: int | None = None
    duration_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    comparison_role: ComparisonRole | None = None
    comparison_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    currency: str | None = None
    monetary_scale: Decimal | None = None
    unit_dimension: UnitDimension | None = None
    unit_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    raw_value: Decimal | None = None
    source_ref: SourceRef
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _provenance_required(self) -> FactCandidate:
        if not self.source_ref.source_sha256:
            raise MissingProvenanceError("FactCandidate requires a source SHA-256")
        return self

    def required_context_resolved(self) -> bool:
        return (
            self.concept_status == ResolutionStatus.RESOLVED
            and self.entity_status == ResolutionStatus.RESOLVED
            and self.period_status == ResolutionStatus.RESOLVED
            and self.unit_status == ResolutionStatus.RESOLVED
        )


class SourceFact(BaseModel):
    """A published-capable source fact retaining complete source identity.

    No publication-specific mutation should alter this object. Release mode is
    applied by a view that receives an explicit ReleaseContext.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    fact_kind: Literal[FactKind.SOURCE] = FactKind.SOURCE
    fact_id: str
    filing_version_id: str
    statement_id: str
    cell_id: str
    issuer_id: str
    metric_code: str
    source_concept: str | None = None
    matched_alias: str | None = None
    accounting_regime: AccountingRegime | None = None
    accounting_regime_status: ResolutionStatus = ResolutionStatus.NOT_APPLICABLE
    entity_scope: EntityScope
    period_end: date
    duration_months: int | None = None
    comparison_role: ComparisonRole
    raw_value: Decimal
    normalized_value: Decimal
    currency: str | None = None
    source_scale: Decimal | None = None
    unit_dimension: UnitDimension
    source_ref: SourceRef
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
    review_status: ReviewStatus = ReviewStatus.REVIEW
    publication_status: PublicationStatus = PublicationStatus.WITHHELD
    document_status: ResolutionStatus = ResolutionStatus.RESOLVED
    statement_status: ResolutionStatus = ResolutionStatus.RESOLVED
    concept_status: ResolutionStatus = ResolutionStatus.RESOLVED
    entity_status: ResolutionStatus = ResolutionStatus.RESOLVED
    period_status: ResolutionStatus = ResolutionStatus.RESOLVED
    duration_status: ResolutionStatus = ResolutionStatus.NOT_APPLICABLE
    comparison_status: ResolutionStatus = ResolutionStatus.RESOLVED
    unit_status: ResolutionStatus = ResolutionStatus.RESOLVED
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _provenance_and_identity(self) -> SourceFact:
        if not self.source_ref.source_sha256:
            raise MissingProvenanceError("SourceFact requires a source SHA-256")
        if self.entity_scope == EntityScope.UNKNOWN:
            raise ValueError("SourceFact cannot store UNKNOWN entity_scope; withhold instead")
        if self.fact_kind != FactKind.SOURCE:
            raise ValueError("SourceFact.fact_kind must remain SOURCE")
        return self


class DerivedFact(BaseModel):
    """A formula output. It is never a source cell and has no source cell_id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    fact_kind: Literal[FactKind.DERIVED] = FactKind.DERIVED
    fact_id: str
    issuer_id: str
    metric_code: str
    formula_id: str
    input_fact_ids: tuple[str, ...] = Field(min_length=1)
    normalized_value: Decimal
    entity_scope: EntityScope
    period_end: date
    duration_months: int | None = None
    comparison_role: ComparisonRole
    unit_dimension: UnitDimension
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
    review_status: ReviewStatus = ReviewStatus.REVIEW
    publication_status: PublicationStatus = PublicationStatus.WITHHELD
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _derived_identity(self) -> DerivedFact:
        if self.fact_kind != FactKind.DERIVED:
            raise ValueError("DerivedFact.fact_kind must remain DERIVED")
        return self
