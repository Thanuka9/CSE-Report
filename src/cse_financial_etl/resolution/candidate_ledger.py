"""Candidate ledger — high recall; discard only when disproven (§29)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class LedgerEntry:
    entry_id: str
    tunnel: str
    concept: str
    status: str  # accepted | rejected | unresolved | alternative
    raw_value: Decimal | None
    normalized_value: Decimal | None
    entity: str | None
    period_end: str | None
    duration_months: int | None
    comparison_role: str | None
    unit: str | None
    scale_factor: int | None
    page: int | None
    bbox: str | None
    label: str | None
    score: float
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateLedger:
    entries: list[LedgerEntry] = field(default_factory=list)

    def add(self, entry: LedgerEntry) -> None:
        self.entries.append(entry)

    def for_concept(self, concept: str) -> list[LedgerEntry]:
        return [e for e in self.entries if e.concept == concept]

    def unresolved(self) -> list[LedgerEntry]:
        return [e for e in self.entries if e.status == "unresolved"]

    def accepted(self) -> list[LedgerEntry]:
        return [e for e in self.entries if e.status == "accepted"]

    def reject(self, entry_id: str, reason: str) -> None:
        for entry in self.entries:
            if entry.entry_id == entry_id:
                entry.status = "rejected"
                entry.reasons.append(reason)
                return

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.entries),
            "by_status": {
                status: sum(1 for e in self.entries if e.status == status)
                for status in ("accepted", "rejected", "unresolved", "alternative")
            },
            "entries": [
                {
                    "id": e.entry_id,
                    "tunnel": e.tunnel,
                    "concept": e.concept,
                    "status": e.status,
                    "value": str(e.normalized_value) if e.normalized_value is not None else None,
                    "entity": e.entity,
                    "duration": e.duration_months,
                    "role": e.comparison_role,
                    "score": e.score,
                    "reasons": e.reasons,
                }
                for e in self.entries
            ],
        }
