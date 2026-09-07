"""Semantic recovery — widen ontology / row context; do not merely lower fuzzy thresholds."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.accounting.semantic_candidates import generate_concept_hypotheses
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_semantic(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    labels = context.get("row_labels") or []
    promoted = 0
    for label in labels:
        hyps = generate_concept_hypotheses(label, min_keep=0.30)
        for hyp in hyps:
            if hyp.concept != ticket.concept:
                continue
            for entry in ledger.for_concept(ticket.concept):
                if entry.status == "rejected" and "SEMANTIC" in " ".join(entry.reasons).upper():
                    entry.status = "unresolved"
                    entry.score = max(entry.score, hyp.total_score)
                    entry.reasons.append("semantic_recovery_reopened")
                    promoted += 1
    if promoted:
        return {"status": "RECOVERED", "promoted": promoted}
    return {"status": "NO_CHANGE", "reason": "no_semantic_reopen"}
