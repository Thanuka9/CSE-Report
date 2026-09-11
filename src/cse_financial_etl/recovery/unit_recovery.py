"""Unit recovery — recover only globally unambiguous, compatible evidence (§33.3)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.compiler.structure_normalizer import normalize_unit_declaration
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_unit(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Fill a missing unit dimension only when filing-level evidence is unambiguous.

    Recovery must never use the first declaration in a mixed-scale filing and must
    never overwrite a dimension already observed on the candidate.  More specific
    cell/table resolution belongs to the compiler; this fallback is intentionally
    conservative.
    """

    declarations = context.get("unit_texts") or []
    candidates: set[tuple[str, int]] = set()
    for text in declarations:
        currency, scale = normalize_unit_declaration(str(text))
        if currency and scale is not None:
            try:
                candidates.add((str(currency).upper(), int(scale)))
            except (TypeError, ValueError):
                continue

    if not candidates:
        return {"status": "NO_CHANGE", "reason": "no_unit_evidence"}
    if len(candidates) != 1:
        return {
            "status": "NO_CHANGE",
            "reason": "ambiguous_unit_evidence",
            "candidates": sorted(f"{currency}:{scale}" for currency, scale in candidates),
        }

    resolved_currency, resolved_scale = next(iter(candidates))
    changed = 0
    incompatible = 0
    for entry in ledger.for_concept(ticket.concept):
        known_currency = str(entry.unit).upper() if entry.unit else None
        known_scale = entry.scale_factor
        if known_currency is not None and known_currency != resolved_currency:
            incompatible += 1
            if "UNIT_RECOVERY_CURRENCY_CONFLICT" not in entry.reasons:
                entry.reasons.append("UNIT_RECOVERY_CURRENCY_CONFLICT")
            continue
        if known_scale is not None and known_scale != resolved_scale:
            incompatible += 1
            if "UNIT_RECOVERY_SCALE_CONFLICT" not in entry.reasons:
                entry.reasons.append("UNIT_RECOVERY_SCALE_CONFLICT")
            continue
        if entry.unit is not None and entry.scale_factor is not None:
            continue

        if entry.unit is None:
            entry.unit = resolved_currency
        if entry.scale_factor is None:
            entry.scale_factor = resolved_scale
        if (
            entry.raw_value is not None
            and entry.normalized_value is None
            and entry.scale_factor is not None
        ):
            entry.normalized_value = entry.raw_value * entry.scale_factor
        if "unit_recovery_applied_unambiguous" not in entry.reasons:
            entry.reasons.append("unit_recovery_applied_unambiguous")
        entry.status = "unresolved" if entry.status == "rejected" else entry.status
        changed += 1

    if changed:
        return {
            "status": "RECOVERED",
            "unit": resolved_currency,
            "scale": resolved_scale,
            "changed": changed,
            "incompatible": incompatible,
        }
    return {
        "status": "NO_CHANGE",
        "reason": "no_compatible_missing_unit_dimension",
        "incompatible": incompatible,
    }
