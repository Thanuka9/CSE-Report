"""Independent diagnostic status dimensions and reason-code containers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import (
    PublicationStatus,
    ResolutionStatus,
    ReviewStatus,
    ValidationStatus,
)


class DiagnosticStatuses(BaseModel):
    """Independent statuses so a secondary failure cannot be hidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    document_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    statement_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    concept_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    entity_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    period_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    duration_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    comparison_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    unit_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
    review_status: ReviewStatus = ReviewStatus.REVIEW
    publication_status: PublicationStatus = PublicationStatus.WITHHELD
    reason_codes: tuple[str, ...] = ()
