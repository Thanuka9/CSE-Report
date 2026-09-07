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


@dataclass
class StatementRow:
    row_id: str
    raw_label: str
    normalized_label: str
    indentation_level: int
    parent_section: str | None
    cells: dict[str, StatementCell]
    hypotheses: list[ConceptHypothesis] = field(default_factory=list)


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
