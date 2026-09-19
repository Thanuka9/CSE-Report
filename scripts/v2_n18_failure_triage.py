"""N18 failure triage against frozen first score + locked N17 gold.

Does NOT overwrite tests/v2/universe/n18_ai_blind_first_score.json.
Reconstructs per-slot V2 facts for triage only (TRIAGE_RECONSTRUCTION).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import sys

from cse_financial_etl.v2.contracts.investigation import SourceTruthItem
from cse_financial_etl.v2.diagnostics.investigation_freeze import collect_investigation_freeze
from cse_financial_etl.v2.diagnostics.serialization import source_fact_to_mapping
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from v2_score_n18_ai_blind import (  # noqa: E402
    _as_date,
    _as_entity,
    _as_int,
    _load_items,
    _same_number,
    score_n18,
)

ROOT = Path(__file__).resolve().parents[1]
GOLD_DEFAULT = Path("tests/v2/source_truth/n17_ai_blind_gold.jsonl")
IDENTITY_DEFAULT = Path("tests/v2/source_truth/holdout_v2_identity_manifest.json")
FROZEN_SCORE_DEFAULT = Path("tests/v2/universe/n18_ai_blind_first_score.json")
OUT_DIR_DEFAULT = Path("tests/v2/universe/n18_failure_triage")

STAGE_TO_FAMILY = {
    "NONE": "ROW_NOT_FOUND",
    "NUMERIC_UNPARSED": "CELL_NOT_FOUND",
    "CONCEPT_UNRESOLVED": "CONCEPT_UNRESOLVED",
    "ENTITY_UNRESOLVED": "ENTITY_UNRESOLVED",
    "PERIOD_UNRESOLVED": "PERIOD_UNRESOLVED",
    "UNIT_UNRESOLVED": "UNIT_UNRESOLVED",
    "UNIT_DIMENSION_MISMATCH": "WRONG_UNIT",
    "PRODUCTION_SELECTION": "SELECTION_WITHHELD",
    "VALIDATION": "VALIDATION_WITHHELD",
    "PUBLICATION": "PUBLICATION_WITHHELD",
}


def _enum_val(value: object) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", str(value))


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _mismatch_primary(flags: list[str], chosen: dict[str, Any], item: SourceTruthItem) -> str:
    """One primary root-cause family for a produced-but-wrong slot."""
    if "entity" in flags:
        return "WRONG_ENTITY"
    if "duration" in flags:
        return "WRONG_DURATION"
    if "period" in flags:
        return "WRONG_PERIOD"
    if "unit" in flags:
        truth_scale = None if item.scale is None else str(item.scale)
        truth_unit = _enum_val(item.unit_dimension)
        if truth_unit == "PER_SHARE" and str(chosen.get("unit_dimension") or "") != "PER_SHARE":
            return "WRONG_UNIT"
        if truth_scale is not None and chosen.get("scale") not in {None, truth_scale}:
            try:
                if Decimal(str(chosen.get("scale"))) != Decimal(truth_scale):
                    return "WRONG_SCALE"
            except Exception:
                return "WRONG_SCALE"
        return "WRONG_UNIT"
    if "value" in flags:
        return "WRONG_VALUE_CELL"
    return "WRONG_SELECTION"


def _trace_stage_for_metric(traces: list[Any], metric: str) -> str | None:
    """Best first-failure stage among candidates resolved to metric (or unresolved near-misses)."""
    stages: list[str] = []
    for tr in traces:
        resolved = getattr(tr, "resolved_metric", None) or getattr(tr, "metric_code", None)
        if resolved == metric:
            stage = _enum_val(getattr(tr, "first_failure_stage", None))
            if stage:
                stages.append(stage)
    if not stages:
        # Concept alternatives mentioning metric but unresolved
        for tr in traces:
            alts = getattr(tr, "concept_alternatives", ()) or ()
            for alt in alts:
                if getattr(alt, "metric_code", None) == metric:
                    stage = _enum_val(getattr(tr, "first_failure_stage", None))
                    if stage:
                        stages.append(stage)
    if not stages:
        return None
    # Prefer concrete unresolved dimensions over NONE
    priority = [
        "ENTITY_UNRESOLVED",
        "PERIOD_UNRESOLVED",
        "UNIT_UNRESOLVED",
        "CONCEPT_UNRESOLVED",
        "NUMERIC_UNPARSED",
        "UNIT_DIMENSION_MISMATCH",
        "VALIDATION",
        "PUBLICATION",
        "PRODUCTION_SELECTION",
        "NONE",
    ]
    for p in priority:
        if p in stages:
            return p
    return stages[0]


def collect_holdout_runs(root: Path, identity_path: Path) -> tuple[list[dict[str, Any]], dict[str, list[Any]], dict[str, str]]:
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    facts: list[dict[str, Any]] = []
    traces_by_issuer: dict[str, list[Any]] = {}
    issuer_type: dict[str, str] = {}
    for row in identity.get("items") or ():
        if not isinstance(row, dict):
            continue
        issuer_id = str(row.get("issuer_id") or "")
        pdf_path = root / str(row.get("local_file") or "")
        issuer_type[issuer_id] = str(row.get("issuer_type") or "")
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
        traces_by_issuer[issuer_id] = list(result.traces or ())
        for fact in result.source_facts:
            mapping = source_fact_to_mapping(fact)
            mapping["currency"] = fact.currency
            mapping["scale"] = None if fact.source_scale is None else str(fact.source_scale)
            mapping["unit_dimension"] = (
                None if fact.unit_dimension is None else fact.unit_dimension.value
            )
            mapping["comparison_role"] = _enum_val(fact.comparison_role)
            mapping["raw_value"] = getattr(fact, "raw_value", None) or mapping.get("raw_value")
            mapping["source_page"] = getattr(fact, "source_page", None) or mapping.get("page")
            facts.append(mapping)
    return facts, traces_by_issuer, issuer_type


def build_triage_rows(
    items: list[SourceTruthItem],
    facts: list[dict[str, Any]],
    traces_by_issuer: dict[str, list[Any]],
    issuer_type: dict[str, str],
    score: dict[str, Any],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        key = (str(fact.get("issuer_id") or ""), str(fact.get("metric_code") or ""))
        by_key.setdefault(key, []).append(fact)

    detail_by_key = {
        (d["issuer_id"], d["metric_code"]): d
        for d in score.get("details") or []
        if isinstance(d, dict)
    }

    rows: list[dict[str, Any]] = []
    for item in items:
        key = (item.issuer_id, item.metric_code)
        candidates = by_key.get(key, [])
        detail = detail_by_key.get(key, {})
        truth_entity = _enum_val(item.entity_scope)
        truth_period = None if item.period_end is None else item.period_end.isoformat()
        presence = item.source_presence.value

        chosen: dict[str, Any] | None = None
        if candidates:
            exact = [
                f
                for f in candidates
                if _same_number(item.normalized_value, f.get("normalized_value"))
                and _as_entity(f.get("entity_scope")) == truth_entity
            ]
            chosen = exact[0] if exact else candidates[0]

        n18_result = detail.get("result")
        flags = list(detail.get("mismatch_kinds") or [])
        severity = "OK"
        root = "NONE"
        first_stage = "NONE"
        generalized = ""

        if presence == "NOT_REPORTED":
            if candidates:
                n18_result = "FALSE_POSITIVE"
                severity = "CRITICAL"
                root = "FALSE_POSITIVE_NOT_REPORTED"
                first_stage = "PRODUCTION_SELECTION"
                generalized = "Suppress emission when source metric is absent (no diluted/top-line promotion)"
            else:
                n18_result = "TN"
                severity = "OK"
                root = "NONE"
                first_stage = "NONE"
        elif presence == "REPORTED":
            if n18_result == "TP":
                severity = "OK"
                root = "NONE"
            elif n18_result == "FN":
                severity = "MISSING"
                stage = _trace_stage_for_metric(traces_by_issuer.get(item.issuer_id, []), item.metric_code)
                first_stage = stage or "ROW_NOT_FOUND"
                root = STAGE_TO_FAMILY.get(first_stage, first_stage)
                if first_stage == "NONE" and not candidates:
                    # No SourceFact and no resolved candidate → structural miss
                    root = "ROW_NOT_FOUND"
                    first_stage = "ROW_NOT_FOUND"
                generalized = f"Recover {root} for target metric emission"
            elif n18_result == "MISMATCH":
                root = _mismatch_primary(flags, chosen or {}, item)
                first_stage = "NONE"
                if "value" in flags or "entity" in flags:
                    severity = "CRITICAL_WRONG"
                    generalized = f"Fix {root} before recall work"
                else:
                    severity = "PRODUCED_WRONG"
                    generalized = f"Fix {root} context binding"

        row = {
            "filing_version_id": item.filing_version_id,
            "issuer_id": item.issuer_id,
            "issuer_type": issuer_type.get(item.issuer_id, ""),
            "metric_code": item.metric_code,
            "gold_source_presence": presence,
            "gold_raw_label": item.raw_source_label,
            "gold_raw_value": item.raw_source_value,
            "gold_normalized_value": None if item.normalized_value is None else str(item.normalized_value),
            "gold_entity_scope": truth_entity,
            "gold_period_end": truth_period,
            "gold_duration_months": item.duration_months,
            "gold_comparison_role": _enum_val(item.comparison_role),
            "gold_currency": item.currency,
            "gold_scale": None if item.scale is None else str(item.scale),
            "gold_page": item.page,
            "gold_evidence_text": item.evidence_text,
            "v2_fact_present": bool(candidates),
            "v2_raw_value": None if chosen is None else _jsonable(chosen.get("raw_value")),
            "v2_normalized_value": None if chosen is None else str(chosen.get("normalized_value")),
            "v2_entity_scope": None if chosen is None else _as_entity(chosen.get("entity_scope")),
            "v2_period_end": None if chosen is None else _as_date(chosen.get("period_end")),
            "v2_duration_months": None if chosen is None else _as_int(chosen.get("duration_months")),
            "v2_comparison_role": None if chosen is None else _jsonable(chosen.get("comparison_role")),
            "v2_currency": None if chosen is None else chosen.get("currency"),
            "v2_scale": None if chosen is None else _jsonable(chosen.get("scale")),
            "v2_source_page": None if chosen is None else chosen.get("source_page"),
            "n18_result": n18_result,
            "severity": severity,
            "first_failure_stage": first_stage,
            "root_cause_family": root,
            "mismatch_kinds": "|".join(flags) if flags else "",
            "source_verified": bool(item.evidence_text),
            "generalized_fix_candidate": generalized,
            "notes": item.notes or "",
        }
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _aggregate_counts(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    c = Counter(str(r.get(key) or "") for r in rows)
    return [{"key": k, "count": v} for k, v in c.most_common()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=GOLD_DEFAULT)
    parser.add_argument("--identity", type=Path, default=IDENTITY_DEFAULT)
    parser.add_argument("--frozen-score", type=Path, default=FROZEN_SCORE_DEFAULT)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR_DEFAULT)
    args = parser.parse_args()

    root = ROOT
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    frozen = json.loads((root / args.frozen_score).read_text(encoding="utf-8"))
    items = _load_items(root / args.gold)
    facts, traces_by_issuer, issuer_type = collect_holdout_runs(root, root / args.identity)
    score = score_n18(items, facts)
    freeze = collect_investigation_freeze(root)

    rows = build_triage_rows(items, facts, traces_by_issuer, issuer_type, score)

    # Persist full reconstruction (not the frozen first score).
    recon = {
        "id": "n18-failure-triage-reconstruction",
        "status": "TRIAGE_RECONSTRUCTION",
        "note": (
            "Per-slot reconstruction for triage only. "
            "Does not replace n18_ai_blind_first_score.json. "
            "Frozen first score remains historical unseen evidence."
        ),
        "frozen_gold_commit_sha": frozen.get("gold_commit_sha"),
        "frozen_n18_commit_ref": "dc146572985f61d828cf1b2365970291bc6451bd",
        "frozen_score_path": str(args.frozen_score).replace("\\", "/"),
        "frozen_aggregates": {
            "tp": frozen.get("tp"),
            "fn": frozen.get("fn"),
            "critical_wrong": frozen.get("critical_wrong"),
            "value_mismatch": frozen.get("value_mismatch"),
            "entity_mismatch": frozen.get("entity_mismatch"),
            "period_mismatch": frozen.get("period_mismatch"),
            "duration_mismatch": frozen.get("duration_mismatch"),
            "unit_mismatch": frozen.get("unit_mismatch"),
            "source_reported_recall": frozen.get("source_reported_recall"),
            "numeric_correctness": frozen.get("numeric_correctness"),
        },
        "reconstruction_score": {
            "tp": score["tp"],
            "fn": score["fn"],
            "critical_wrong": score["critical_wrong"],
            "value_mismatch": score["value_mismatch"],
            "entity_mismatch": score["entity_mismatch"],
            "period_mismatch": score["period_mismatch"],
            "duration_mismatch": score["duration_mismatch"],
            "unit_mismatch": score["unit_mismatch"],
            "v2_source_fact_count": score["v2_source_fact_count"],
            "source_reported_recall": score["source_reported_recall"],
            "numeric_correctness": score["numeric_correctness"],
        },
        "reconstruction_engine_sha": freeze.actual_code_sha,
        "score_matches_frozen": {
            "tp": score["tp"] == frozen.get("tp"),
            "fn": score["fn"] == frozen.get("fn"),
            "critical_wrong": score["critical_wrong"] == frozen.get("critical_wrong"),
        },
        "details": score["details"],
    }
    (out_dir / "n18_triage_reconstruction_score.json").write_text(
        json.dumps(recon, indent=2) + "\n", encoding="utf-8"
    )

    _write_csv(out_dir / "n18_failure_triage.csv", rows)
    (out_dir / "n18_failure_triage.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )

    failures = [r for r in rows if r["severity"] not in {"OK"} or r["n18_result"] == "FALSE_POSITIVE"]
    # Include FALSE_POSITIVE even if severity set; exclude pure TN/TP
    failures = [
        r
        for r in rows
        if r["n18_result"] in {"FN", "MISMATCH", "FALSE_POSITIVE"}
    ]

    def _count_csv(name: str, key: str, subset: list[dict[str, Any]] | None = None) -> None:
        src = subset if subset is not None else failures
        agg = [{"key": k, "count": v} for k, v in Counter(str(r.get(key) or "") for r in src).most_common()]
        _write_csv(out_dir / name, agg, ["key", "count"])

    _count_csv("n18_failure_by_root_cause.csv", "root_cause_family")
    _count_csv("n18_failure_by_metric.csv", "metric_code")
    _count_csv("n18_failure_by_issuer_type.csv", "issuer_type")
    _count_csv("n18_failure_by_severity.csv", "severity")

    # Statement type proxy from metric family
    for r in failures:
        m = r["metric_code"]
        if m in {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES", "NAVPS"}:
            r["statement_type"] = "SOFP"
        elif m in {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT", "EPS_BASIC", "EPS_DILUTED"}:
            r["statement_type"] = "PL"
        else:
            r["statement_type"] = "OTHER"
    _count_csv("n18_failure_by_statement_type.csv", "statement_type")

    reported = [r for r in rows if r["gold_source_presence"] == "REPORTED"]
    not_reported = [r for r in rows if r["gold_source_presence"] == "NOT_REPORTED"]
    tp = sum(1 for r in reported if r["n18_result"] == "TP")
    missing = sum(1 for r in reported if r["n18_result"] == "FN")
    produced_wrong = sum(1 for r in reported if r["n18_result"] == "MISMATCH")
    critical_wrong = sum(1 for r in reported if r["severity"] == "CRITICAL_WRONG")
    fp_nr = sum(1 for r in not_reported if r["n18_result"] == "FALSE_POSITIVE")

    critical_rows = [r for r in reported if r["severity"] == "CRITICAL_WRONG"]
    p0a_table = [
        {
            "filing": r["issuer_id"],
            "metric": r["metric_code"],
            "gold": r["gold_normalized_value"],
            "v2": r["v2_normalized_value"],
            "gold_entity": r["gold_entity_scope"],
            "v2_entity": r["v2_entity_scope"],
            "root_cause": r["root_cause_family"],
            "mismatch_kinds": r["mismatch_kinds"],
            "generalized_fix": r["generalized_fix_candidate"],
            "gold_evidence": (r["gold_evidence_text"] or "")[:180],
        }
        for r in critical_rows
    ]

    root_counts = Counter(r["root_cause_family"] for r in failures)
    ranked = []
    for family, count in root_counts.most_common():
        if family in {"NONE"}:
            continue
        sev_boost = 3 if family.startswith("WRONG_") or family == "FALSE_POSITIVE_NOT_REPORTED" else 1
        if family == "WRONG_ENTITY":
            sev_boost = 5
        ranked.append(
            {
                "root_cause_family": family,
                "n18_failure_count": count,
                "severity_weight": sev_boost,
                "priority_score": sev_boost * count,
                "generalizability": "HIGH" if count >= 5 else ("MEDIUM" if count >= 2 else "LOW"),
            }
        )
    ranked.sort(key=lambda x: (-x["priority_score"], -x["n18_failure_count"]))

    summary = {
        "id": "n18-failure-summary",
        "status": "TRIAGE_COMPLETE" if score["tp"] == frozen.get("tp") else "TRIAGE_COMPLETE_WITH_RECON_DRIFT",
        "frozen_gold_commit_sha": frozen.get("gold_commit_sha"),
        "frozen_n18_score_commit": "dc146572985f61d828cf1b2365970291bc6451bd",
        "total_gold_reported": len(reported),
        "TP": tp,
        "missing": missing,
        "produced_wrong": produced_wrong,
        "critical_wrong": critical_wrong,
        "false_positive_not_reported": fp_nr,
        "accounting_check": {
            "reported_minus_tp_minus_fn": len(reported) - tp - missing,
            "equals_produced_wrong": (len(reported) - tp - missing) == produced_wrong,
        },
        "frozen_vs_recon": recon["score_matches_frozen"],
        "root_cause_counts": dict(root_counts),
        "metric_counts": dict(Counter(r["metric_code"] for r in failures)),
        "issuer_type_counts": dict(Counter(r["issuer_type"] for r in failures)),
        "p0a_critical_wrong_table": p0a_table,
        "ranked_engineering_targets": ranked[:8],
        "note": (
            "N18 set is now regression/DEV evidence after triage. "
            "Do not claim unseen holdout success on re-runs. "
            "No code fixes until clusters reviewed."
        ),
    }
    (out_dir / "n18_failure_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    # Also mirror summary/triage at universe root for plan path convenience
    (root / "tests/v2/universe/n18_failure_triage.csv").write_text(
        (out_dir / "n18_failure_triage.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (root / "tests/v2/universe/n18_failure_triage.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    (root / "tests/v2/universe/n18_failure_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({k: summary[k] for k in (
        "TP", "missing", "produced_wrong", "critical_wrong",
        "false_positive_not_reported", "root_cause_counts", "ranked_engineering_targets",
        "frozen_vs_recon", "status",
    )}, indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
