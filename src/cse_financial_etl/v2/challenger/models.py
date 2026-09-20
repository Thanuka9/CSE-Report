"""Challenger-only V1 physical source observation contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.provenance import SourceRef


class V1SourceObservation(BaseModel):
    """One PDF-anchored cell observation recovered by the V1 physical reader.

    Context dimensions may be unresolved. Observations without a verifiable
    SourceRef bbox remain ``DISCOVERY_ONLY`` and must never be publishable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    observation_id: str
    reader_id: str = "v1_physical_table_reconstructor"
    reader_version: str = "1"
    source_ref: SourceRef
    statement_hint: str | None = None
    table_id: str
    row_index: int
    col_index: int
    row_label: str
    raw_text: str
    raw_value: Decimal | None = None
    entity_scope: EntityScope | None = None
    period_end: date | None = None
    duration_months: int | None = None
    comparison_role: ComparisonRole | None = None
    currency: str | None = None
    monetary_scale: Decimal | None = None
    unit_dimension: UnitDimension | None = None
    concept_hint: str | None = None
    publishable: bool = False
    reason_codes: tuple[str, ...] = ()
    evidence_notes: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def discovery_only(self) -> bool:
        return (
            (not self.publishable)
            or self.source_ref.bbox is None
            or "DISCOVERY_ONLY" in self.reason_codes
        )
