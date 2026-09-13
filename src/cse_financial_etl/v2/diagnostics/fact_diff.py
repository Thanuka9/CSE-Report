"""Fact-identity diff for fixed-input replay. Counts alone are not a comparison."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class FactDiffClass(StrEnum):
    UNCHANGED = "UNCHANGED"
    LOST = "LOST"
    NEW = "NEW"
    VALUE_CHANGED = "VALUE_CHANGED"
    CONTEXT_CHANGED = "CONTEXT_CHANGED"
    STATUS_CHANGED = "STATUS_CHANGED"


class FactIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filing_version_id: str
    entity_scope: str
    period_end: str
    duration_months: int | None
    comparison_role: str
    metric_code: str

    def key(self) -> tuple[str, str, str, int | None, str, str]:
        return (
            self.filing_version_id,
            self.entity_scope,
            self.period_end,
            self.duration_months,
            self.comparison_role,
            self.metric_code,
        )


CONTEXT_FIELDS: tuple[str, ...] = (
    "entity_scope",
    "period_end",
    "duration_months",
    "comparison_role",
)


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("duration_months cannot be a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise ValueError(f"invalid duration_months: {value!r}")


def fact_identity_from_mapping(payload: Mapping[str, object]) -> FactIdentity:
    return FactIdentity(
        filing_version_id=str(payload.get("filing_version_id") or ""),
        entity_scope=str(payload.get("entity_scope") or ""),
        period_end=str(payload.get("period_end") or ""),
        duration_months=_optional_int(payload.get("duration_months")),
        comparison_role=str(payload.get("comparison_role") or ""),
        metric_code=str(payload.get("metric_code") or ""),
    )


def classify_fact_pair(
    reference: Mapping[str, object] | None,
    current: Mapping[str, object] | None,
) -> FactDiffClass:
    if reference is None and current is None:
        raise ValueError("both reference and current facts are missing")
    if reference is None:
        return FactDiffClass.NEW
    if current is None:
        return FactDiffClass.LOST
    if any(
        str(reference.get(field) or "") != str(current.get(field) or "") for field in CONTEXT_FIELDS
    ):
        return FactDiffClass.CONTEXT_CHANGED
    if str(reference.get("normalized_value") or "") != str(current.get("normalized_value") or ""):
        return FactDiffClass.VALUE_CHANGED
    ref_status = (
        str(reference.get("validation_status") or ""),
        str(reference.get("review_status") or ""),
        str(reference.get("publication_status") or ""),
    )
    cur_status = (
        str(current.get("validation_status") or ""),
        str(current.get("review_status") or ""),
        str(current.get("publication_status") or ""),
    )
    if ref_status != cur_status:
        return FactDiffClass.STATUS_CHANGED
    return FactDiffClass.UNCHANGED


def diff_fact_populations(
    reference: tuple[Mapping[str, object], ...],
    current: tuple[Mapping[str, object], ...],
) -> dict[FactDiffClass, int]:
    ref_map = {fact_identity_from_mapping(item).key(): item for item in reference}
    cur_map = {fact_identity_from_mapping(item).key(): item for item in current}
    keys = set(ref_map) | set(cur_map)
    counts = {cls: 0 for cls in FactDiffClass}
    for key in sorted(keys):
        classified = classify_fact_pair(ref_map.get(key), cur_map.get(key))
        counts[classified] += 1
    return counts
