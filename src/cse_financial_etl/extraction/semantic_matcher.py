from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from rapidfuzz import fuzz

CANONICAL_LABELS: dict[str, tuple[str, ...]] = {
    "TOP_LINE": (
        "revenue",
        "net revenue",
        "gross income",
        "total operating income",
        "total income",
        "net operating income",
        "insurance revenue",
        "gross written premium",
        "net earned premium",
        "net sales",
        "total revenue",
        "turnover",
        "interest income",
        "net interest income",
    ),
    "OPERATING_PROFIT": (
        "operating profit",
        "results from operating activities",
        "profit from operations",
        "profit from operation",
        "profit loss from operations",
        "operating profit before tax on financial services",
        "operating profit before taxes on financial services",
        "results of operating activities",
        "profit from operating activities",
        "results from operations",
        "result from operating activities",
        "ebit",
        "earnings before interest and tax",
    ),
    "PBT": (
        "profit before tax",
        "profit before taxation",
        "profit before income tax",
        "loss before tax",
        "loss before taxation",
    ),
    "PAT": (
        "profit for the period",
        "profit for the quarter",
        "profit after tax",
        "profit after taxation",
        "net profit after tax",
        "loss for the period",
        "net loss for the period",
        "net profit for the period",
        "profit attributable to equity holders",
        "profit attributable to owners of the company",
        "profit attributable to shareholders of the company",
    ),
    "EPS_BASIC": (
        "basic earnings per share",
        "basic loss per share",
        "earnings per share basic",
        "basic diluted earnings per share",
        "earnings per ordinary share",
    ),
    "EPS_DILUTED": (
        "diluted earnings per share",
        "diluted loss per share",
        "earnings per share diluted",
        "basic diluted earnings per share",
    ),
    "TOTAL_ASSETS": ("total assets",),
    "TOTAL_EQUITY": (
        "total equity",
        "total shareholders equity",
        "equity attributable to owners of the company",
        "equity attributable to equity holders",
        "shareholders funds",
        "total shareholders funds",
        "equity attributable to owners",
    ),
    "TOTAL_LIABILITIES": ("total liabilities", "liabilities total", "total liability"),
    "NAVPS": (
        "net assets per share",
        "net asset per share",
        "net book value per share",
        "net asset value per share",
    ),
}


def normalize_label(label: str) -> str:
    cleaned = re.sub(r"\([^)]*(?:rs|lkr|note)[^)]*\)", " ", label, flags=re.I)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


@dataclass(frozen=True, slots=True)
class SemanticMatch:
    metric_code: str
    score: float
    canonical_label: str
    model: str


class SemanticMatcher:
    """Regex aliases plus RapidFuzz token-set matching. No MiniLM or LLM."""

    def __init__(self, *, use_transformer: bool | None = None) -> None:
        del use_transformer
        self.model_name = "rapidfuzz-token-set"

    def match(self, label: str, metric_code: str) -> SemanticMatch:
        normalized = normalize_label(label)
        labels = CANONICAL_LABELS[metric_code]
        best_label = max(labels, key=lambda item: fuzz.token_set_ratio(normalized, item))
        fuzzy_score = fuzz.token_set_ratio(normalized, best_label) / 100
        return SemanticMatch(metric_code, fuzzy_score, best_label, self.model_name)


def apply_metric_catalog(catalog: dict[str, Any]) -> None:
    """Merge YAML catalog aliases into the in-memory canonical labels."""

    metrics = catalog.get("metrics") if isinstance(catalog, dict) else None
    if not isinstance(metrics, dict):
        return
    for code, spec in metrics.items():
        if not isinstance(spec, dict):
            continue
        aliases = spec.get("aliases") or {}
        extra: list[str] = []
        if isinstance(aliases, dict):
            for group in aliases.values():
                if isinstance(group, list):
                    extra.extend(normalize_label(str(item)) for item in group if item)
        current = CANONICAL_LABELS.get(str(code), ())
        merged = tuple(dict.fromkeys([*current, *[item for item in extra if item]]))
        if merged:
            CANONICAL_LABELS[str(code)] = merged
    get_semantic_matcher.cache_clear()


@lru_cache(maxsize=1)
def get_semantic_matcher() -> SemanticMatcher:
    os.environ.setdefault("CSE_ETL_USE_TRANSFORMER", "0")
    return SemanticMatcher(use_transformer=False)
