"""Official-release gate with source- and fact-bound signed review decisions.

Machine eligibility is decided by the pipeline. Official publication additionally
requires a reviewer decision bound to the fact identity, exact filing SHA-256, exact
materialized fact fingerprint, policy version and a reviewer-held signing secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REVIEW_POLICY_VERSION = "R2-2026-09-FACTBOUND"
DECISION_APPROVED = "APPROVED"
DECISION_REJECTED = "REJECTED"
DECISIONS = frozenset({DECISION_APPROVED, DECISION_REJECTED})
AUTH_PROVIDER_HMAC = "HMAC_SHA256_ENV"
DEFAULT_DECISIONS_RELATIVE_PATH = Path("data") / "review" / "review_decisions.jsonl"


def fact_identity(issuer_name: str, symbol: str, period_end: str, metric_code: str) -> str:
    payload = f"{issuer_name.strip().casefold()}|{symbol.strip().upper()}|{period_end}|{metric_code.strip().upper()}"
    return "fact:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def fact_fingerprint(fact: Any) -> str:
    """Hash the exact reviewed value and its material source/context provenance."""

    period = fact.period_end.isoformat() if hasattr(fact.period_end, "isoformat") else str(fact.period_end)
    evidence_raw = getattr(fact, "evidence_json", None)
    evidence: Any = evidence_raw
    if isinstance(evidence_raw, str) and evidence_raw.strip():
        try:
            evidence = json.loads(evidence_raw)
        except json.JSONDecodeError:
            evidence = evidence_raw
    payload = {
        "issuer_name": str(getattr(fact, "issuer_name", "")).strip().casefold(),
        "symbol": str(getattr(fact, "symbol", "")).strip().upper(),
        "period_end": period,
        "metric_code": str(getattr(fact, "metric_code", "")).strip().upper(),
        "metric_type": str(getattr(fact, "metric_type", "")),
        "raw_text": getattr(fact, "raw_text", None),
        "raw_value": str(getattr(fact, "raw_value", None)) if getattr(fact, "raw_value", None) is not None else None,
        "normalized_value": str(getattr(fact, "normalized_value", None)) if getattr(fact, "normalized_value", None) is not None else None,
        "currency": getattr(fact, "currency", None),
        "scale_factor": getattr(fact, "scale_factor", None),
        "entity_scope": getattr(fact, "entity_scope", None),
        "comparison_role": getattr(fact, "comparison_role", None),
        "duration_months": getattr(fact, "duration_months", None),
        "source_page": getattr(fact, "source_page", None),
        "source_line": getattr(fact, "source_line", None),
        "raw_label": getattr(fact, "raw_label", None),
        "source_bbox": getattr(fact, "source_bbox", None),
        "extraction_method": getattr(fact, "extraction_method", None),
        "semantic_model": getattr(fact, "semantic_model", None),
        "evidence": evidence,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "factfp:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _secret_env_name(key_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", key_id.strip().upper()).strip("_")
    if not safe:
        raise ValueError("key_id is required")
    return f"CSE_REVIEW_KEY_{safe}"


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    issuer_name: str
    symbol: str
    period_end: str
    metric_code: str
    filing_sha256: str
    fact_fingerprint: str
    policy_version: str
    reviewer_id: str
    decision: str
    decided_at: str
    note: str = ""
    auth_provider: str = ""
    key_id: str = ""
    signature: str = ""

    @property
    def identity(self) -> str:
        return fact_identity(self.issuer_name, self.symbol, self.period_end, self.metric_code)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fact_identity": self.identity}


def _signing_payload(decision: ReviewDecision) -> bytes:
    payload = {
        "issuer_name": decision.issuer_name,
        "symbol": decision.symbol,
        "period_end": decision.period_end,
        "metric_code": decision.metric_code,
        "filing_sha256": decision.filing_sha256,
        "fact_fingerprint": decision.fact_fingerprint,
        "policy_version": decision.policy_version,
        "reviewer_id": decision.reviewer_id,
        "decision": decision.decision,
        "decided_at": decision.decided_at,
        "note": decision.note,
        "auth_provider": AUTH_PROVIDER_HMAC,
        "key_id": decision.key_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_decision(decision: ReviewDecision, *, secret: str, key_id: str) -> ReviewDecision:
    if not secret:
        raise ValueError("review signing secret is empty")
    if not decision.fact_fingerprint:
        raise ValueError("fact_fingerprint is required before signing")
    unsigned = replace(decision, auth_provider=AUTH_PROVIDER_HMAC, key_id=key_id.strip(), signature="")
    signature = hmac.new(secret.encode("utf-8"), _signing_payload(unsigned), hashlib.sha256).hexdigest()
    return replace(unsigned, signature=signature)


def verify_decision_signature(decision: ReviewDecision) -> tuple[bool, str]:
    if decision.auth_provider != AUTH_PROVIDER_HMAC:
        return False, "UNSUPPORTED_AUTH_PROVIDER"
    if not decision.fact_fingerprint:
        return False, "FACT_FINGERPRINT_MISSING"
    if not decision.key_id or not decision.signature:
        return False, "SIGNATURE_MISSING"
    env_name = _secret_env_name(decision.key_id)
    secret = os.environ.get(env_name)
    if not secret:
        return False, f"SIGNING_KEY_UNAVAILABLE:{env_name}"
    expected = hmac.new(secret.encode("utf-8"), _signing_payload(decision), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, decision.signature):
        return False, "SIGNATURE_INVALID"
    return True, "AUTHENTICATED"


def make_decision(
    *, issuer_name: str, symbol: str, period_end: str, metric_code: str,
    filing_sha256: str, reviewer_id: str, decision: str,
    fact_fingerprint: str, note: str = "", policy_version: str = REVIEW_POLICY_VERSION,
    key_id: str | None = None,
) -> ReviewDecision:
    normalized = decision.strip().upper()
    if normalized not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}, got {decision!r}")
    if not reviewer_id.strip():
        raise ValueError("reviewer_id is required for an official review decision")
    if not filing_sha256.strip():
        raise ValueError("filing_sha256 is required to bind the decision to the source document")
    if not fact_fingerprint.strip():
        raise ValueError("fact_fingerprint is required to bind the decision to the reviewed fact")
    created = ReviewDecision(
        issuer_name=issuer_name, symbol=symbol, period_end=period_end, metric_code=metric_code,
        filing_sha256=filing_sha256, fact_fingerprint=fact_fingerprint,
        policy_version=policy_version, reviewer_id=reviewer_id.strip(), decision=normalized,
        decided_at=datetime.now(UTC).isoformat(), note=note,
    )
    if key_id is None:
        return created
    env_name = _secret_env_name(key_id)
    secret = os.environ.get(env_name)
    if not secret:
        raise ValueError(f"review signing key is not provisioned in {env_name}")
    return sign_decision(created, secret=secret, key_id=key_id)


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
            decisions.append(ReviewDecision(
                issuer_name=str(raw["issuer_name"]), symbol=str(raw["symbol"]),
                period_end=str(raw["period_end"]), metric_code=str(raw["metric_code"]),
                filing_sha256=str(raw["filing_sha256"]),
                fact_fingerprint=str(raw.get("fact_fingerprint") or ""),
                policy_version=str(raw.get("policy_version") or ""),
                reviewer_id=str(raw.get("reviewer_id") or ""),
                decision=str(raw.get("decision") or "").upper(), decided_at=str(raw.get("decided_at") or ""),
                note=str(raw.get("note") or ""), auth_provider=str(raw.get("auth_provider") or ""),
                key_id=str(raw.get("key_id") or ""), signature=str(raw.get("signature") or ""),
            ))
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
    stale_fact_fingerprint: int = 0
    policy_mismatch: int = 0
    unauthenticated: int = 0
    invalid_signature: int = 0
    signing_key_unavailable: int = 0
    unmatched: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_review_decisions(
    facts: list[Any], decisions: list[ReviewDecision], *, filing_sha256: str,
    policy_version: str = REVIEW_POLICY_VERSION,
) -> tuple[list[Any], ReleaseSummary]:
    summary = ReleaseSummary(policy_version=policy_version, decisions_loaded=len(decisions))
    by_identity: dict[str, ReviewDecision] = {decision.identity: decision for decision in decisions}
    updated: list[Any] = []
    matched: set[str] = set()
    for fact in facts:
        period = fact.period_end.isoformat() if hasattr(fact.period_end, "isoformat") else str(fact.period_end)
        identity = fact_identity(fact.issuer_name, fact.symbol, period, fact.metric_code)
        decision = by_identity.get(identity)
        if decision is None:
            updated.append(fact); continue
        matched.add(identity)
        if not decision.reviewer_id:
            summary.unauthenticated += 1; updated.append(fact); continue
        authenticated, auth_reason = verify_decision_signature(decision)
        if not authenticated:
            summary.unauthenticated += 1
            if auth_reason == "SIGNATURE_INVALID": summary.invalid_signature += 1
            if auth_reason.startswith("SIGNING_KEY_UNAVAILABLE"): summary.signing_key_unavailable += 1
            updated.append(fact); continue
        if decision.policy_version != policy_version:
            summary.policy_mismatch += 1; updated.append(fact); continue
        if decision.filing_sha256 != filing_sha256:
            summary.stale_source_hash += 1; updated.append(fact); continue
        if decision.fact_fingerprint != fact_fingerprint(fact):
            summary.stale_fact_fingerprint += 1; updated.append(fact); continue
        if decision.decision == DECISION_APPROVED:
            summary.approved_applied += 1
        elif decision.decision == DECISION_REJECTED:
            summary.rejected_applied += 1
        else:
            updated.append(fact); continue
        updated.append(replace(fact, review_status=decision.decision))
    summary.unmatched = len([identity for identity in by_identity if identity not in matched])
    return updated, summary


def official_release_allowed(fact: Any) -> tuple[bool, str | None]:
    from cse_financial_etl.validation.acceptance import publishability_decision
    return publishability_decision(fact, release_mode="OFFICIAL")
