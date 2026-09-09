"""Official-release gate: human approval bound to fact identity (audit finding 6, gap B9).

Machine eligibility (status, validation, shared eligibility contract) is decided by
the pipeline. *Official* publication additionally requires a reviewer decision that
is bound to:

* the fact identity (issuer, symbol, period end, metric code),
* the exact source document (``filing_sha256``),
* the review policy version in force, and
* an authenticated reviewer identity.

Decisions are appended to ``data/review/review_decisions.jsonl``; a decision whose
source hash or policy version no longer matches is *stale* and is never applied.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REVIEW_POLICY_VERSION = "R2-2026-09"
DECISION_APPROVED = "APPROVED"
DECISION_REJECTED = "REJECTED"
DECISIONS = frozenset({DECISION_APPROVED, DECISION_REJECTED})
DEFAULT_DECISIONS_RELATIVE_PATH = Path("data") / "review" / "review_decisions.jsonl"


def fact_identity(issuer_name: str, symbol: str, period_end: str, metric_code: str) -> str:
    payload = f"{issuer_name.strip().casefold()}|{symbol.strip().upper()}|{period_end}|{metric_code.strip().upper()}"
    return "fact:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    issuer_name: str
    symbol: str
    period_end: str
    metric_code: str
    filing_sha256: str
    policy_version: str
    reviewer_id: str
    decision: str
    decided_at: str
    note: str = ""

    @property
    def identity(self) -> str:
        return fact_identity(self.issuer_name, self.symbol, self.period_end, self.metric_code)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fact_identity": self.identity}


def make_decision(
    *,
    issuer_name: str,
    symbol: str,
    period_end: str,
    metric_code: str,
    filing_sha256: str,
    reviewer_id: str,
    decision: str,
    note: str = "",
    policy_version: str = REVIEW_POLICY_VERSION,
) -> ReviewDecision:
    normalized = decision.strip().upper()
    if normalized not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}, got {decision!r}")
    if not reviewer_id.strip():
        raise ValueError("reviewer_id is required for an official review decision")
    if not filing_sha256.strip():
        raise ValueError("filing_sha256 is required to bind the decision to the source document")
    return ReviewDecision(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=metric_code,
        filing_sha256=filing_sha256,
        policy_version=policy_version,
        reviewer_id=reviewer_id.strip(),
        decision=normalized,
        decided_at=datetime.now(UTC).isoformat(),
        note=note,
    )


def append_decision(path: Path, decision: ReviewDecision) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision.as_dict(), ensure_ascii=False) + "\n")


def load_review_decisions(path: Path) -> list[ReviewDecision]:
    if not path.exists():
        return []
    decisions: list[ReviewDecision] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            decisions.append(
                ReviewDecision(
                    issuer_name=str(raw["issuer_name"]),
                    symbol=str(raw["symbol"]),
                    period_end=str(raw["period_end"]),
                    metric_code=str(raw["metric_code"]),
                    filing_sha256=str(raw["filing_sha256"]),
                    policy_version=str(raw.get("policy_version") or ""),
                    reviewer_id=str(raw.get("reviewer_id") or ""),
                    decision=str(raw.get("decision") or "").upper(),
                    decided_at=str(raw.get("decided_at") or ""),
                    note=str(raw.get("note") or ""),
                )
            )
        except KeyError:
            continue
    return decisions


@dataclass(slots=True)
class ReleaseSummary:
    policy_version: str = REVIEW_POLICY_VERSION
    decisions_loaded: int = 0
    approved_applied: int = 0
    rejected_applied: int = 0
    stale_source_hash: int = 0
    policy_mismatch: int = 0
    unauthenticated: int = 0
    unmatched: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_review_decisions(
    facts: list[Any],
    decisions: list[ReviewDecision],
    *,
    filing_sha256: str,
    policy_version: str = REVIEW_POLICY_VERSION,
) -> tuple[list[Any], ReleaseSummary]:
    """Bind approvals to facts of one filing. Returns new facts and a summary.

    ``facts`` are ``ExtractedFact`` dataclass instances (any dataclass exposing
    issuer_name/symbol/period_end/metric_code/review_status works).
    """

    summary = ReleaseSummary(policy_version=policy_version, decisions_loaded=len(decisions))
    by_identity: dict[str, ReviewDecision] = {}
    for decision in decisions:
        # Latest decision per identity wins (append-only log).
        by_identity[decision.identity] = decision
    updated: list[Any] = []
    matched: set[str] = set()
    for fact in facts:
        period = fact.period_end.isoformat() if hasattr(fact.period_end, "isoformat") else str(fact.period_end)
        identity = fact_identity(fact.issuer_name, fact.symbol, period, fact.metric_code)
        decision = by_identity.get(identity)
        if decision is None:
            updated.append(fact)
            continue
        matched.add(identity)
        if not decision.reviewer_id:
            summary.unauthenticated += 1
            updated.append(fact)
            continue
        if decision.policy_version != policy_version:
            summary.policy_mismatch += 1
            updated.append(fact)
            continue
        if decision.filing_sha256 != filing_sha256:
            summary.stale_source_hash += 1
            updated.append(fact)
            continue
        if decision.decision == DECISION_APPROVED:
            summary.approved_applied += 1
        else:
            summary.rejected_applied += 1
        updated.append(replace(fact, review_status=decision.decision))
    summary.unmatched = len([d for d in by_identity if d not in matched])
    return updated, summary


def official_release_allowed(fact: Any) -> tuple[bool, str | None]:
    """The governed official-release predicate for one fact (independent of Excel)."""

    status = str(getattr(fact, "status", "") or "")
    if status not in {"EXTRACTED", "EXTRACTED_DERIVED"}:
        return False, status or "NOT_REPORTED"
    if getattr(fact, "normalized_value", None) is None:
        return False, "NOT_REPORTED"
    validation = str(getattr(fact, "validation_status", "") or "")
    if validation != "PASSED":
        return False, "NOT_VALIDATED" if validation != "FAILED" else "VALIDATION_FAILED"
    review = str(getattr(fact, "review_status", "") or "")
    if review not in {DECISION_APPROVED, "CURATED"}:
        return False, "REVIEW_REQUIRED"
    return True, None
