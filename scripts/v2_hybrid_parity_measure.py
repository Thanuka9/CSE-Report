"""Compare V1 extracted facts vs V2 hybrid (V1 baseline + V2 recovery) on the pinned 829.

Primary KPI: like-for-like preserved/agreeing target facts, not candidate counts.
Does not set extraction.engine: v2.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET_METRICS = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "NAVPS",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}
DEFAULT_COHORT = (
    ROOT
    / "reports/v1_v2_same_input/alias_pct_other_selrank_full829_2026-09-20/pinned_cohort.json"
)


UNION_REASONS = {
    "V1_BASELINE_PRESERVED",
    "V1_V2_AGREE",
    "V2_RECOVERY",
    "V2_SUPERSEDES_V1",
    "CONFLICT_UNRESOLVED",
}


STOCK_METRICS = {
    "NAVPS",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}


def _key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    comparison = str(row.get("comparison_role") or "").upper()
    if comparison in {"", "UNKNOWN", "NONE"}:
        comparison = "CURRENT"
    duration = str(row.get("duration_months") if row.get("duration_months") not in (None, "") else "")
    metric = str(row.get("metric_code") or "")
    if metric in STOCK_METRICS:
        duration = ""
    return (
        str(row.get("pdf_sha256") or ""),
        metric,
        str(row.get("entity_scope") or ""),
        str(row.get("period_end") or ""),
        comparison,
        duration,
    )


def _v1_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    from cse_financial_etl.extraction.statement_extractor import extract_filing as extract_v1

    period = date.fromisoformat(item["period_end"])
    facts = extract_v1(
        Path(item["abs_path"]),
        str(item.get("legal_name") or item["issuer_dir"]),
        str(item.get("symbol") or item["issuer_dir"]),
        period,
    )
    out: list[dict[str, Any]] = []
    for fact in facts:
        if fact.metric_code not in TARGET_METRICS:
            continue
        if fact.status != "EXTRACTED" or fact.normalized_value is None:
            continue
        out.append(
            {
                "engine": "v1",
                "pdf_sha256": item["pdf_sha256"],
                "symbol": item.get("symbol"),
                "metric_code": fact.metric_code,
                "entity_scope": fact.entity_scope,
                "period_end": item["period_end"],
                "normalized_value": str(fact.normalized_value),
                "status": fact.status,
                "comparison_role": getattr(fact, "comparison_role", None) or "CURRENT",
                "duration_months": getattr(fact, "duration_months", None),
            }
        )
    return out


def _hybrid_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    from cse_financial_etl.v2.contracts.enums import EntityScope
    from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
    from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts

    period = date.fromisoformat(item["period_end"])
    result = run_pdf_pipeline(
        Path(item["abs_path"]),
        issuer_id=str(item.get("symbol") or item["issuer_dir"]),
        filing_version_id=f"{item.get('symbol') or item['issuer_dir']}-{item['period_end']}",
        target_period_end=period,
        issuer_name=str(item.get("legal_name") or ""),
        issuer_type=str(item.get("issuer_type") or ""),
        v1_baseline_facts=True,
        v1_source_observations=False,
    )
    selected = ()
    for ent in (EntityScope.COMPANY, EntityScope.GROUP, EntityScope.BANK):
        sel = select_pipeline_facts(result.source_facts, period_end=period, expected_entity=ent)
        if sel:
            selected = sel
            break
    selected_ids = {fact.fact_id for fact in selected}
    out: list[dict[str, Any]] = []
    for fact in result.source_facts:
        if fact.metric_code not in TARGET_METRICS:
            continue
        out.append(
            {
                "engine": "v2_hybrid",
                "pdf_sha256": item["pdf_sha256"],
                "symbol": item.get("symbol"),
                "metric_code": fact.metric_code,
                "entity_scope": None if fact.entity_scope is None else fact.entity_scope.value,
                "period_end": fact.period_end.isoformat(),
                "normalized_value": str(fact.normalized_value),
                "publication_status": fact.publication_status.value,
                "reason_codes": list(fact.reason_codes or ()),
                "draft_selected": fact.fact_id in selected_ids,
                "comparison_role": None if fact.comparison_role is None else fact.comparison_role.value,
                "duration_months": fact.duration_months,
            }
        )
    return out


def _reasons(row: dict[str, Any]) -> set[str]:
    codes = row.get("reason_codes") or []
    if isinstance(codes, str):
        codes = [part.strip() for part in codes.replace(",", "|").split("|") if part.strip()]
    return {str(code) for code in codes if code}


def _is_eligible(row: dict[str, Any]) -> bool:
    selected = row.get("draft_selected")
    if selected in (True, "True", "true", "1"):
        return True
    return str(row.get("publication_status") or "") == "ELIGIBLE"


def _values_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    raw_left = str(left.get("normalized_value") or "").strip()
    raw_right = str(right.get("normalized_value") or "").strip()
    if raw_left == raw_right:
        return True
    try:
        return Decimal(raw_left) == Decimal(raw_right)
    except InvalidOperation:
        return False


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")


def _classify(
    v1_rows: list[dict[str, Any]],
    hybrid_rows: list[dict[str, Any]],
    ocr_shas: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ocr_shas = ocr_shas or set()
    hybrid_by_key: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in hybrid_rows:
        hybrid_by_key.setdefault(_key(row), []).append(row)
    disagreements: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen_v1: set[tuple[str, ...]] = set()
    for row in v1_rows:
        key = _key(row)
        if key in seen_v1:
            continue
        seen_v1.add(key)
        matches = hybrid_by_key.get(key, [])
        eligible = [item for item in matches if _is_eligible(item)]
        reasons = set().union(*(_reasons(item) for item in matches)) if matches else set()
        hybrid_value = eligible[0].get("normalized_value") if eligible else (
            matches[0].get("normalized_value") if matches else ""
        )
        if eligible and _values_equal(row, eligible[0]):
            classification = "AGREE_PRESERVE"
        elif eligible and "V2_SUPERSEDES_V1" in reasons:
            classification = "SUPERSEDE_V2_STRONGER"
        elif "CONFLICT_UNRESOLVED" in reasons:
            classification = "QUARANTINE"
        elif eligible:
            classification = "UNEXPLAINED_VALUE_MISMATCH"
        elif matches:
            classification = "UNEXPLAINED_LOSS_WITHHELD"
        elif key[0] in ocr_shas:
            classification = "QUARANTINE_OCR"
        else:
            classification = "UNEXPLAINED_LOSS_ABSENT"
        counts[classification] += 1
        if classification != "AGREE_PRESERVE":
            disagreements.append(
                {
                    "classification": classification,
                    "pdf_sha256": key[0],
                    "symbol": row.get("symbol") or "",
                    "issuer_dir": row.get("issuer_dir") or "",
                    "metric_code": key[1],
                    "entity_scope": key[2],
                    "period_end": key[3],
                    "comparison_role": key[4],
                    "duration_months": key[5],
                    "v1_value": row.get("normalized_value") or "",
                    "hybrid_value": hybrid_value or "",
                    "hybrid_status": (eligible or matches or [{}])[0].get("publication_status") or "",
                    "reason_codes": "|".join(sorted(reasons)),
                }
            )
    v1_keys = {_key(row) for row in v1_rows}
    for key, matches in hybrid_by_key.items():
        if key in v1_keys:
            continue
        eligible = [item for item in matches if _is_eligible(item)]
        if not eligible:
            continue
        reasons = set().union(*(_reasons(item) for item in matches))
        classification = "V2_RECOVERY_EXTRA"
        counts[classification] += 1
        disagreements.append(
            {
                "classification": classification,
                "pdf_sha256": key[0],
                "symbol": eligible[0].get("symbol") or "",
                "issuer_dir": eligible[0].get("issuer_dir") or "",
                "metric_code": key[1],
                "entity_scope": key[2],
                "period_end": key[3],
                "comparison_role": key[4],
                "duration_months": key[5],
                "v1_value": "",
                "hybrid_value": eligible[0].get("normalized_value") or "",
                "hybrid_status": eligible[0].get("publication_status") or "",
                "reason_codes": "|".join(sorted(reasons)),
            }
        )
    return disagreements, dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "reports/v1_v2_same_input/hybrid_baseline",
    )
    args = parser.parse_args()
    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    filings = list(cohort["filings"])
    if args.limit > 0:
        filings = filings[: args.limit]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ledger_v1 = args.out_dir / "ledger_v1.csv"
    ledger_hybrid = args.out_dir / "ledger_hybrid.csv"
    jsonl_v1 = args.out_dir / "ledger_v1.jsonl"
    jsonl_hybrid = args.out_dir / "ledger_hybrid.jsonl"
    progress_path = args.out_dir / "progress.jsonl"
    done_shas = set()
    if progress_path.exists():
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                done_shas.add(json.loads(line).get("pdf_sha256"))
            except json.JSONDecodeError:
                continue
    pending = [item for item in filings if item.get("pdf_sha256") not in done_shas]
    print(f"cohort={len(filings)} resume_skip={len(filings) - len(pending)} pending={len(pending)}")

    v1_rows = _load_jsonl(jsonl_v1)
    hybrid_rows = _load_jsonl(jsonl_hybrid)
    errors: list[dict[str, str]] = []
    error_path = args.out_dir / "errors.jsonl"
    if error_path.exists():
        errors.extend(_load_jsonl(error_path))

    v1_fields = [
        "engine",
        "pdf_sha256",
        "symbol",
        "issuer_dir",
        "metric_code",
        "entity_scope",
        "period_end",
        "comparison_role",
        "duration_months",
        "normalized_value",
        "status",
    ]
    hybrid_fields = [
        "engine",
        "pdf_sha256",
        "symbol",
        "issuer_dir",
        "metric_code",
        "entity_scope",
        "period_end",
        "comparison_role",
        "duration_months",
        "normalized_value",
        "publication_status",
        "reason_codes",
        "draft_selected",
    ]

    def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                out = dict(row)
                if isinstance(out.get("reason_codes"), list):
                    out["reason_codes"] = "|".join(str(code) for code in out["reason_codes"] if code)
                writer.writerow(out)

    def one(item: dict[str, Any]) -> dict[str, Any]:
        local: dict[str, Any] = {"item": item, "v1": [], "hybrid": [], "error": None}
        try:
            local["v1"] = [
                {**row, "issuer_dir": item["issuer_dir"]} for row in _v1_rows(item)
            ]
        except Exception as exc:
            local["error"] = f"v1 {type(exc).__name__}: {exc}"
        try:
            local["hybrid"] = [
                {**row, "issuer_dir": item["issuer_dir"]} for row in _hybrid_rows(item)
            ]
        except Exception as exc:
            hybrid_err = f"hybrid {type(exc).__name__}: {exc}"
            local["error"] = f"{local['error']} | {hybrid_err}" if local["error"] else hybrid_err
        return local

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [pool.submit(one, item) for item in pending]
            for index, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                sha = str(result["item"].get("pdf_sha256") or "")
                if result["error"]:
                    err = {"pdf_sha256": sha, "error": result["error"]}
                    errors.append(err)
                    _append_jsonl(error_path, [err])
                v1_rows.extend(result["v1"])
                hybrid_rows.extend(result["hybrid"])
                _append_jsonl(jsonl_v1, result["v1"])
                _append_jsonl(jsonl_hybrid, result["hybrid"])
                with progress_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "pdf_sha256": sha,
                                "v1": len(result["v1"]),
                                "hybrid": len(result["hybrid"]),
                                "error": result["error"],
                            }
                        )
                        + "\n"
                    )
                if index % 10 == 0 or index == len(futures):
                    print(
                        f"  measured {index}/{len(futures)} total_done={len(done_shas) + index} "
                        f"errors={len(errors)}",
                        flush=True,
                    )
                    _write_csv(ledger_v1, v1_rows, v1_fields)
                    _write_csv(ledger_hybrid, hybrid_rows, hybrid_fields)

    v1_keys = {_key(row) for row in v1_rows}
    hybrid_eligible = [row for row in hybrid_rows if _is_eligible(row)]
    hybrid_keys = {_key(row) for row in hybrid_eligible}
    v1_only = sorted(v1_keys - hybrid_keys)
    hybrid_only = sorted(hybrid_keys - v1_keys)
    both = v1_keys & hybrid_keys
    reason_counts: Counter[str] = Counter()
    for row in hybrid_rows:
        reason_counts.update(_reasons(row) & UNION_REASONS)
    ocr_shas = {
        str(item.get("pdf_sha256") or "")
        for item in errors
        if "OCR_REQUIRED_NOT_AVAILABLE" in str(item.get("error") or "")
        or "OcrRouteNotEnabledError" in str(item.get("error") or "")
    }
    non_ocr_errors = [item for item in errors if item.get("pdf_sha256") not in ocr_shas]
    disagreements, class_counts = _classify(v1_rows, hybrid_rows, ocr_shas=ocr_shas)
    unexplained = sum(
        class_counts.get(name, 0)
        for name in (
            "UNEXPLAINED_LOSS_ABSENT",
            "UNEXPLAINED_LOSS_WITHHELD",
            "UNEXPLAINED_VALUE_MISMATCH",
        )
    )
    preserved = class_counts.get("AGREE_PRESERVE", 0)
    completed = len(
        {
            json.loads(line).get("pdf_sha256")
            for line in progress_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if progress_path.exists()
        else set()
    )
    summary = {
        "id": "v2-hybrid-v1-baseline-parity",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "filings_attempted": len(filings),
        "filings_completed": completed,
        "filings_error": len(errors),
        "filings_ocr_quarantine": len(ocr_shas),
        "filings_error_non_ocr": len(non_ocr_errors),
        "v1_target_extracted": len(v1_rows),
        "hybrid_eligible_or_selected": len(hybrid_eligible),
        "identical_keys": len(both),
        "v1_only_keys": len(v1_only),
        "hybrid_only_keys": len(hybrid_only),
        "coverage_vs_v1": (len(both) / len(v1_keys)) if v1_keys else None,
        "preserved_agree": preserved,
        "unexplained_losses_or_mismatches": unexplained,
        "classification_counts": class_counts,
        "reason_counts": dict(reason_counts),
        "parity_pass": (
            completed == len(filings)
            and unexplained == 0
            and len(non_ocr_errors) == 0
            and len(v1_keys) > 0
        ),
        "errors": errors[:50],
    }
    _write_csv(ledger_v1, v1_rows, v1_fields)
    _write_csv(ledger_hybrid, hybrid_rows, hybrid_fields)
    disagreement_fields = [
        "classification",
        "pdf_sha256",
        "symbol",
        "issuer_dir",
        "metric_code",
        "entity_scope",
        "period_end",
        "comparison_role",
        "duration_months",
        "v1_value",
        "hybrid_value",
        "hybrid_status",
        "reason_codes",
    ]
    _write_csv(args.out_dir / "disagreements.csv", disagreements, disagreement_fields)
    (args.out_dir / "hybrid_parity_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    with (args.out_dir / "v1_only_keys.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["pdf_sha256", "metric_code", "entity_scope", "period_end", "comparison_role", "duration_months"]
        )
        writer.writerows(v1_only)
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=2))


if __name__ == "__main__":
    main()
