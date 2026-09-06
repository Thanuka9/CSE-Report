from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from cse_financial_etl.domain.enums import UnitScope
from cse_financial_etl.domain.models import UnitCandidate


class UnitDetectionError(ValueError):
    """Base class for unit-resolution failures."""


class UnitNotDetectedError(UnitDetectionError):
    """Raised when an absolute monetary metric has no reliable unit."""


class UnitConflictError(UnitDetectionError):
    """Raised when equally applicable evidence disagrees."""


@dataclass(frozen=True, slots=True)
class UnitPattern:
    pattern_id: str
    regex: re.Pattern[str]
    currency: str
    scale_factor: int


PATTERNS: tuple[UnitPattern, ...] = (
    UnitPattern(
        "lkr_billion",
        re.compile(
            r"\b(?:lkr|rs\.?|sri\s+lank(?:a|an)\s+rupees?)\s*(?:in\s+)?(?:bn|billions?)\b",
            re.I,
        ),
        "LKR",
        1_000_000_000,
    ),
    UnitPattern(
        "lkr_million",
        re.compile(
            r"\b(?:lkr|rs\.?|sri\s+lank(?:a|an)\s+rupees?)\s*(?:in\s+)?(?:mn|millions?)\b",
            re.I,
        ),
        "LKR",
        1_000_000,
    ),
    UnitPattern(
        "lkr_paren_million",
        re.compile(r"\(\s*(?:rs\.?|lkr)\s*mn\s*\)", re.I),
        "LKR",
        1_000_000,
    ),
    UnitPattern(
        "lkr_rs_space_thousand",
        re.compile(r"\b(?:rs\.?|lkr)\s+0{3}s?\b", re.I),
        "LKR",
        1_000,
    ),
    UnitPattern(
        "lkr_in_rs_thousands",
        re.compile(r"\bin\s+(?:rs\.?|lkr)\s*thousands?\b", re.I),
        "LKR",
        1_000,
    ),
    UnitPattern(
        "lkr_thousand",
        re.compile(
            r"\b(?:lkr|rs\.?|sri\s+lank(?:a|an)\s+rupees?)\s*(?:in\s+)?(?:['’]\s*0{3}s?|thousands?)\b",
            re.I,
        ),
        "LKR",
        1_000,
    ),
    UnitPattern(
        "lkr_thousand_inverse",
        re.compile(
            r"\b(?:in\s+)?thousands?\s+of\s+(?:sri\s+lank(?:a|an)\s+)?rupees?\b",
            re.I,
        ),
        "LKR",
        1_000,
    ),
    UnitPattern(
        "lkr_million_inverse",
        re.compile(
            r"\b(?:in\s+)?millions?\s+of\s+(?:sri\s+lank(?:a|an)\s+)?rupees?\b",
            re.I,
        ),
        "LKR",
        1_000_000,
    ),
    UnitPattern(
        "usd_thousand",
        re.compile(r"(?:\busd\b|us\$)\s*(?:['’]\s*0{3}s?|thousands?)\b", re.I),
        "USD",
        1_000,
    ),
    UnitPattern(
        "lkr_unit",
        re.compile(r"(?:\blkr\b|\brs\.?(?=\s|$)|\bsri\s+lank(?:a|an)\s+rupees?\b)", re.I),
        "LKR",
        1,
    ),
    UnitPattern("usd_unit", re.compile(r"(?:\busd\b|us\$)", re.I), "USD", 1),
)

SCOPE_PRIORITY: dict[UnitScope, int] = {
    UnitScope.METRIC: 0,
    UnitScope.ROW: 0,
    UnitScope.CELL: 0,
    UnitScope.COLUMN: 1,
    UnitScope.TABLE: 2,
    UnitScope.STATEMENT: 3,
    UnitScope.PAGE: 4,
    UnitScope.REPORT: 5,
}


def configure_unit_patterns(payload: dict[str, object] | None) -> None:
    """Replace compiled patterns from YAML; keep the built-in list if YAML is empty."""

    global PATTERNS, SCOPE_PRIORITY
    if not payload:
        return
    raw_patterns = payload.get("patterns") if isinstance(payload, dict) else None
    loaded: list[UnitPattern] = []
    if isinstance(raw_patterns, list):
        for item in raw_patterns:
            if not isinstance(item, dict):
                continue
            try:
                loaded.append(
                    UnitPattern(
                        str(item["id"]),
                        re.compile(str(item["regex"])),
                        str(item["currency"]),
                        int(item["scale_factor"]),
                    )
                )
            except (KeyError, TypeError, ValueError, re.error):
                continue
    if loaded:
        PATTERNS = tuple(loaded)
    raw_priority = payload.get("scope_priority") if isinstance(payload, dict) else None
    if isinstance(raw_priority, dict):
        mapped: dict[UnitScope, int] = {}
        for key, value in raw_priority.items():
            try:
                mapped[UnitScope(str(key))] = int(value)
            except (TypeError, ValueError):
                continue
        if mapped:
            SCOPE_PRIORITY = mapped


def detect_candidates(
    text: str,
    *,
    scope: UnitScope,
    page: int | None = None,
    distance: float = 0.0,
) -> list[UnitCandidate]:
    """Return the most specific non-overlapping unit matches in one text block."""

    candidates: list[UnitCandidate] = []
    occupied: list[tuple[int, int]] = []
    for unit_pattern in PATTERNS:
        for match in unit_pattern.regex.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            candidates.append(
                UnitCandidate(
                    source_text=match.group(0),
                    currency=unit_pattern.currency,
                    scale_factor=unit_pattern.scale_factor,
                    scope=scope,
                    page=page,
                    distance=distance,
                    pattern_id=unit_pattern.pattern_id,
                )
            )
    return candidates


def compose_unit_text(*parts: str) -> str:
    """Join adjacent currency and scale fragments into one detector string."""

    chunks = [re.sub(r"\s+", " ", part).strip() for part in parts if part and part.strip()]
    return " ".join(chunks)


def prefer_explicit_scale(candidates: list[UnitCandidate]) -> list[UnitCandidate]:
    """Within the same page and scope, currency+scale outranks a bare currency."""

    if not candidates:
        return candidates
    kept: list[UnitCandidate] = []
    for candidate in candidates:
        scaled_peers = [
            other
            for other in candidates
            if other.page == candidate.page
            and other.scope == candidate.scope
            and other.currency == candidate.currency
            and other.scale_factor > 1
        ]
        if candidate.scale_factor == 1 and scaled_peers:
            continue
        kept.append(candidate)
    return kept or candidates


def resolve_unit(candidates: Iterable[UnitCandidate]) -> UnitCandidate:
    """Resolve by scope, then proximity; fail closed on an equal-priority conflict."""

    ordered = prefer_explicit_scale(
        sorted(
            candidates,
            key=lambda item: (SCOPE_PRIORITY[item.scope], item.distance),
        )
    )
    if not ordered:
        raise UnitNotDetectedError("UNIT_NOT_DETECTED")

    winner = ordered[0]
    winner_key = (SCOPE_PRIORITY[winner.scope], winner.distance)
    peers = [
        candidate
        for candidate in ordered
        if (SCOPE_PRIORITY[candidate.scope], candidate.distance) == winner_key
    ]
    interpretations = {(candidate.currency, candidate.scale_factor) for candidate in peers}
    if len(interpretations) > 1:
        raise UnitConflictError("UNIT_CONFLICT")
    return winner
