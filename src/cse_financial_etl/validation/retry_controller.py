"""Bounded, failure-specific extraction retry controller (Phase One).

Retries may change parser/layout interpretation. They never relax business rules
(Company→Group, 3M→YTD, etc.).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.equation_engine import ValidationOutcome, ValidationResult

DEFAULT_MAX_RETRY_ROUNDS = 2

STRATEGY_BY_FAILURE: dict[str, str] = {
    "BALANCE_SHEET_IDENTITY": "RESELECT_SOFP_CANDIDATES",
    "BALANCE_SHEET_SANITY": "RESELECT_SOFP_CANDIDATES",
    "CROSS_METRIC_CONTEXT_INCONSISTENT": "RESELECT_PNL_CONTEXT",
    "PAT_TAX_BRIDGE": "RESELECT_PNL_CONTEXT",
    "EPS_RECONCILIATION": "RESELECT_PNL_CONTEXT",
    "NAVPS_RECONCILIATION": "RESELECT_SOFP_CANDIDATES",
    "ENTITY_MISMATCH": "REBUILD_ENTITY_SPANS",
    "PERIOD_MISMATCH": "REBUILD_DURATION_SPANS",
    "UNIT_CONFLICT": "RESEARCH_UNIT_SCOPE",
    "UNIT_NOT_RESOLVED": "RESEARCH_UNIT_SCOPE",
    "METRIC_NOT_FOUND": "EXPAND_SEMANTIC_SEARCH",
    "VALUE_CONTEXT_UNRESOLVED": "EXPAND_SEMANTIC_SEARCH",
    "WRONG_STATEMENT_REGION": "RESELECT_STATEMENT_REGION",
    "COLUMN_AMBIGUOUS": "RESELECT_PNL_CONTEXT",
    "CUMULATIVE_ONLY": "REBUILD_DURATION_SPANS",
    "LOW_CERTAINTY": "EXPAND_SEMANTIC_SEARCH",
    "INCOMPLETE_EXTRACTION": "EXPAND_SEMANTIC_SEARCH",
}

# Core publish metrics where an incomplete extraction is worth a bounded retry.
CORE_RETRY_METRICS = frozenset(
    {
        "PAT",
        "PBT",
        "TOP_LINE",
        "OPERATING_PROFIT",
        "TOTAL_ASSETS",
        "TOTAL_EQUITY",
        "TOTAL_LIABILITIES",
        "EPS_BASIC",
        "EPS_DILUTED",
        "EPS_SELECTED",
        "NAVPS",
    }
)

# Statuses that may recover under an alternate layout/unit/entity pass.
ACTIONABLE_EXTRACTION_STATUSES = frozenset(
    {
        "NOT_FOUND_BY_PARSER",
        "VALUE_CONTEXT_UNRESOLVED",
        "UNIT_NOT_RESOLVED",
        "PERIOD_NOT_RESOLVED",
        "ENTITY_NOT_RESOLVED",
        "WRONG_STATEMENT_REGION",
        "COLUMN_AMBIGUOUS",
        "CUMULATIVE_ONLY",
        "LOW_CERTAINTY",
        "UNIT_CONFLICT",
    }
)

_STATUS_TO_RULE: dict[str, str] = {
    "UNIT_NOT_RESOLVED": "UNIT_NOT_RESOLVED",
    "UNIT_CONFLICT": "UNIT_CONFLICT",
    "CUMULATIVE_ONLY": "PERIOD_MISMATCH",
    "PERIOD_NOT_RESOLVED": "PERIOD_MISMATCH",
    "ENTITY_NOT_RESOLVED": "ENTITY_MISMATCH",
    "WRONG_STATEMENT_REGION": "WRONG_STATEMENT_REGION",
    "COLUMN_AMBIGUOUS": "COLUMN_AMBIGUOUS",
    "VALUE_CONTEXT_UNRESOLVED": "VALUE_CONTEXT_UNRESOLVED",
    "LOW_CERTAINTY": "LOW_CERTAINTY",
    "NOT_FOUND_BY_PARSER": "METRIC_NOT_FOUND",
}


@dataclass(slots=True)
class RetryAttempt:
    round: int
    strategy: str
    failure_rule_id: str
    validation_before: str
    validation_after: str | None = None
    detail: str = ""
    metrics_touched: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "retry_round": self.round,
            "strategy": self.strategy,
            "failure": self.failure_rule_id,
            "validation_before": self.validation_before,
            "validation_after": self.validation_after,
            "detail": self.detail,
            "metrics_touched": self.metrics_touched,
        }


@dataclass(slots=True)
class RetryOutcome:
    facts: list[ExtractedFact]
    attempts: list[RetryAttempt]
    final_results: list[ValidationResult]
    recovered: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "final_results": [result.as_dict() for result in self.final_results],
        }


ExtractFn = Callable[..., list[ExtractedFact]]
ValidateFn = Callable[[list[ExtractedFact]], list[ValidationResult]]


def extraction_gap_triggers(
    facts: Iterable[ExtractedFact],
) -> list[ValidationResult]:
    """Synthesize retry triggers for actionable incomplete core-metric extractions."""

    triggers: list[ValidationResult] = []
    for fact in facts:
        if fact.metric_code not in CORE_RETRY_METRICS:
            continue
        if fact.status not in ACTIONABLE_EXTRACTION_STATUSES:
            continue
        rule_id = _STATUS_TO_RULE.get(fact.status, "INCOMPLETE_EXTRACTION")
        triggers.append(
            ValidationResult(
                rule_id,
                ValidationOutcome.FAIL,
                f"Incomplete extraction for {fact.metric_code}: {fact.status}",
                evidence={
                    "metrics": [fact.metric_code],
                    "status": fact.status,
                    "metric_code": fact.metric_code,
                },
            )
        )
    return triggers


def _failures(results: list[ValidationResult]) -> list[ValidationResult]:
    return [
        result
        for result in results
        if result.outcome in {ValidationOutcome.FAIL, ValidationOutcome.WARN}
    ]


def strategy_for(result: ValidationResult) -> str:
    return STRATEGY_BY_FAILURE.get(result.rule_id, "RESELECT_STATEMENT_REGION")


class RetryController:
    def __init__(
        self,
        *,
        max_rounds: int = DEFAULT_MAX_RETRY_ROUNDS,
        extract_fn: ExtractFn | None = None,
        validate_fn: ValidateFn | None = None,
    ) -> None:
        self.max_rounds = max_rounds
        self.extract_fn = extract_fn
        self.validate_fn = validate_fn

    def run(
        self,
        initial_facts: list[ExtractedFact],
        *,
        pdf_path: Path,
        issuer_name: str,
        symbol: str,
        period_end: Any,
        validate: ValidateFn | None = None,
        extract: ExtractFn | None = None,
        lineage_dir: Path | None = None,
        extra_failures: list[ValidationResult] | None = None,
        extract_kwargs: dict[str, Any] | None = None,
    ) -> RetryOutcome:
        validate_fn = validate or self.validate_fn
        extract_fn = extract or self.extract_fn
        if validate_fn is None:
            raise ValueError("validate_fn is required")

        facts = list(initial_facts)
        attempts: list[RetryAttempt] = []
        results = validate_fn(facts)
        pending = _failures(results)
        if extra_failures:
            pending = list(pending) + list(extra_failures)
        if not pending:
            gap_triggers = extraction_gap_triggers(facts)
            pending = list(gap_triggers)
        if not pending or extract_fn is None:
            return RetryOutcome(facts, attempts, results, recovered=False)

        base_kwargs = dict(extract_kwargs or {})
        for round_number in range(1, self.max_rounds + 1):
            if not pending:
                break
            focus = pending[0]
            strategy = strategy_for(focus)
            attempt = RetryAttempt(
                round=round_number,
                strategy=strategy,
                failure_rule_id=focus.rule_id,
                validation_before=focus.outcome.value,
                detail=focus.detail,
                metrics_touched=list(focus.evidence.get("metrics") or focus.evidence.keys()),
            )
            # Controlled re-extract: same business rules, alternate layout pass.
            kwargs: dict[str, Any] = dict(base_kwargs)
            if strategy == "RESEARCH_UNIT_SCOPE":
                kwargs["force_unit_rescan"] = True
            if strategy in {
                "RESELECT_PNL_CONTEXT",
                "REBUILD_DURATION_SPANS",
                "EXPAND_SEMANTIC_SEARCH",
            }:
                kwargs["prefer_exact_quarter"] = True
            if strategy in {
                "RESELECT_SOFP_CANDIDATES",
                "REBUILD_ENTITY_SPANS",
                "RESELECT_STATEMENT_REGION",
            }:
                kwargs["prefer_standalone_sofp"] = True
            try:
                refreshed = extract_fn(
                    pdf_path,
                    issuer_name,
                    symbol,
                    period_end,
                    **kwargs,
                )
            except TypeError:
                # Extractors that do not accept retry flags still get a clean re-run.
                refreshed = extract_fn(pdf_path, issuer_name, symbol, period_end)
            facts = list(refreshed)
            results = validate_fn(facts)
            pending = _failures(results) + extraction_gap_triggers(facts)
            after = next(
                (item for item in results if item.rule_id == focus.rule_id),
                None,
            )
            if after is None and focus.rule_id in STRATEGY_BY_FAILURE:
                # Extraction-gap triggers are not equation results; treat recovery by status.
                metric = None
                metrics = focus.evidence.get("metrics")
                if isinstance(metrics, list) and metrics:
                    metric = metrics[0]
                elif isinstance(focus.evidence.get("metric_code"), str):
                    metric = focus.evidence["metric_code"]
                if metric:
                    recovered_fact = next(
                        (fact for fact in facts if fact.metric_code == metric),
                        None,
                    )
                    if recovered_fact and recovered_fact.status in {
                        "EXTRACTED",
                        "EXTRACTED_DERIVED",
                    }:
                        attempt.validation_after = ValidationOutcome.PASS.value
                    else:
                        attempt.validation_after = (
                            recovered_fact.status if recovered_fact else None
                        )
                else:
                    attempt.validation_after = None
            else:
                attempt.validation_after = after.outcome.value if after else None
            attempts.append(attempt)

        recovered = bool(attempts) and not (
            _failures(results) or extraction_gap_triggers(facts)
        )
        outcome = RetryOutcome(facts, attempts, results, recovered=recovered)
        if lineage_dir is not None:
            lineage_dir.mkdir(parents=True, exist_ok=True)
            (lineage_dir / "retry_lineage.json").write_text(
                json.dumps(outcome.as_dict(), indent=2),
                encoding="utf-8",
            )
        return outcome
