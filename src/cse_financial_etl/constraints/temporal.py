"""Cross-duration / temporal reasoning (§5, §23) — never silently derive quarters."""

from __future__ import annotations

from decimal import Decimal


def corroborate_standalone_quarter(
    *,
    cumulative_longer: Decimal | None,
    cumulative_shorter: Decimal | None,
    printed_standalone: Decimal | None,
    longer_months: int,
    shorter_months: int,
    tolerance: Decimal = Decimal("2"),
) -> str:
    """Use YTD differences only as corroborating evidence for a printed 3M value."""

    if printed_standalone is None:
        return "UNTESTED"
    if cumulative_longer is None or cumulative_shorter is None:
        return "UNTESTED"
    if longer_months - shorter_months != 3:
        return "NOT_APPLICABLE"
    implied = cumulative_longer - cumulative_shorter
    if abs(implied - printed_standalone) <= tolerance:
        return "PASS"
    return "FAIL"


def duration_satisfies_flow_target(candidate_months: int | None, target_months: int = 3) -> bool:
    """Exact standalone quarter required for flow metrics."""

    return candidate_months == target_months
