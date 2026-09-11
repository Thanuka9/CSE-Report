"""High-recall semantic candidate generation — regex + RapidFuzz only (§17).

No language model is involved anywhere in this module. Anchored regex patterns
are the primary channel (score 1.0). Curated exact regex matches are authoritative
for semantic identity; exclusion patterns guard the fuzzy alias fallback so a
broad similarity such as ``Income tax expense`` can never become revenue merely
because it shares the token ``income``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from cse_financial_etl.accounting.ontology import (
    CONCEPT_ALIASES,
    CONCEPT_EXCLUSIONS,
    CONCEPT_PATTERNS,
    FINANCIAL_POSITION_CONCEPTS,
    PROFIT_LOSS_CONCEPTS,
)

_FLOW_ONLY = set(PROFIT_LOSS_CONCEPTS) - {"TOP_LINE"}
_STOCK_ONLY = set(FINANCIAL_POSITION_CONCEPTS)
_UNIT_PAREN_RE = re.compile(
    r"\((?:rs\.?|lkr|usd|cents?|'?000|mn|in\s+rs\.?\s*'?000|rs\.?\s*'?000|rs\.?\s*mn|note\s*\d*|\d+(?:\.\d+)?)\)",
    re.I,
)
_SLASH_ALT_RE = re.compile(
    r"\b(profit|loss|earnings|income|gain|expense|expenses|cost|costs)\s*/\s*\(?\s*"
    r"(profit|loss|earnings|income|gain|expense|expenses|cost|costs)\)?(?=\s|$)",
    re.I,
)
_LEADING_QUALIFIER_RE = re.compile(r"^(?:less|add|plus|minus)\s*:?\s*", re.I)
_TRAILING_NOTE_RE = re.compile(r"\s+notes?\s*\d*$", re.I)


@dataclass(frozen=True, slots=True)
class ConceptHypothesis:
    concept: str
    semantic_score: float
    structural_score: float
    accounting_score: float
    total_score: float
    evidence: tuple[str, ...]


def normalize_label(label: str) -> str:
    """Canonical label form used for matching (never for publication)."""

    text = label.replace("’", "'").replace("‘", "'")
    text = _UNIT_PAREN_RE.sub(" ", text)
    text = re.sub(r"\(\s*(loss|profit|expenses?|income|gain|costs?)\s*\)", r"\1", text, flags=re.I)
    text = _SLASH_ALT_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"[/:;,\-–—]+", " ", text)
    text = re.sub(r"[()]", " ", text)
    text = _LEADING_QUALIFIER_RE.sub("", text)
    text = _TRAILING_NOTE_RE.sub("", text)
    text = text.replace("'", "")
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"\bnon controlling\b", "non-controlling", text)
    text = re.sub(r"\bnon current\b", "non-current", text)
    return text


def generate_concept_hypotheses(
    label: str,
    *,
    statement_type: str | None = None,
    structural_score: float = 0.0,
    accounting_score: float = 0.0,
    min_keep: float = 0.55,
) -> list[ConceptHypothesis]:
    """Retain uncertain candidates above ``min_keep``; fuzzy exclusions fail closed."""

    normalized = normalize_label(label)
    if not normalized:
        return []
    hypotheses: list[ConceptHypothesis] = []
    for concept in {*CONCEPT_PATTERNS.keys(), *CONCEPT_ALIASES.keys()}:
        if statement_type == "FINANCIAL_POSITION" and concept in _FLOW_ONLY:
            continue
        if statement_type in {"PROFIT_LOSS", "COMPREHENSIVE_INCOME"} and concept in _STOCK_ONLY:
            continue

        # A curated anchored regex is the strongest semantic evidence and must be
        # evaluated before broad fuzzy exclusions. This prevents the ontology
        # from contradicting itself when a deliberately supported label contains
        # a token (for example ``before tax``) that is unsafe only for fuzzy
        # matching. Exclusions still fail closed for every fallback candidate.
        best = 0.0
        best_evidence = ""
        for pattern in CONCEPT_PATTERNS.get(concept, ()):
            if pattern.search(normalized):
                best = 1.0
                best_evidence = f"regex:{pattern.pattern}"
                break

        if best < 1.0:
            if any(p.search(normalized) for p in CONCEPT_EXCLUSIONS.get(concept, ())):
                continue
            for alias in CONCEPT_ALIASES.get(concept, ()):
                if normalized == alias:
                    score = 1.0
                elif normalized.startswith(alias + " "):
                    score = 0.86 + 0.1 * (len(alias) / len(normalized))
                else:
                    ratio = max(fuzz.ratio(normalized, alias), fuzz.token_sort_ratio(normalized, alias)) / 100.0
                    score = ratio * 0.85
                if score > best:
                    best = score
                    best_evidence = f"alias:{alias}"
        if best < min_keep:
            continue
        total = 0.55 * best + 0.25 * structural_score + 0.20 * accounting_score
        hypotheses.append(
            ConceptHypothesis(
                concept=concept,
                semantic_score=round(best, 4),
                structural_score=round(structural_score, 4),
                accounting_score=round(accounting_score, 4),
                total_score=round(total, 4),
                evidence=(best_evidence, f"label:{normalized}"),
            )
        )
    hypotheses.sort(key=lambda h: (h.total_score, h.concept), reverse=True)
    return hypotheses
