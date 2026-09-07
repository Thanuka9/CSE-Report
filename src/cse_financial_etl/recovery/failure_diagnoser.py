"""Dimension-specific failure tickets (§31)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FAILURE_FAMILIES = (
    "STATEMENT_REGION_CONFLICT",
    "TABLE_BOUNDARY_CONFLICT",
    "ROW_RECONSTRUCTION_CONFLICT",
    "HEADER_TREE_CONFLICT",
    "ENTITY_CONFLICT",
    "PERIOD_CONFLICT",
    "DURATION_CONFLICT",
    "CURRENT_COMPARATIVE_CONFLICT",
    "UNIT_CONFLICT",
    "NUMERIC_PARSE_CONFLICT",
    "SEMANTIC_CONFLICT",
    "SUBTOTAL_CONFLICT",
    "FORMULA_CONTRADICTION",
    "CROSS_COLUMN_CONTRADICTION",
    "CROSS_FILING_CONTRADICTION",
    "OCR_QUALITY_FAILURE",
    "SOURCE_DISCLOSURE_REVIEW_REQUIRED",
    "SEARCH_BUDGET_EXHAUSTED",
    "SEARCH_INCOMPLETE",
)


@dataclass
class FailureTicket:
    ticket_id: str
    concept: str
    family: str
    dimension: str
    detail: str
    recovery_routes: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    terminal_status: str | None = None


def diagnose_failures(
    unresolved_concepts: dict[str, list[str]],
) -> list[FailureTicket]:
    tickets: list[FailureTicket] = []
    for concept, reasons in unresolved_concepts.items():
        family, dimension = _classify(reasons)
        tickets.append(
            FailureTicket(
                ticket_id=f"{concept}:{family}",
                concept=concept,
                family=family,
                dimension=dimension,
                detail="; ".join(reasons) or "unresolved",
                recovery_routes=_routes_for(family),
            )
        )
    return tickets


def _classify(reasons: list[str]) -> tuple[str, str]:
    joined = " ".join(reasons).upper()
    mapping = (
        ("GROUP", "ENTITY_CONFLICT", "entity"),
        ("ENTITY", "ENTITY_CONFLICT", "entity"),
        ("YTD", "DURATION_CONFLICT", "duration"),
        ("3M", "DURATION_CONFLICT", "duration"),
        ("DURATION", "DURATION_CONFLICT", "duration"),
        ("COMPARATIVE", "CURRENT_COMPARATIVE_CONFLICT", "column"),
        ("PERIOD", "PERIOD_CONFLICT", "period"),
        ("UNIT", "UNIT_CONFLICT", "unit"),
        ("BUDGET", "SEARCH_BUDGET_EXHAUSTED", "concept"),
        ("OCR", "OCR_QUALITY_FAILURE", "numeric"),
        ("FORMULA", "FORMULA_CONTRADICTION", "accounting"),
    )
    for needle, family, dimension in mapping:
        if needle in joined:
            return family, dimension
    return "SEMANTIC_CONFLICT", "concept"


def _routes_for(family: str) -> list[str]:
    routes = {
        "ENTITY_CONFLICT": ["entity_recovery"],
        "DURATION_CONFLICT": ["period_recovery"],
        "PERIOD_CONFLICT": ["period_recovery"],
        "UNIT_CONFLICT": ["unit_recovery"],
        "NUMERIC_PARSE_CONFLICT": ["numeric_recovery"],
        "OCR_QUALITY_FAILURE": ["ocr_recovery", "numeric_recovery"],
        "TABLE_BOUNDARY_CONFLICT": ["structural_recovery"],
        "HEADER_TREE_CONFLICT": ["structural_recovery", "entity_recovery"],
        "ROW_RECONSTRUCTION_CONFLICT": ["structural_recovery"],
        "SEMANTIC_CONFLICT": ["semantic_recovery"],
        "FORMULA_CONTRADICTION": ["semantic_recovery"],
        "CURRENT_COMPARATIVE_CONFLICT": ["period_recovery", "structural_recovery"],
    }
    return routes.get(family, ["semantic_recovery", "structural_recovery"])
