"""Canonical financial statement IR (§14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from cse_financial_etl.accounting.semantic_candidates import ConceptHypothesis
from cse_financial_etl.compiler.column_compiler import StatementColumn
from cse_financial_etl.document.document_ir import BBox


@dataclass(frozen=True, slots=True)
class StatementCell:
    raw_text: str
    raw_numeric: Decimal | None
    normalized_value: Decimal | None
    source_page: int
    source_bbox: BBox
    column_id: str
    effective_unit_evidence_ids: tuple[str, ...] = ()
    unit_override: dict[str, Any] | None = None
    coordinate_transform_id: str | None = None
    # Dimension-typed normalization: decided before any scaling is applied.
    dimension_values: dict[str, Decimal | None] = field(default_factory=dict)
    unit_resolutions: dict[str, dict[str, Any]] = field(default_factory=dict)
    primary_dimension: str | None = None

    def value_for(self, dimension: str) -> Decimal | None:
        if dimension in self.dimension_values:
            return self.dimension_values[dimension]
        return None

    def unit_for(self, dimension: str) -> dict[str, Any] | None:
        return self.unit_resolutions.get(dimension)


@dataclass
class StatementRow:
    row_id: str
    raw_label: str
    normalized_label: str
    indentation_level: int
    parent_section: str | None
    cells: dict[str, StatementCell]
    hypotheses: list[ConceptHypothesis] = field(default_factory=list)
    source_line_ids: tuple[str, ...] = ()
    row_unit_evidence: list[dict[str, Any]] = field(default_factory=list)
    dimension_hint: str | None = None


@dataclass
class CanonicalFinancialStatement:
    issuer_id: str
    source_sha256: str
    statement_type: str
    columns: list[StatementColumn]
    rows: list[StatementRow]
    unit_evidence: list[dict[str, Any]] = field(default_factory=list)
    compilation_evidence: dict[str, Any] = field(default_factory=dict)
    page_start: int | None = None
    page_end: int | None = None
    table_index: int = 0
    header_conflicts: list[str] = field(default_factory=list)

    @property
    def value_columns(self) -> list[StatementColumn]:
        return [c for c in self.columns if c.kind == "VALUE"]
