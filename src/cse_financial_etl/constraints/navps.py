"""NAVPS constraint policy (§39)."""

from __future__ import annotations

from decimal import Decimal


def reconcile_navps(
    equity: Decimal | None,
    period_end_shares: Decimal | None,
    reported_navps: Decimal | None,
    *,
    tolerance: Decimal = Decimal("0.05"),
) -> str:
    if equity is None or period_end_shares is None or period_end_shares == 0:
        return "UNTESTED"
    if reported_navps is None:
        return "UNTESTED"
    implied = equity / period_end_shares
    return "PASS" if abs(implied - reported_navps) <= tolerance else "FAIL"
