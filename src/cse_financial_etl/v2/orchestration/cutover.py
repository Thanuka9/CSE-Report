"""Cutover gates. V1 remains the production default until institutional gates pass."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.exceptions import V2Error


class CutoverNotReadyError(V2Error):
    """Institutional cutover (gold, frozen universe, V1 deletion) is not complete."""


class CutoverGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    name: str
    passed: bool
    detail: str


class CutoverDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    ready: bool
    default_engine: Literal["V1", "V2"]
    gates: tuple[CutoverGate, ...]


REQUIRED_GATES: tuple[str, ...] = (
    "canonical_document",
    "column_owned_context",
    "provenance",
    "quarter_flow",
    "q4_reported_only",
    "explicit_liabilities",
    "unresolved_cannot_publish",
    "source_derived_distinct",
    "explicit_release_context",
    "coverage_floors",
    "workbook_reconciliation",
    "golden_corpus",
    "frozen_universe",
    "determinism",
    "current_universe",
    "draft_numeric_workbook",
    "official_human_review",
)


def evaluate_cutover(
    results: dict[str, bool], *, details: dict[str, str] | None = None
) -> CutoverDecision:
    details = details or {}
    gates = tuple(
        CutoverGate(name=name, passed=bool(results.get(name)), detail=details.get(name, ""))
        for name in REQUIRED_GATES
    )
    ready = all(gate.passed for gate in gates)
    return CutoverDecision(ready=ready, default_engine="V2" if ready else "V1", gates=gates)


def assert_v1_remains_default(decision: CutoverDecision) -> None:
    """Production extracts with V1 until ready. V1 extract_filing stays importable."""

    from cse_financial_etl.extraction.statement_extractor import extract_filing as extract_filing_v1

    if extract_filing_v1 is None:
        raise CutoverNotReadyError("V1 extract_filing must remain importable")
    if decision.ready:
        raise CutoverNotReadyError(
            "ready=true still requires institutional sign-off before deleting V1"
        )
