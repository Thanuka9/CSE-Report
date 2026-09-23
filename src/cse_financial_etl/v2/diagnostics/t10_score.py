"""Score locked V2 SourceFacts against T10 blind source-truth items."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.contracts.investigation import SourceTruthItem
from cse_financial_etl.v2.diagnostics.real_filings import load_real_filing_cases
from cse_financial_etl.v2.diagnostics.serialization import source_fact_to_mapping
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline


def load_t10_items(path: Path) -> list[SourceTruthItem]:
    rows: list[SourceTruthItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(SourceTruthItem.model_validate_json(line))
    return rows


def _same_number(left: Decimal | None, right: object) -> bool:
    if left is None or right in {None, ""}:
        return left is None
    try:
        return left == Decimal(str(right))
    except Exception:
        return False


def _entity_of(fact: dict[str, Any]) -> str | None:
    value = fact.get("entity_scope")
    if value in {None, ""}:
        return None
    return str(value)


def _duration_of(fact: dict[str, Any]) -> int | None:
    value = fact.get("duration_months")
    if value in {None, ""}:
        return None
    return int(str(value))


def score_t10_items(
    items: list[SourceTruthItem],
    v2_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    facts_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in v2_facts:
        key = (str(fact.get("issuer_id") or ""), str(fact.get("metric_code") or ""))
        facts_by_key.setdefault(key, []).append(fact)
    tp = fp_value = fn = g01_withheld = 0
    ambiguous = 0
    duration_invented = 0
    details: list[dict[str, Any]] = []
    for item in items:
        if item.source_presence.value == "AMBIGUOUS":
            ambiguous += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "metric_code": item.metric_code,
                    "result": "AMBIGUOUS_TRUTH",
                }
            )
            continue
        if item.source_presence.value != "REPORTED":
            continue
        candidates = facts_by_key.get((item.issuer_id, item.metric_code), [])
        truth_entity = None if item.entity_scope is None else item.entity_scope.value
        matched = [
            fact
            for fact in candidates
            if _same_number(item.normalized_value, fact.get("normalized_value"))
            and _entity_of(fact) == truth_entity
        ]
        invented = [
            fact
            for fact in candidates
            if item.duration_months is None and _duration_of(fact) is not None
        ]
        if invented:
            duration_invented += 1
        if matched:
            tp += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "metric_code": item.metric_code,
                    "result": "TP",
                    "v2_value": str(matched[0].get("normalized_value")),
                    "v2_entity": _entity_of(matched[0]),
                }
            )
            continue
        if truth_entity is None and not candidates:
            g01_withheld += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "metric_code": item.metric_code,
                    "result": "G01_WITHHELD",
                    "truth": str(item.normalized_value),
                    "truth_entity": None,
                }
            )
            continue
        if candidates:
            fp_value += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "metric_code": item.metric_code,
                    "result": "VALUE_OR_ENTITY_MISMATCH",
                    "truth": str(item.normalized_value),
                    "truth_entity": truth_entity,
                    "v2_values": [str(fact.get("normalized_value")) for fact in candidates[:6]],
                    "v2_entities": [_entity_of(fact) for fact in candidates[:6]],
                }
            )
        else:
            fn += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "metric_code": item.metric_code,
                    "result": "FN",
                    "truth": str(item.normalized_value),
                    "truth_entity": truth_entity,
                }
            )
    labeled = tp + fp_value + fn
    reported = labeled + g01_withheld
    return {
        "item_count": len(items),
        "reported": reported,
        "entity_resolved_reported": labeled,
        "ambiguous": ambiguous,
        "tp": tp,
        "value_or_entity_mismatch": fp_value,
        "fn": fn,
        "g01_withheld": g01_withheld,
        "duration_invented_on_null_truth": duration_invented,
        "recall_vs_entity_resolved": None if not labeled else round(tp / labeled, 4),
        "critical_wrong_facts": fp_value,
        "note": (
            "T10 truth vs V2 SourceFacts. Unlabeled REPORTED rows are G01 withheld, "
            "not value errors. Publication gates are not applied to truth. "
            "Not certification and not holdout."
        ),
        "details": details,
        "gates": _gate_decisions(
            items,
            tp=tp,
            mismatch=fp_value,
            fn=fn,
            invented=duration_invented,
            withheld=g01_withheld,
        ),
    }


def _gate_decisions(
    items: list[SourceTruthItem],
    *,
    tp: int,
    mismatch: int,
    fn: int,
    invented: int,
    withheld: int,
) -> dict[str, Any]:
    unlabeled = [
        item
        for item in items
        if item.source_presence.value == "REPORTED" and item.entity_scope is None
    ]
    greg = [
        item for item in items if item.issuer_id == "GREG.N0000" and item.duration_months is None
    ]
    return {
        "G01": {
            "decision": "KEEP",
            "rule": (
                "Unresolved entity withholds. Do not copy issuer-name or document "
                "heading as entity. GROUP is never COMPANY."
            ),
            "evidence": (
                f"{len(unlabeled)} T10 REPORTED rows have null entity_scope "
                f"(ABL/CBNK/CTC unlabeled columns). V2 withheld {withheld} as SourceFacts."
            ),
        },
        "G02": {
            "decision": "UNTESTED",
            "rule": "Partial-context cascade remains production default.",
            "evidence": "T10 queue was VALUE_DISAGREEMENT, not cascade suppression.",
        },
        "G03": {
            "decision": "KEEP",
            "rule": (
                "Do not invent duration from Period ended. Exact-quarter remains "
                "publication policy, not source presence."
            ),
            "evidence": (
                f"{len(greg)} GREG T10 rows have duration_months null. "
                f"V2 duration inventions on null-truth rows: {invented}."
            ),
        },
        "G04": {
            "decision": "UNTESTED",
            "evidence": "No T10 OTHER-page adjudication.",
        },
        "G05": {
            "decision": "UNTESTED",
            "evidence": "No T10 continuation adjudication.",
        },
        "G06": {
            "decision": "UNTESTED",
            "evidence": "No T10 conflict-group adjudication.",
        },
        "G07": {
            "decision": "UNTESTED",
            "evidence": "No T10 collapsed-row adjudication.",
        },
        "G08": {
            "decision": "UNTESTED",
            "evidence": "Production selection is measured separately from source truth.",
        },
        "G09": {
            "decision": "KEEP",
            "rule": "Absence of Group is not Company. Do not infer COMPANY on EPS_NOTE.",
            "evidence": (
                "CIC EPS is COMPANY because the statement says Company. "
                "ATL/DIMO/GREG EPS are GROUP because they say Group. "
                "Silence is not Company."
            ),
        },
        "score": {
            "tp": tp,
            "value_or_entity_mismatch": mismatch,
            "fn": fn,
            "g01_withheld": withheld,
            "not_certification": True,
        },
    }


def collect_t10_v2_facts(root: Path, items: list[SourceTruthItem]) -> list[dict[str, Any]]:
    wanted = {item.issuer_id for item in items}
    facts: list[dict[str, Any]] = []
    for case in load_real_filing_cases(root=root, locked=True, limit=40):
        if case.issuer_id not in wanted:
            continue
        document = read_document(case.pdf_path, filing_version_id=case.case_id)
        result = run_filing_pipeline(
            document,
            issuer_id=case.issuer_id,
            issuer_name=case.issuer_name,
            issuer_type=case.issuer_type,
        )
        facts.extend(source_fact_to_mapping(fact) for fact in result.source_facts)
    return facts


def collect_holdout_v2_facts(root: Path, items: list[SourceTruthItem]) -> list[dict[str, Any]]:
    """Score holdout PDFs from the identity manifest only. Do not retune from misses."""

    wanted = {item.issuer_id for item in items}
    manifest = json.loads(
        (root / "tests" / "v2" / "source_truth" / "holdout_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    facts: list[dict[str, Any]] = []
    for row in manifest.get("items") or ():
        if not isinstance(row, dict):
            continue
        issuer_id = str(row.get("issuer_id") or "")
        if issuer_id not in wanted:
            continue
        pdf_path = root / str(row.get("local_file") or "")
        if not pdf_path.is_file():
            continue
        filing_version_id = str(row.get("filing_version_id") or issuer_id)
        document = read_document(pdf_path, filing_version_id=filing_version_id)
        result = run_filing_pipeline(
            document,
            issuer_id=issuer_id,
            issuer_name=str(row.get("legal_name") or ""),
            issuer_type=str(row.get("issuer_type") or ""),
        )
        facts.extend(source_fact_to_mapping(fact) for fact in result.source_facts)
    return facts


def score_t10_filings(root: Path, *, split: str | None = "DEV") -> dict[str, Any]:
    items = load_t10_items(root / "tests" / "v2" / "source_truth" / "items.jsonl")
    if split is not None:
        items = [item for item in items if item.split == split]
    if split == "HOLDOUT":
        facts = collect_holdout_v2_facts(root, items)
    else:
        facts = collect_t10_v2_facts(root, items)
    payload = score_t10_items(items, facts)
    payload["split"] = split
    payload["v2_source_fact_count"] = len(facts)
    payload["issuers"] = sorted({item.issuer_id for item in items})
    return payload


def score_from_baseline(root: Path) -> dict[str, Any]:
    items = load_t10_items(root / "tests" / "v2" / "source_truth" / "items.jsonl")
    facts: list[dict[str, Any]] = []
    baseline = root / "outputs" / "v2_extraction_baseline"
    for path in sorted(baseline.glob("*/source_facts.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            facts.extend(item for item in payload if isinstance(item, dict))
    if facts:
        return score_t10_items(items, facts)
    return score_t10_filings(root)
