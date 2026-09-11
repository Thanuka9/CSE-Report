"""Semantic recovery — re-evaluate each rejected row's own label only."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.accounting.semantic_candidates import generate_concept_hypotheses
from cse_financial_etl.contracts.eligibility import MIN_PUBLISHABLE_SEMANTIC_SCORE
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_semantic(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Reopen only the exact entry whose own label now has publishable semantics.

    Older recovery used any matching row label in the filing to reopen every rejected
    entry for the concept.  That allowed evidence from one row to rehabilitate another.
    Context labels may still be retained by callers for diagnostics, but they are never
    evidence ownership for a different ledger entry.
    """

    promoted = 0
    for entry in ledger.for_concept(ticket.concept):
        if entry.status != "rejected":
            continue
        if "SEMANTIC" not in " ".join(entry.reasons).upper():
            continue
        if not entry.label:
            continue

        matching = [
            hyp
            for hyp in generate_concept_hypotheses(entry.label, min_keep=0.30)
            if hyp.concept == ticket.concept
            and hyp.semantic_score >= MIN_PUBLISHABLE_SEMANTIC_SCORE
        ]
        if not matching:
            continue
        best = max(matching, key=lambda hyp: (hyp.semantic_score, hyp.total_score))
        entry.status = "unresolved"
        entry.score = max(entry.score, best.total_score)
        entry.evidence["semantic_score"] = best.semantic_score
        entry.evidence["semantic_evidence"] = list(best.evidence)
        if "semantic_recovery_reopened_own_label" not in entry.reasons:
            entry.reasons.append("semantic_recovery_reopened_own_label")
        promoted += 1

    if promoted:
        return {"status": "RECOVERED", "promoted": promoted}
    return {"status": "NO_CHANGE", "reason": "no_entry_owned_semantic_reopen"}
