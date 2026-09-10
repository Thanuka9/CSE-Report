"""Single publishability rule shared by storage, ratios, gates and Excel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

PUBLISHABLE_STATUSES = frozenset({"EXTRACTED", "EXTRACTED_DERIVED"})
BLOCKED_REVIEW = frozenset({"REJECTED", "FAILED"})
# Validation and review are independent dimensions.  A reviewer approval never
# substitutes for a machine/source validation pass.
PASSED_VALIDATION = frozenset({"PASSED"})
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
DERIVED_RATIO_CODES = frozenset({"DEBT_TO_EQUITY", "ROE", "ROA", "NPM"})


class SupportsPublishFields(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def normalized_value(self) -> Any: ...
    @property
    def review_status(self) -> str: ...
    @property
    def validation_status(self) -> str: ...
    @property
    def duration_months(self) -> int | None: ...
    @property
    def comparison_role(self) -> str: ...
    @property
    def metric_type(self) -> str: ...


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
    """Classify a known output metric as FLOW or AS_AT; unknown stays UNKNOWN.

    This function is deliberately fail closed.  A misspelled/new metric must not
    inherit AS_AT semantics merely because its code is non-empty, otherwise it can
    bypass the CURRENT/three-month checks that protect reported flows.
    """

    code = (metric_code or "").upper()
    kind = (metric_type or "").upper()
    if code in FLOW_METRIC_CODES:
        return "FLOW"
    if code in STOCK_METRIC_CODES:
        return "AS_AT"
    if code in DERIVED_RATIO_CODES and kind == "RATIO":
        return "FLOW"
    return "UNKNOWN"


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
    if mode not in RELEASE_MODES:
        return False, "UNKNOWN_RELEASE_MODE"
    allowed_review = DRAFT_ALLOWED_REVIEW if mode == RELEASE_DRAFT else ALLOWED_REVIEW
    status = str(_field(fact, "status") or "")
    value = _field(fact, "normalized_value", None)
    review = str(_field(fact, "review_status") or "")
    validation = str(_field(fact, "validation_status") or "")
    duration = _coerce_duration(_field(fact, "duration_months", None))
    comparison_role = str(_field(fact, "comparison_role") or "").upper()
    metric_type = str(_field(fact, "metric_type") or "")
    metric_code = str(_field(fact, "metric_code") or "")
    basis = period_basis_for_metric(metric_code, metric_type)

    if status not in PUBLISHABLE_STATUSES:
        return False, status or "NOT_REPORTED"
    if value in (None, ""):
        return False, "NOT_REPORTED"
    if basis == "UNKNOWN":
        return False, "UNKNOWN_METRIC_SEMANTICS"
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
        # Reported statement flows must be proven to come from the target/current
        # column. Derived ratios inherit their validated source periods and do not
        # need a raw table comparison role of their own.
        if metric_code.upper() in FLOW_METRIC_CODES and comparison_role != "CURRENT":
            return False, "CURRENT_PERIOD_UNRESOLVED"
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
