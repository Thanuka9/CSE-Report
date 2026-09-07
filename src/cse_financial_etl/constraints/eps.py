"""EPS constraint policy (§38) — diluted preferred when valid; zero ≠ missing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EpsSelection:
    selected: str  # EPS_DILUTED | EPS_BASIC | NONE
    reason: str
    value: Decimal | None


def select_eps(
    *,
    diluted: Decimal | None,
    diluted_status: str,
    basic: Decimal | None,
    basic_status: str,
) -> EpsSelection:
    diluted_ok = diluted_status in {"EXTRACTED", "EXTRACTED_DERIVED"} and diluted is not None
    basic_ok = basic_status in {"EXTRACTED", "EXTRACTED_DERIVED"} and basic is not None
    # Valid zero is not missing.
    if diluted_ok:
        return EpsSelection("EPS_DILUTED", "diluted_eligible_and_valid", diluted)
    if basic_ok:
        return EpsSelection("EPS_BASIC", "diluted_unavailable_fallback_basic", basic)
    return EpsSelection("NONE", "neither_basic_nor_diluted_valid", None)


def reconcile_eps(
    earnings: Decimal | None,
    weighted_shares: Decimal | None,
    reported_eps: Decimal | None,
    *,
    tolerance: Decimal = Decimal("0.01"),
) -> str:
    if earnings is None or weighted_shares is None or weighted_shares == 0:
        return "UNTESTED"
    if reported_eps is None:
        return "UNTESTED"
    implied = earnings / weighted_shares
    return "PASS" if abs(implied - reported_eps) <= tolerance else "FAIL"
