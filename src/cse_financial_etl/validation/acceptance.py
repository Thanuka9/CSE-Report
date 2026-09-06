"""Single publishability rule shared by storage, ratios, gates and Excel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

PUBLISHABLE_STATUSES = frozenset({"EXTRACTED", "EXTRACTED_DERIVED"})
BLOCKED_REVIEW = frozenset({"REJECTED", "FAILED"})


class SupportsPublishFields(Protocol):
    status: str
    normalized_value: Any
    review_status: str
    validation_status: str
    duration_months: int | None
    metric_type: str


def is_publishable_fact(
    fact: SupportsPublishFields | Mapping[str, Any],
    *,
    require_quarter_flow: bool = False,
) -> bool:
    """True when a fact may appear as a numeric cell in ratios/Excel/gates."""

    if isinstance(fact, Mapping):
        status = str(fact.get("status") or "")
        value = fact.get("normalized_value")
        review = str(fact.get("review_status") or "")
        validation = str(fact.get("validation_status") or "")
        duration = fact.get("duration_months")
        metric_type = str(fact.get("metric_type") or "")
    else:
        status = fact.status
        value = fact.normalized_value
        review = fact.review_status
        validation = fact.validation_status
        duration = fact.duration_months
        metric_type = fact.metric_type

    if status not in PUBLISHABLE_STATUSES:
        return False
    if value in (None, ""):
        return False
    if review in BLOCKED_REVIEW:
        return False
    if validation in {"FAILED", "REJECTED"}:
        return False
    # Stock metrics use duration None; flow absolutes must be exact quarter when required.
    return not (
        require_quarter_flow
        and metric_type == "MONETARY_ABSOLUTE"
        and duration in {6, 9, 12}
    )
