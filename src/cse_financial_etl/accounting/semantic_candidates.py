"""High-recall semantic candidate generation — regex + RapidFuzz only (§17)."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from cse_financial_etl.accounting.ontology import CONCEPT_ALIASES


@dataclass(frozen=True, slots=True)
class ConceptHypothesis:
    concept: str
    semantic_score: float
    structural_score: float
    accounting_score: float
    total_score: float
    evidence: tuple[str, ...]


def generate_concept_hypotheses(
    label: str,
    *,
    statement_type: str | None = None,
    structural_score: float = 0.0,
    accounting_score: float = 0.0,
    min_keep: float = 0.35,
) -> list[ConceptHypothesis]:
    """Retain uncertain candidates; never drop early on a high threshold."""

    normalized = " ".join(label.lower().replace("'", "").split())
    if not normalized:
        return []
    hypotheses: list[ConceptHypothesis] = []
    for concept, aliases in CONCEPT_ALIASES.items():
        if statement_type == "FINANCIAL_POSITION" and concept in {
            "PAT",
            "PBT",
            "OPERATING_PROFIT",
            "TOP_LINE",
        }:
            continue
        if statement_type in {"PROFIT_LOSS", "COMPREHENSIVE_INCOME"} and concept in {
            "TOTAL_ASSETS",
            "TOTAL_EQUITY",
            "TOTAL_LIABILITIES",
            "NAVPS",
        }:
            continue
        best = 0.0
        best_alias = ""
        for alias in aliases:
            if normalized == alias or normalized.startswith(alias + " "):
                score = 1.0
            else:
                score = fuzz.token_set_ratio(normalized, alias) / 100.0
            if score > best:
                best = score
                best_alias = alias
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
                evidence=(f"alias:{best_alias}", f"label:{normalized}"),
            )
        )
    hypotheses.sort(key=lambda h: h.total_score, reverse=True)
    return hypotheses
