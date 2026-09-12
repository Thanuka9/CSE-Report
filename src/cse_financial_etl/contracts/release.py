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
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cse_financial_etl.contracts.publication import publishability_decision

REVIEW_POLICY_VERSION = "R2-2026-09-FACTBOUND"
DECISION_APPROVED = "APPROVED"
DECISION_REJECTED = "REJECTED"
DECISIONS = frozenset({DECISION_APPROVED, DECISION_REJECTED})
AUTH_PROVIDER_HMAC = "HMAC_SHA256_ENV"
DEFAULT_DECISIONS_RELATIVE_PATH = Path("data") / "review" / "review_decisions.jsonl"


def fact_identity(issuer_name: str, symbol: str, period_end: str, metric_code: str) -> str:
    payload = f"{issuer_name.strip().casefold()}|{symbol.strip().upper()}|{period_end}|{metric_code.strip().upper()}"
    return "fact:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _fact_field(fact: Any, name: str) -> Any:
    if isinstance(fact, Mapping):
        return fact.get(name)
    return getattr(fact, name, None)


def _canonical_scalar(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()


def _canonical_period(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value or "").strip()


def _material_evidence(fact: Any) -> dict[str, Any]:
    """Return only stable evidence that materially defines the reviewed fact."""

    raw = _fact_field(fact, "evidence_json")
    if isinstance(raw, Mapping):
        parsed: Any = dict(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
    else:
        parsed = {}
    if not isinstance(parsed, Mapping):
        return {}
    stable_keys = (
        "source_evidence",
        "extraction_origin",
        "publication_routing",
        "eligibility_reasons",
        "final_check",
        "formula",
        "inputs",
        "derived_value",
        "entity_scope",
        "comparison_role",
        "period_end",
        "row_safety",
        "preferred_source",
    )
    return {key: parsed[key] for key in stable_keys if key in parsed}


def fact_fingerprint(fact: Any) -> str:
    """Hash exact value/context/source provenance identically for objects and CSV rows."""

    payload = {
        "issuer_name": str(_fact_field(fact, "issuer_name") or "").strip().casefold(),
        "symbol": str(_fact_field(fact, "symbol") or "").strip().upper(),
        "period_end": _canonical_period(_fact_field(fact, "period_end")),
        "metric_code": str(_fact_field(fact, "metric_code") or "").strip().upper(),
        "metric_type": _canonical_scalar(_fact_field(fact, "metric_type")),
        "raw_text": _canonical_scalar(_fact_field(fact, "raw_text")),
        "raw_value": _canonical_scalar(_fact_field(fact, "raw_value")),
        "normalized_value": _canonical_scalar(_fact_field(fact, "normalized_value")),
        "currency": _canonical_scalar(_fact_field(fact, "currency")),
        "scale_factor": _canonical_scalar(_fact_field(fact, "scale_factor")),
        "entity_scope": _canonical_scalar(_fact_field(fact, "entity_scope")),
        "comparison_role": _canonical_scalar(_fact_field(fact, "comparison_role")),
        "duration_months": _canonical_scalar(_fact_field(fact, "duration_months")),
        "source_page": _canonical_scalar(_fact_field(fact, "source_page")),
        "source_line": _canonical_scalar(_fact_field(fact, "source_line")),
        "raw_label": _canonical_scalar(_fact_field(fact, "raw_label")),
        "source_bbox": _canonical_scalar(_fact_field(fact, "source_bbox")),
        "extraction_method": _canonical_scalar(_fact_field(fact, "extraction_method")),
        "semantic_model": _canonical_scalar(_fact_field(fact, "semantic_model")),
        "evidence": _material_evidence(fact),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
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
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_decision(decision: ReviewDecision, *, secret: str, key_id: str) -> ReviewDecision:
    if not secret:
        raise ValueError("review signing secret is empty")
    if not decision.fact_fingerprint:
        raise ValueError("fact_fingerprint is required before signing")
    unsigned = replace(
        decision,
        auth_provider=AUTH_PROVIDER_HMAC,
        key_id=key_id.strip(),
        signature="",
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        _signing_payload(unsigned),
        hashlib.sha256,
    ).hexdigest()
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
    expected = hmac.new(
        secret.encode("utf-8"),
        _signing_payload(decision),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, decision.signature):
        return False, "SIGNATURE_INVALID"
    return True, "AUTHENTICATED"


def make_decision(
    *,
    issuer_name: str,
    symbol: str,
    period_end: str,
    metric_code: str,
    filing_sha256: str,
    reviewer_id: str,
    decision: str,
    fact_fingerprint: str,
    note: str = "",
    policy_version: str = REVIEW_POLICY_VERSION,
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
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=metric_code,
        filing_sha256=filing_sha256,
        fact_fingerprint=fact_fingerprint,
        policy_version=policy_version,
        reviewer_id=reviewer_id.strip(),
        decision=normalized,
        decided_at=datetime.now(UTC).isoformat(),
        note=note,
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
            decisions.append(
                ReviewDecision(
                    issuer_name=str(raw["issuer_name"]),
                    symbol=str(raw["symbol"]),
                    period_end=str(raw["period_end"]),
                    metric_code=str(raw["metric_code"]),
                    filing_sha256=str(raw["filing_sha256"]),
                    fact_fingerprint=str(raw.get("fact_fingerprint") or ""),
                    policy_version=str(raw.get("policy_version") or ""),
                    reviewer_id=str(raw.get("reviewer_id") or ""),
                    decision=str(raw.get("decision") or "").upper(),
                    decided_at=str(raw.get("decided_at") or ""),
                    note=str(raw.get("note") or ""),
                    auth_provider=str(raw.get("auth_provider") or ""),
                    key_id=str(raw.get("key_id") or ""),
                    signature=str(raw.get("signature") or ""),
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
    stale_fact_fingerprint: int = 0
    policy_mismatch: int = 0
    unauthenticated: int = 0
    invalid_signature: int = 0
    signing_key_unavailable: int = 0
    duplicate_decision_identities: int = 0
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
    summary = ReleaseSummary(
        policy_version=policy_version,
        decisions_loaded=len(decisions),
    )
    decision_groups: dict[str, list[ReviewDecision]] = {}
    for decision in decisions:
        decision_groups.setdefault(decision.identity, []).append(decision)
    duplicate_identities = {
        identity for identity, items in decision_groups.items() if len(items) > 1
    }
    summary.duplicate_decision_identities = len(duplicate_identities)
    by_identity: dict[str, ReviewDecision] = {
        identity: items[0]
        for identity, items in decision_groups.items()
        if len(items) == 1
    }
    updated: list[Any] = []
    matched: set[str] = set()
    for fact in facts:
        period = _canonical_period(_fact_field(fact, "period_end"))
        identity = fact_identity(
            str(_fact_field(fact, "issuer_name") or ""),
            str(_fact_field(fact, "symbol") or ""),
            period,
            str(_fact_field(fact, "metric_code") or ""),
        )
        if identity in duplicate_identities:
            # Never let JSONL ordering choose between multiple human decisions.
            # Operators must resolve the conflicting/replayed identity explicitly.
            matched.add(identity)
            updated.append(fact)
            continue
        decision = by_identity.get(identity)
        if decision is None:
            updated.append(fact)
            continue
        matched.add(identity)
        if not decision.reviewer_id:
            summary.unauthenticated += 1
            updated.append(fact)
            continue
        authenticated, auth_reason = verify_decision_signature(decision)
        if not authenticated:
            summary.unauthenticated += 1
            if auth_reason == "SIGNATURE_INVALID":
                summary.invalid_signature += 1
            if auth_reason.startswith("SIGNING_KEY_UNAVAILABLE"):
                summary.signing_key_unavailable += 1
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
        if decision.fact_fingerprint != fact_fingerprint(fact):
            summary.stale_fact_fingerprint += 1
            updated.append(fact)
            continue
        if decision.decision == DECISION_APPROVED:
            summary.approved_applied += 1
        elif decision.decision == DECISION_REJECTED:
            summary.rejected_applied += 1
        else:
            updated.append(fact)
            continue
        updated.append(replace(fact, review_status=decision.decision))
    summary.unmatched = len(
        [identity for identity in by_identity if identity not in matched]
    )
    return updated, summary


def official_release_allowed(fact: Any) -> tuple[bool, str | None]:
    return publishability_decision(fact, release_mode="OFFICIAL")
