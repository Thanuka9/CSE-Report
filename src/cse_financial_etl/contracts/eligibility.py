"""Shared publication-eligibility contract.

One rule set decides whether a ledger candidate can be published for a target query.
The arbiter uses it to filter candidates and the final validator re-runs it independently
on chosen evidence. Missing or weak evidence stays unresolved; scoring never converts an
unproven dimension into a fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from cse_financial_etl.accounting.concept_rules import (
    group_cannot_satisfy_company,
    requires_exact_3m,
)
from cse_financial_etl.compiler.units import COUNT, PER_SHARE, concept_dimension

VALUE_MISSING = "VALUE_MISSING"
ENTITY_UNKNOWN = "ENTITY_UNKNOWN"
GROUP_CANNOT_SATISFY_COMPANY = "GROUP_CANNOT_SATISFY_COMPANY"
ENTITY_MISMATCH = "ENTITY_MISMATCH"
PERIOD_UNKNOWN = "PERIOD_UNKNOWN"
PERIOD_MISMATCH = "PERIOD_MISMATCH"
DURATION_UNKNOWN = "DURATION_UNKNOWN"
YTD_CANNOT_SATISFY_3M = "YTD_CANNOT_SATISFY_3M"
ROLE_UNKNOWN = "ROLE_UNKNOWN"
COMPARATIVE_NOT_CURRENT = "COMPARATIVE_NOT_CURRENT"
UNIT_UNRESOLVED = "UNIT_UNRESOLVED"
SCALE_UNRESOLVED = "SCALE_UNRESOLVED"
DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
SOURCE_EVIDENCE_MISSING = "SOURCE_EVIDENCE_MISSING"
HEADER_CONFLICT = "HEADER_CONFLICT"
DERIVED_LIABILITIES_FORBIDDEN = "DERIVED_LIABILITIES_FORBIDDEN"
VALIDATION_FAILED_PRESERVED = "VALIDATION_FAILED_PRESERVED"
LABEL_EVIDENCE_WEAK = "LABEL_EVIDENCE_WEAK"
STATEMENT_REGION_UNKNOWN = "STATEMENT_REGION_UNKNOWN"
STATEMENT_REGION_WEAK = "STATEMENT_REGION_WEAK"

MIN_PUBLISHABLE_SEMANTIC_SCORE = 0.80
MIN_PUBLISHABLE_REGION_CONFIDENCE = 0.80


@runtime_checkable
class CandidateLike(Protocol):
    concept: str
    normalized_value: Decimal | None
    entity: str | None
    period_end: str | None
    duration_months: int | None
    comparison_role: str | None
    unit: str | None
    scale_factor: int | None
    page: int | None
    label: str | None
    reasons: list[str]
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]
    concept: str

    @property
    def primary_reason(self) -> str | None:
        return self.reasons[0] if self.reasons else None


@dataclass(frozen=True, slots=True)
class FinalCheck:
    metric_code: str
    status: str
    detail: str
    reasons: tuple[str, ...] = ()


def evaluate_eligibility(
    entry: CandidateLike | None,
    *,
    required_entity: str,
    target_duration: int | None,
    target_period_end: str | None,
    concept: str | None = None,
) -> EligibilityResult:
    """Full fail-closed eligibility contract for one candidate and target query."""

    if entry is None:
        return EligibilityResult(False, (VALUE_MISSING,), concept or "UNKNOWN")
    concept = concept or entry.concept
    reasons: list[str] = []
    evidence = entry.evidence if isinstance(entry.evidence, dict) else {}

    if entry.normalized_value is None:
        reasons.append(VALUE_MISSING)

    entity = entry.entity
    if entity is None:
        reasons.append(ENTITY_UNKNOWN)
    elif group_cannot_satisfy_company(required_entity, entity):
        reasons.append(GROUP_CANNOT_SATISFY_COMPANY)
    elif entity != required_entity and not _entity_alias_ok(required_entity, entity):
        reasons.append(ENTITY_MISMATCH)

    if entry.period_end is None:
        reasons.append(PERIOD_UNKNOWN)
    elif target_period_end and entry.period_end != target_period_end:
        reasons.append(PERIOD_MISMATCH)
    if requires_exact_3m(concept):
        if entry.duration_months is None:
            reasons.append(DURATION_UNKNOWN)
        elif target_duration is not None and entry.duration_months != target_duration:
            reasons.append(YTD_CANNOT_SATISFY_3M)
        role = str(entry.comparison_role or "").strip().upper()
        if role in {"", "UNKNOWN", "UNRESOLVED", "NONE"}:
            reasons.append(ROLE_UNKNOWN)
        elif role != "CURRENT":
            reasons.append(COMPARATIVE_NOT_CURRENT)

    dimension = concept_dimension(concept)
    if dimension != COUNT and not entry.unit:
        reasons.append(UNIT_UNRESOLVED)
    if entry.scale_factor is None and entry.normalized_value is not None and not _cents_declared(entry):
        reasons.append(SCALE_UNRESOLVED)
    if dimension == PER_SHARE and entry.scale_factor not in {None, 1}:
        reasons.append(SCALE_UNRESOLVED)
    observed_dimension = evidence.get("dimension")
    if observed_dimension and observed_dimension != dimension:
        reasons.append(DIMENSION_MISMATCH)

    if entry.page is None or not entry.label:
        reasons.append(SOURCE_EVIDENCE_MISSING)
    semantic = evidence.get("semantic_score")
    if not isinstance(semantic, (int, float)) or semantic < MIN_PUBLISHABLE_SEMANTIC_SCORE:
        reasons.append(LABEL_EVIDENCE_WEAK)

    # Native compiler candidates must own credible statement-region provenance.
    # Layout-assist candidates are already blocked on source-owned context; recovery and
    # hand-built test candidates that do not claim compiler origin are not retroactively
    # required to possess a detector score.
    if evidence.get("candidate_origin") == "compiler_geometry":
        region_confidence = evidence.get("statement_region_confidence")
        if not isinstance(region_confidence, (int, float)):
            reasons.append(STATEMENT_REGION_UNKNOWN)
        elif region_confidence < MIN_PUBLISHABLE_REGION_CONFIDENCE:
            reasons.append(STATEMENT_REGION_WEAK)

    for reason in entry.reasons or []:
        if reason.startswith("UNIT_UNRESOLVED") and UNIT_UNRESOLVED not in reasons:
            reasons.append(UNIT_UNRESOLVED)
        elif reason.startswith("HEADER_CONFLICT") or reason.startswith(
            ("ENTITY_CONFLICT", "PERIOD_CONFLICT", "DURATION_CONFLICT")
        ):
            reasons.append(HEADER_CONFLICT)
        elif reason.startswith("STATEMENT_REGION_WEAK"):
            reasons.append(STATEMENT_REGION_WEAK)
        elif reason == "STATEMENT_REGION_CONFIDENCE_UNKNOWN":
            reasons.append(STATEMENT_REGION_UNKNOWN)
        elif reason == "SEARCH_BUDGET_EXHAUSTED":
            reasons.append(reason)
        elif reason == "VALIDATION_FAILED":
            reasons.append(VALIDATION_FAILED_PRESERVED)

    column_id = evidence.get("column_id")
    if isinstance(column_id, str) and column_id:
        for conflict in evidence.get("header_conflicts") or []:
            text = str(conflict)
            if text.startswith(f"{column_id}:") or f":{column_id}:" in text:
                reasons.append(HEADER_CONFLICT)
                break

    if concept == "TOTAL_LIABILITIES" and _derived_from_assets_minus_equity(entry):
        reasons.append(DERIVED_LIABILITIES_FORBIDDEN)

    deduped = tuple(dict.fromkeys(reasons))
    return EligibilityResult(not deduped, deduped, concept)


def _entity_alias_ok(required_entity: str, entity: str) -> bool:
    standalone = {"COMPANY", "BANK"}
    return required_entity in standalone and entity in standalone


def _cents_declared(entry: CandidateLike) -> bool:
    evidence = entry.evidence if isinstance(entry.evidence, dict) else {}
    unit = evidence.get("unit_resolution") or evidence.get("unit") or {}
    return str(unit.get("scale")) == "0.01" and unit.get("status") == "RESOLVED"


def _derived_from_assets_minus_equity(entry: CandidateLike) -> bool:
    blob = " ".join(entry.reasons or []).upper()
    evidence = entry.evidence if isinstance(entry.evidence, dict) else {}
    if evidence.get("derived_from") in {"ASSETS_MINUS_EQUITY", "A-E"}:
        return True
    return "ASSETS" in blob and "EQUITY" in blob and "DERIV" in blob
