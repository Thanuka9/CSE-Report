"""Known filing context — expected vs observed, never force incompatible quarters (§6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class KnownContext:
    issuer_id: str
    issuer_name: str
    symbol: str
    security_class: str
    sector_profile: str
    required_entity: str
    target_period_end: date
    target_duration_months: int
    display_bucket: str | None
    expected_current_end: date | None
    expected_comparative_end: date | None
    knowledge_cutoff: date | None
    source_version_ids: tuple[str, ...] = ()
    expected_context: dict[str, Any] = field(default_factory=dict)
    observed_context: dict[str, Any] = field(default_factory=dict)
    context_evidence: dict[str, Any] = field(default_factory=dict)
    conflicts: tuple[str, ...] = ()


def build_known_context(
    *,
    issuer_name: str,
    symbol: str,
    period_end: date,
    required_entity: str,
    sector_profile: str = "GENERAL_CORPORATE",
    target_duration_months: int = 3,
    display_bucket: str | None = None,
    knowledge_cutoff: date | None = None,
    fiscal_calendar: dict[str, Any] | None = None,
) -> KnownContext:
    expected = {
        "period_end": period_end.isoformat(),
        "duration_months": target_duration_months,
        "entity": required_entity,
        "fiscal_calendar": fiscal_calendar or {},
    }
    return KnownContext(
        issuer_id=symbol,
        issuer_name=issuer_name,
        symbol=symbol,
        security_class="VOTING" if ".N" in symbol.upper() else "UNKNOWN",
        sector_profile=sector_profile,
        required_entity=required_entity,
        target_period_end=period_end,
        target_duration_months=target_duration_months,
        display_bucket=display_bucket,
        expected_current_end=period_end,
        expected_comparative_end=None,
        knowledge_cutoff=knowledge_cutoff or period_end,
        expected_context=expected,
    )


def merge_observed_context(
    known: KnownContext,
    *,
    observed: dict[str, Any],
    evidence: dict[str, Any] | None = None,
    conflicts: list[str] | None = None,
) -> KnownContext:
    return KnownContext(
        issuer_id=known.issuer_id,
        issuer_name=known.issuer_name,
        symbol=known.symbol,
        security_class=known.security_class,
        sector_profile=known.sector_profile,
        required_entity=known.required_entity,
        target_period_end=known.target_period_end,
        target_duration_months=known.target_duration_months,
        display_bucket=known.display_bucket,
        expected_current_end=known.expected_current_end,
        expected_comparative_end=known.expected_comparative_end,
        knowledge_cutoff=known.knowledge_cutoff,
        source_version_ids=known.source_version_ids,
        expected_context=known.expected_context,
        observed_context=observed,
        context_evidence=evidence or {},
        conflicts=tuple(conflicts or ()),
    )
