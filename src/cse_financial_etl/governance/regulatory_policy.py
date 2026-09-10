"""Regulatory and semantic policy helpers for CSE quarterly production.

R4 intentionally remains local/file based.  It introduces no database and no XBRL
runtime dependency.  These helpers encode disclosure expectations and source semantics
that are stable enough to enforce deterministically while allowing unknown master-data
attributes to fail closed instead of being guessed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Any


MAIN_SEGMENTS = {"MAIN", "DIRI_SAVI", "DEBT", "UNKNOWN"}
EMPOWER_SEGMENTS = {"EMPOWER"}


@dataclass(frozen=True, slots=True)
class DisclosureExpectation:
    listing_segment: str
    quarter: int
    statement_requirement: str
    due_days: int | None
    note: str


def expected_disclosure(listing_segment: str | None, quarter: int) -> DisclosureExpectation:
    """Return the filing expectation without inventing unavailable segment metadata.

    MAIN-style issuers: Q1-Q3 within 45 days; Q4 within two months.  Empower Board:
    full interim statements are half-yearly while Q1/Q3 use supplementary disclosures.
    UNKNOWN is deliberately treated as a normal full-quarter expectation for extraction
    but remains explicitly labelled UNKNOWN so coverage governance can distinguish it.
    """

    if quarter not in {1, 2, 3, 4}:
        raise ValueError(f"quarter must be 1..4, got {quarter}")
    segment = (listing_segment or "UNKNOWN").strip().upper()
    if segment in EMPOWER_SEGMENTS:
        if quarter in {1, 3}:
            return DisclosureExpectation(
                segment,
                quarter,
                "SUPPLEMENTARY_ONLY",
                45,
                "Empower Board Q1/Q3 supplementary disclosure; do not expect a full interim statement.",
            )
        return DisclosureExpectation(
            segment,
            quarter,
            "FULL_INTERIM_REQUIRED",
            60 if quarter == 4 else 45,
            "Empower Board half-year/full-year interim statement expectation.",
        )
    return DisclosureExpectation(
        segment,
        quarter,
        "FULL_INTERIM_REQUIRED",
        60 if quarter == 4 else 45,
        "Full quarterly interim statement expectation; UNKNOWN segment remains auditable.",
    )


def canonical_issuer_id(legal_name: str, configured_id: str | None = None) -> str:
    """Return a stable local issuer identifier without requiring a database.

    Explicit configured IDs always win.  Otherwise a deterministic identifier is made
    from the normalized legal name.  The original name remains an attribute, never the
    fact/security join key in generated master data.
    """

    if configured_id and configured_id.strip():
        return configured_id.strip()
    normalized = re.sub(r"[^A-Z0-9]+", " ", legal_name.upper()).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16].upper()
    return f"CSEI_{digest}"


def insurance_accounting_regime(
    period_end: date,
    *,
    explicit_regime: str | None = None,
) -> str:
    """Classify insurance presentation basis conservatively.

    2026 contains issuer-specific transition relief/SoAT treatment, so no automatic
    SLFRS 17 assumption is made.  An explicit filing/config value is required in 2026+.
    """

    if explicit_regime:
        return explicit_regime.strip().upper()
    if period_end.year < 2026:
        return "SLFRS4_LEGACY"
    return "INSURANCE_REGIME_UNRESOLVED"


def price_semantic_from_row(row: dict[str, Any]) -> tuple[str, Any] | None:
    """Select only last-traded/trade price semantics; never generic closing price."""

    for key in ("last_traded_price", "last_trade_price", "trade_price", "price"):
        raw = row.get(key)
        if raw not in (None, ""):
            return key, raw
    return None


def quarantine_matches(
    configured: dict[str, Any],
    *,
    issuer_name: str,
    symbol: str,
    period_end: str,
    filing_id: int | None,
    sha256: str | None,
) -> bool:
    """Match a known quarantine only when immutable filing identity also agrees.

    Legacy entries without filing_id/sha256 intentionally do not match once immutable
    identity is supplied by the runtime; they must be recalibrated from exact evidence.
    """

    if str(configured.get("issuer_name") or "").strip().upper() != issuer_name.strip().upper():
        return False
    if str(configured.get("symbol") or "").strip().upper() != symbol.strip().upper():
        return False
    if str(configured.get("period_end") or "").strip() != period_end.strip():
        return False
    expected_filing_id = configured.get("filing_id")
    expected_sha = str(configured.get("sha256") or "").strip().lower()
    if filing_id is not None:
        if expected_filing_id in (None, "") or int(expected_filing_id) != int(filing_id):
            return False
    if sha256:
        if not expected_sha or expected_sha != sha256.strip().lower():
            return False
    return True


def q4_publication_allowed(*, duration_months: int | None, explicit_quarter: bool) -> bool:
    """R4 contract: published Q4 flows must be explicitly reported three-month facts."""

    return bool(explicit_quarter and duration_months == 3)
