"""Investigation contracts: source truth is not publication policy.

These models record what a filing establishes, or why a candidate stopped,
without changing extraction behaviour.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import (
    AdjudicationStatus,
    ComparisonRole,
    EntityScope,
    EvidenceLevel,
    FirstFailureStage,
    PublicationStatus,
    ResolutionStatus,
    SourcePresence,
    UnitDimension,
    ValidationStatus,
)

SOURCE_TARGET_METRICS: tuple[str, ...] = (
    "PAT",
    "PBT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "NAVPS",
    "OPERATING_PROFIT",
    "TOTAL_EQUITY",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOP_LINE",
)

DERIVED_METRICS: tuple[str, ...] = (
    "EPS_SELECTED",
    "LIABILITIES_TO_EQUITY",
    "ROE",
    "ROA",
    "NPM",
)

MARKET_METRICS: tuple[str, ...] = ("LAST_TRADED_PRICE",)


class SourceTruthItem(BaseModel):
    """Blind source adjudication row. Must not encode current V1/V2 gate decisions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    filing_version_id: str
    pdf_sha256: str
    issuer_id: str
    metric_code: str
    source_presence: SourcePresence
    raw_source_label: str | None = None
    raw_source_value: str | None = None
    normalized_value: Decimal | None = None
    entity_scope: EntityScope | None = None
    period_end: date | None = None
    duration_months: int | None = None
    comparison_role: ComparisonRole | None = None
    currency: str | None = None
    scale: Decimal | None = None
    unit_dimension: UnitDimension | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    evidence_text: str | None = None
    evidence_level: EvidenceLevel
    reviewer_1: str | None = None
    reviewer_2: str | None = None
    adjudication_status: AdjudicationStatus = AdjudicationStatus.NOT_STARTED
    notes: str | None = None
    split: Literal["DEV", "HOLDOUT"] | None = None


class SourceManifestRow(BaseModel):
    """Frozen input identity for V1/V2 comparison on the same PDF SHA set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    filing_version_id: str
    issuer_id: str
    symbol: str
    period: date | None = None
    local_file: str
    pdf_sha256: str
    file_size: int
    page_count: int | None = None
    source_acquisition_timestamp: str | None = None
    revision_identifier: str | None = None


class CandidateTrace(BaseModel):
    """One diagnostic row per numeric candidate. Rejected candidates must remain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    run_id: str | None = None
    code_sha: str | None = None
    pdf_sha: str
    filing_version_id: str
    issuer_id: str
    sector: str | None = None
    regime: str | None = None
    page: int
    statement_id: str
    statement_type: str | None = None
    table_id: str | None = None
    row_id: str
    row_label: str
    cell_id: str
    raw_numeric_text: str | None = None
    parsed_numeric_value: Decimal | None = None
    page_classification: str | None = None
    statement_detection_status: str | None = None
    table_reconstruction_status: str | None = None
    row_reconstruction_status: str | None = None
    concept_candidates: tuple[str, ...] = ()
    concept_status: ResolutionStatus
    entity_status: ResolutionStatus
    period_status: ResolutionStatus
    duration_status: ResolutionStatus
    comparison_status: ResolutionStatus
    unit_status: ResolutionStatus
    resolved_metric: str | None = None
    entity_scope: EntityScope | None = None
    period_end: date | None = None
    duration_months: int | None = None
    comparison_role: ComparisonRole | None = None
    currency: str | None = None
    scale: Decimal | None = None
    unit_dimension: UnitDimension | None = None
    source_ref_sha256: str
    header_evidence: str | None = None
    unit_evidence: str | None = None
    reason_codes: tuple[str, ...] = ()
    source_fact_created: bool
    validation_status: ValidationStatus | None = None
    production_selected: bool | None = None
    publication_status: PublicationStatus | None = None
    first_failure_stage: FirstFailureStage
    extra: dict[str, str] = Field(default_factory=dict)
