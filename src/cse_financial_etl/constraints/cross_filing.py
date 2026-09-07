"""Cross-filing evidence without temporal leakage (§24)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FilingFactKey:
    issuer_id: str
    concept: str
    entity: str
    period_start: date | None
    period_end: date
    duration_months: int
    currency: str
    accounting_basis: str


def keys_comparable(a: FilingFactKey, b: FilingFactKey) -> bool:
    return (
        a.issuer_id == b.issuer_id
        and a.concept == b.concept
        and a.entity == b.entity
        and a.period_end == b.period_end
        and a.period_start == b.period_start
        and a.duration_months == b.duration_months
        and a.currency == b.currency
        and a.accounting_basis == b.accounting_basis
    )


def corroborate_cross_filing(
    current: Decimal | None,
    prior_or_later: Decimal | None,
    *,
    current_key: FilingFactKey,
    other_key: FilingFactKey,
    knowledge_cutoff: date,
    other_publication: date,
    tolerance: Decimal = Decimal("1"),
) -> str:
    """Later sources beyond knowledge cutoff cannot change historical release."""

    if other_publication > knowledge_cutoff:
        return "NOT_APPLICABLE"
    if not keys_comparable(current_key, other_key):
        return "NOT_APPLICABLE"
    if current is None or prior_or_later is None:
        return "UNTESTED"
    return "PASS" if abs(current - prior_or_later) <= tolerance else "FAIL"
