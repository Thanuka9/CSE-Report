"""V2 diagnostics: stage metrics, fact identity diffs, and replay pins."""

from __future__ import annotations

from cse_financial_etl.v2.diagnostics.fact_diff import FactDiffClass, diff_fact_populations
from cse_financial_etl.v2.diagnostics.golden import (
    GoldenFact,
    GoldenGates,
    evaluate_golden_gates,
    score_golden,
)
from cse_financial_etl.v2.diagnostics.replay import (
    RuntimePin,
    collect_runtime_pin,
    facts_are_deterministic,
    replay_fact_diff,
)
from cse_financial_etl.v2.diagnostics.serialization import source_fact_to_mapping
from cse_financial_etl.v2.diagnostics.shadow import shadow_diff
from cse_financial_etl.v2.diagnostics.stage_metrics import StageMetrics

__all__ = [
    "FactDiffClass",
    "GoldenFact",
    "GoldenGates",
    "RuntimePin",
    "StageMetrics",
    "collect_runtime_pin",
    "diff_fact_populations",
    "evaluate_golden_gates",
    "facts_are_deterministic",
    "replay_fact_diff",
    "score_golden",
    "shadow_diff",
    "source_fact_to_mapping",
]
