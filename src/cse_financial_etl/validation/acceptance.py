"""Single publishability rule shared by storage, ratios, gates and Excel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

PUBLISHABLE_STATUSES = frozenset({"EXTRACTED", "EXTRACTED_DERIVED"})
BLOCKED_REVIEW = frozenset({"REJECTED", "FAILED"})
PASSED_VALIDATION = frozenset({"PASSED", "APPROVED", "CURATED"})
# Official release: only an authenticated reviewer approval (or a curated
# correction) makes a numeric cell publishable. ``REVIEW`` / blank never do
# (gap A4, audit finding 6).
ALLOWED_REVIEW = frozenset({"APPROVED", "CURATED"})
# Machine-eligible but unreviewed rows may be *displayed* only in an explicitly
# labelled DRAFT release; they are never part of the governed official release.
DRAFT_ALLOWED_REVIEW = frozenset({"APPROVED", "CURATED", "REVIEW"})

RELEASE_OFFICIAL = "OFFICIAL"
RELEASE_DRAFT = "DRAFT"
RELEASE_MODES = frozenset({RELEASE_OFFICIAL, RELEASE_DRAFT})
_release_mode = RELEASE_OFFICIAL


def set_release_mode(mode: str) -> str:
    """Configure the process-wide release mode (from configs/app.yml ``publication``)."""

    global _release_mode
    normalized = (mode or RELEASE_OFFICIAL).strip().upper()
    if normalized not in RELEASE_MODES:
        raise ValueError(f"unknown release_mode {mode!r}; expected one of {sorted(RELEASE_MODES)}")
    _release_mode = normalized
    return _release_mode


def current_release_mode() -> str:
    return _release_mode


def is_official_release() -> bool:
    return _release_mode == RELEASE_OFFICIAL
FLOW_METRIC_CODES = frozenset(
    {
        "PAT",
        "PBT",
        "TOP_LINE",
        "OPERATING_PROFIT",
        "EPS_BASIC",
        "EPS_DILUTED",
        "EPS_SELECTED",
    }
)
STOCK_METRIC_CODES = frozenset(
    {
        "TOTAL_ASSETS",
        "TOTAL_EQUITY",
        "TOTAL_LIABILITIES",
        "NAVPS",
    }
)


class SupportsPublishFields(Protocol):
    status: str
    normalized_value: Any
    review_status: str
    validation_status: str
    duration_months: int | None
    metric_type: str


def _field(fact: SupportsPublishFields | Mapping[str, Any], name: str, default: Any = "") -> Any:
    if isinstance(fact, Mapping):
        return fact.get(name, default)
    return getattr(fact, name, default)


def _coerce_duration(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def period_basis_for_metric(metric_code: str, metric_type: str = "") -> str:
    """Classify whether a metric is a period FLOW or an AS_AT stock/balance."""

    code = (metric_code or "").upper()
    if code in FLOW_METRIC_CODES:
        return "FLOW"
    if code in STOCK_METRIC_CODES:
        return "AS_AT"
    if (metric_type or "").upper() == "RATIO":
        return "FLOW"
    if (metric_type or "").upper() == "MONETARY_PER_SHARE" and "NAV" in code:
        return "AS_AT"
    if (metric_type or "").upper() == "MONETARY_PER_SHARE":
        return "FLOW"
    return "AS_AT" if code else "UNKNOWN"


def publishability_decision(
    fact: SupportsPublishFields | Mapping[str, Any],
    *,
    require_quarter_flow: bool | None = None,
    release_mode: str | None = None,
) -> tuple[bool, str | None]:
    """Return (publishable?, reason_code). reason_code is set when rejected.

    ``release_mode`` defaults to the configured process-wide mode. In OFFICIAL
    mode only APPROVED/CURATED rows publish; in DRAFT mode validated rows that
    are still pending review are displayed as draft candidates.
    """

    mode = (release_mode or _release_mode).upper()
    allowed_review = DRAFT_ALLOWED_REVIEW if mode == RELEASE_DRAFT else ALLOWED_REVIEW
    status = str(_field(fact, "status") or "")
    value = _field(fact, "normalized_value", None)
    review = str(_field(fact, "review_status") or "")
    validation = str(_field(fact, "validation_status") or "")
    duration = _coerce_duration(_field(fact, "duration_months", None))
    metric_type = str(_field(fact, "metric_type") or "")
    metric_code = str(_field(fact, "metric_code") or "")
    basis = period_basis_for_metric(metric_code, metric_type)

    if status not in PUBLISHABLE_STATUSES:
        return False, status or "NOT_REPORTED"
    if value in (None, ""):
        return False, "NOT_REPORTED"
    if review in BLOCKED_REVIEW:
        return False, "REVIEW_REJECTED"
    if validation in {"FAILED", "REJECTED"}:
        return False, "VALIDATION_FAILED"
    if validation not in PASSED_VALIDATION:
        return False, "NOT_VALIDATED"
    if review not in allowed_review:
        return False, "REVIEW_REQUIRED"

    require_quarter = require_quarter_flow
    if require_quarter is None:
        require_quarter = basis == "FLOW"

    if require_quarter and basis == "FLOW":
        if duration is None:
            return False, "PERIOD_UNRESOLVED"
        if duration != 3:
            return False, "NON_QUARTER_DURATION"

    if (
        require_quarter_flow is True
        and basis != "FLOW"
        and metric_type == "MONETARY_ABSOLUTE"
        and duration in {6, 9, 12}
    ):
        return False, "NON_QUARTER_DURATION"

    return True, None


def is_publishable_fact(
    fact: SupportsPublishFields | Mapping[str, Any],
    *,
    require_quarter_flow: bool | None = None,
    release_mode: str | None = None,
) -> bool:
    """True when a fact may appear as a numeric cell in ratios/Excel/gates."""

    return publishability_decision(
        fact, require_quarter_flow=require_quarter_flow, release_mode=release_mode
    )[0]
