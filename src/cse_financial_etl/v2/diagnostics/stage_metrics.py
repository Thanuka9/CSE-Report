"""Stage-level diagnostic counters. Independent context rates are not a chain."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import SCHEMA_VERSION


class StageMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    filings_available: int = 0
    documents_parsed: int = 0
    statements_detected: int = 0
    source_numeric_cells: int = 0
    concept_candidates: int = 0
    entity_resolved_candidates: int = 0
    period_resolved_candidates: int = 0
    duration_resolved_candidates: int = 0
    comparison_resolved_candidates: int = 0
    unit_resolved_candidates: int = 0
    source_facts: int = 0
    validated_facts: int = 0
    draft_eligible_facts: int = 0
    pivot_facts: int = 0
    numeric_workbook_cells: int = 0
    extra: dict[str, int] = Field(default_factory=dict)
