"""N18: score V2 SourceFacts once against locked N17 AI blind gold.

Do not retune the engine before writing the first frozen score artifact.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.contracts.investigation import SourceTruthItem
from cse_financial_etl.v2.diagnostics.investigation_freeze import collect_investigation_freeze
from cse_financial_etl.v2.diagnostics.serialization import source_fact_to_mapping
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline

ROOT = Path(__file__).resolve().parents[1]
GOLD_DEFAULT = Path("tests/v2/source_truth/n17_ai_blind_gold.jsonl")
IDENTITY_DEFAULT = Path("tests/v2/source_truth/holdout_v2_identity_manifest.json")
OUT_DEFAULT = Path("tests/v2/universe/n18_ai_blind_first_score.json")


def _git_sha(root: Path) -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except Exception:
        return "UNKNOWN"


def _same_number(left: Decimal | None, right: object) -> bool:
    if left is None or right in {None, ""}:
        return left is None
    try:
        return left == Decimal(str(right))
    except Exception:
        return False


def _as_date(value: object) -> str | None:
    if value in {None, ""}:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _as_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    return int(str(value))


def _as_entity(value: object) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def _load_items(path: Path) -> list[SourceTruthItem]:
    rows: list[SourceTruthItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(SourceTruthItem.model_validate_json(line))
    return rows


def collect_n17_v2_facts(root: Path, identity_path: Path) -> list[dict[str, Any]]:
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    facts: list[dict[str, Any]] = []
    for row in identity.get("items") or ():
        if not isinstance(row, dict):
            continue
        issuer_id = str(row.get("issuer_id") or "")
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
        for fact in result.source_facts:
            mapping = source_fact_to_mapping(fact)
            # Enrich for unit/scale checks (not in compact serializer).
            mapping["currency"] = fact.currency
            mapping["scale"] = (
                None if fact.source_scale is None else str(fact.source_scale)
            )
            mapping["unit_dimension"] = (
                None if fact.unit_dimension is None else fact.unit_dimension.value
            )
            facts.append(mapping)
    return facts


def score_n18(items: list[SourceTruthItem], facts: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        key = (str(fact.get("issuer_id") or ""), str(fact.get("metric_code") or ""))
        by_key.setdefault(key, []).append(fact)

    tp = fn = 0
    value_mismatch = entity_mismatch = period_mismatch = 0
    duration_mismatch = unit_mismatch = 0
    critical_wrong = 0
    details: list[dict[str, Any]] = []
    reported = [i for i in items if i.source_presence.value == "REPORTED"]
    not_reported = sum(1 for i in items if i.source_presence.value == "NOT_REPORTED")
    ambiguous = sum(1 for i in items if i.source_presence.value == "AMBIGUOUS")

    for item in reported:
        truth_entity = None if item.entity_scope is None else item.entity_scope.value
        truth_period = None if item.period_end is None else item.period_end.isoformat()
        truth_duration = item.duration_months
        truth_unit = None if item.unit_dimension is None else item.unit_dimension.value
        truth_scale = None if item.scale is None else str(item.scale)
        truth_currency = item.currency
        candidates = by_key.get((item.issuer_id, item.metric_code), [])
        if not candidates:
            fn += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "filing_version_id": item.filing_version_id,
                    "metric_code": item.metric_code,
                    "result": "FN",
                    "truth": str(item.normalized_value),
                }
            )
            continue

        # Prefer exact value+entity match; else best candidate for mismatch taxonomy.
        exact = [
            f
            for f in candidates
            if _same_number(item.normalized_value, f.get("normalized_value"))
            and _as_entity(f.get("entity_scope")) == truth_entity
        ]
        chosen = exact[0] if exact else candidates[0]
        flags: list[str] = []
        if not _same_number(item.normalized_value, chosen.get("normalized_value")):
            flags.append("value")
            value_mismatch += 1
        if _as_entity(chosen.get("entity_scope")) != truth_entity:
            flags.append("entity")
            entity_mismatch += 1
        if _as_date(chosen.get("period_end")) != truth_period:
            flags.append("period")
            period_mismatch += 1
        if _as_int(chosen.get("duration_months")) != truth_duration:
            flags.append("duration")
            duration_mismatch += 1
        unit_ok = True
        if truth_unit is not None and str(chosen.get("unit_dimension") or "") != truth_unit:
            unit_ok = False
        if truth_currency is not None and chosen.get("currency") not in {None, truth_currency}:
            # currency present and disagrees
            unit_ok = False
        if truth_scale is not None and chosen.get("scale") not in {None, truth_scale}:
            try:
                if Decimal(str(chosen.get("scale"))) != Decimal(truth_scale):
                    unit_ok = False
            except Exception:
                unit_ok = False
        if not unit_ok:
            flags.append("unit")
            unit_mismatch += 1

        if not flags:
            tp += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "filing_version_id": item.filing_version_id,
                    "metric_code": item.metric_code,
                    "result": "TP",
                    "v2_value": str(chosen.get("normalized_value")),
                }
            )
        else:
            # Value or entity wrong on a reported slot is critical.
            if "value" in flags or "entity" in flags:
                critical_wrong += 1
            details.append(
                {
                    "issuer_id": item.issuer_id,
                    "filing_version_id": item.filing_version_id,
                    "metric_code": item.metric_code,
                    "result": "MISMATCH",
                    "mismatch_kinds": flags,
                    "truth": str(item.normalized_value),
                    "truth_entity": truth_entity,
                    "v2_value": str(chosen.get("normalized_value")),
                    "v2_entity": _as_entity(chosen.get("entity_scope")),
                }
            )

    scored = len(reported)
    source_reported_recall = None if scored == 0 else round(tp / scored, 6)
    # Numeric correctness among slots where V2 produced a candidate.
    numeric_den = tp + value_mismatch
    numeric_correctness = None if numeric_den == 0 else round(tp / numeric_den, 6)

    return {
        "total_slots": len(items),
        "reported_scored_count": scored,
        "not_reported_count": not_reported,
        "ambiguous_count": ambiguous,
        "tp": tp,
        "fn": fn,
        "value_mismatch": value_mismatch,
        "entity_mismatch": entity_mismatch,
        "period_mismatch": period_mismatch,
        "duration_mismatch": duration_mismatch,
        "unit_mismatch": unit_mismatch,
        "critical_wrong": critical_wrong,
        "source_reported_recall": source_reported_recall,
        "numeric_correctness": numeric_correctness,
        "v2_source_fact_count": len(facts),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=GOLD_DEFAULT)
    parser.add_argument("--identity", type=Path, default=IDENTITY_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument(
        "--gold-commit-sha",
        default=None,
        help="Immutable N17 gold commit SHA (defaults to current HEAD)",
    )
    args = parser.parse_args()

    root = ROOT
    items = _load_items(root / args.gold)
    facts = collect_n17_v2_facts(root, root / args.identity)
    score = score_n18(items, facts)
    freeze = collect_investigation_freeze(root)
    gold_commit = args.gold_commit_sha or _git_sha(root)

    # Compact public artifact: keep mismatch examples, drop full TP list noise.
    mismatch_examples = [
        d for d in score["details"] if d.get("result") in {"FN", "MISMATCH"}
    ][:80]
    payload = {
        "id": "n18-ai-blind-first-score",
        "recovery_step": "N18",
        "status": "FIRST_SCORE_FROZEN_UNTOUCHED",
        "gold_path": str(args.gold).replace("\\", "/"),
        "gold_commit_sha": gold_commit,
        "engine_code_sha": freeze.actual_code_sha,
        "investigation_base_sha": freeze.investigation_base_sha,
        "total_slots": score["total_slots"],
        "reported_scored_count": score["reported_scored_count"],
        "not_reported_count": score["not_reported_count"],
        "ambiguous_count": score["ambiguous_count"],
        "tp": score["tp"],
        "fn": score["fn"],
        "value_mismatch": score["value_mismatch"],
        "entity_mismatch": score["entity_mismatch"],
        "period_mismatch": score["period_mismatch"],
        "duration_mismatch": score["duration_mismatch"],
        "unit_mismatch": score["unit_mismatch"],
        "critical_wrong": score["critical_wrong"],
        "source_reported_recall": score["source_reported_recall"],
        "numeric_correctness": score["numeric_correctness"],
        "v2_source_fact_count": score["v2_source_fact_count"],
        "issuers": sorted({i.issuer_id for i in items}),
        "mismatch_examples": mismatch_examples,
        "note": (
            "Untouched first N18 score against locked n17_ai_blind_gold. "
            "Do not retune V2 before freezing this artifact."
        ),
    }
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "mismatch_examples"}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
