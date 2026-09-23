"""E02: full-universe CandidateTrace census with N18 taxonomy + entity layout patterns.

Does not retune extraction. Does not claim WRONG_ENTITY counts (needs source truth).
WRONG_ENTITY remains N18-confirmed only; universe reports entity-resolution prevalence
and source layout patterns as supporting evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cse_financial_etl.config import infer_issuer_type
from cse_financial_etl.v2.contracts.investigation import SOURCE_TARGET_METRICS
from cse_financial_etl.v2.diagnostics.investigation_freeze import collect_investigation_freeze
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.resolution.column_context import (
    _column_kinds,
    _entity_banners,
)
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.taxonomy.matcher import accounting_regime_for

try:
    from cse_financial_etl.v2.statements.continuation import detect_continuation_bridge_links
except ImportError:  # pragma: no cover - optional until continuation lands
    def detect_continuation_bridge_links(document, regions):  # type: ignore[no-redef]
        return ()

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path("tests/v2/universe/e02_universe_candidate_trace")
PERIODS = ("2025-12-31", "2026-03-31", "2026-06-30")

# STOCK metrics have no flow duration. An unresolved duration on these is correct,
# not evidence of missing 3M/6M/9M context.
STOCK_TARGET_METRICS = frozenset(
    {"NAVPS", "TOTAL_EQUITY", "TOTAL_ASSETS", "TOTAL_LIABILITIES"}
)

# Map engine FirstFailureStage (+ status dims) onto N18 recovery taxonomy labels.
STAGE_TO_N18 = {
    "ENTITY_UNRESOLVED": "ENTITY_UNRESOLVED",
    "PERIOD_UNRESOLVED": "PERIOD_UNRESOLVED",
    "UNIT_UNRESOLVED": "UNIT_UNRESOLVED",
    "CONCEPT_UNRESOLVED": "CONCEPT_UNRESOLVED",
    "VALIDATION": "VALIDATION_WITHHELD",
    "PUBLICATION": "SOURCEFACT_WITHHELD",
    "PRODUCTION_SELECTION": "SELECTION_WITHHELD",
    "NUMERIC_UNPARSED": "CELL_NOT_FOUND",
    "UNIT_DIMENSION_MISMATCH": "UNIT_UNRESOLVED",
    "NONE": "NONE",
}

N18_COMPARE = {
    "ENTITY_UNRESOLVED": 36,
    "WRONG_ENTITY": 7,  # confirmed on N18 only — not counted from universe
    "ROW_NOT_FOUND": 26,
}


def classify_n18_taxonomy(*, stage: str, duration_status: str | None, metric: str) -> str:
    """A candidate-level diagnostic, not proof of a source-reported target fact."""
    family = STAGE_TO_N18.get(stage, stage)
    if (
        metric not in STOCK_TARGET_METRICS
        and duration_status == "UNRESOLVED"
        and family == "NONE"
    ):
        return "DURATION_UNRESOLVED"
    return family


@dataclass(frozen=True)
class FilingJob:
    pdf_path: str
    issuer_folder: str
    period: str


def discover_jobs(root: Path, periods: tuple[str, ...]) -> list[FilingJob]:
    filings = root / "data" / "raw" / "filings"
    jobs: list[FilingJob] = []
    if not filings.is_dir():
        return jobs
    for issuer_dir in sorted(filings.iterdir()):
        if not issuer_dir.is_dir():
            continue
        for pdf in sorted(issuer_dir.glob("*.pdf")):
            period = pdf.name.split("_")[0]
            if period not in periods:
                continue
            jobs.append(
                FilingJob(
                    pdf_path=str(pdf),
                    issuer_folder=issuer_dir.name,
                    period=period,
                )
            )
    return jobs


def _enum_val(value: object) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", str(value))


def classify_entity_layout(
    *,
    document: Any,
    statements: tuple[Any, ...],
    regions: tuple[Any, ...],
) -> list[dict[str, Any]]:
    region_by_id = {r.region_id: r for r in regions}
    links = detect_continuation_bridge_links(document, regions)
    cont_pages = {link.to_page for link in links}
    rows: list[dict[str, Any]] = []
    for statement in statements:
        region = region_by_id.get(statement.statement_id)
        kinds = _column_kinds(statement)
        monetary_indices = [i for i, k in enumerate(kinds) if k == "monetary"]
        monetary_count = len(monetary_indices)
        banners = _entity_banners(document, region) if region is not None else []
        banner_scopes = []
        for _x, scope in banners:
            val = _enum_val(scope)
            if val and val not in banner_scopes:
                banner_scopes.append(val)
        bound_scopes = []
        unresolved_monetary = 0
        for i in monetary_indices:
            col = statement.columns[i]
            scope = _enum_val(col.entity_scope)
            if scope is None:
                unresolved_monetary += 1
            elif scope not in bound_scopes:
                bound_scopes.append(scope)

        has_group = any(s in {"GROUP", "CONSOLIDATED"} for s in banner_scopes + bound_scopes)
        has_company = any(s in {"COMPANY", "SEPARATE"} for s in banner_scopes + bound_scopes)
        has_bank = any(s == "BANK" for s in banner_scopes + bound_scopes)

        if has_group and has_company:
            pattern = "GROUP_AND_COMPANY_BOTH_EXPLICIT"
        elif has_group and has_bank:
            pattern = "GROUP_AND_BANK_BOTH_EXPLICIT"
        elif has_group and not has_company and not has_bank:
            pattern = "SINGLE_GROUP_BANNER"
        elif has_company and not has_group and not has_bank:
            pattern = "SINGLE_COMPANY_BANNER"
        elif has_bank and not has_group and not has_company:
            pattern = "SINGLE_BANK_BANNER"
        elif unresolved_monetary == monetary_count and monetary_count > 0:
            pattern = "UNLABELLED_COLUMNS"
        elif not banner_scopes and monetary_count > 0:
            pattern = "UNLABELLED_COLUMNS"
        else:
            pattern = "OTHER_OR_MIXED"

        banner_count = len(banners)
        mismatch = bool(monetary_count and banner_count and banner_count != monetary_count)
        page_start = min(
            (ref.page_number for ref in statement.source_refs),
            default=None,
        )
        continuation = bool(page_start is not None and page_start in cont_pages)

        rows.append(
            {
                "statement_id": statement.statement_id,
                "statement_type": _enum_val(statement.statement_type),
                "layout_family": pattern,
                "banner_scopes": "|".join(banner_scopes),
                "bound_scopes": "|".join(bound_scopes),
                "entity_banner_count": banner_count,
                "monetary_column_count": monetary_count,
                "banner_count_ne_monetary_count": mismatch,
                "unresolved_monetary_columns": unresolved_monetary,
                "continuation_inherited_entity_schema": continuation,
            }
        )
    return rows


def process_one(job_dict: dict[str, str]) -> dict[str, Any]:
    pdf_path = Path(job_dict["pdf_path"])
    issuer_folder = job_dict["issuer_folder"]
    period = job_dict["period"]
    issuer_id = issuer_folder  # folder is legal-name style; symbol unknown
    # Prefer symbol-like if folder looks like SYMBOL.N0000 — rare; else name.
    issuer_name = issuer_folder.replace("_", " ")
    issuer_type = infer_issuer_type(issuer_name) or "GENERAL"
    filing_version_id = f"{issuer_folder}-{period}"
    try:
        document = read_document(pdf_path, filing_version_id=filing_version_id)
        result = run_filing_pipeline(
            document,
            issuer_id=issuer_id,
            issuer_name=issuer_name,
            issuer_type=issuer_type,
        )
        regions = detect_statement_regions(document)
        layouts = classify_entity_layout(
            document=document,
            statements=result.statements,
            regions=regions,
        )
        target_set = set(SOURCE_TARGET_METRICS)
        candidates: list[dict[str, Any]] = []
        metrics_seen: set[str] = set()
        for tr in result.traces:
            metric = tr.resolved_metric
            if metric is None and tr.concept_alternatives:
                for alt in tr.concept_alternatives:
                    if getattr(alt, "metric_code", None) in target_set:
                        metric = alt.metric_code
                        break
            if metric not in target_set:
                continue
            metrics_seen.add(metric)
            stage = _enum_val(tr.first_failure_stage) or "NONE"
            n18 = classify_n18_taxonomy(
                stage=stage,
                duration_status=_enum_val(tr.duration_status),
                metric=metric,
            )
            candidates.append(
                {
                    "filing_version_id": filing_version_id,
                    "issuer_folder": issuer_folder,
                    "issuer_type": issuer_type,
                    "period": period,
                    "metric_code": metric,
                    "statement_type": tr.statement_type,
                    "first_failure_stage": stage,
                    "n18_family": n18,
                    "entity_status": _enum_val(tr.entity_status),
                    "period_status": _enum_val(tr.period_status),
                    "duration_status": _enum_val(tr.duration_status),
                    "unit_status": _enum_val(tr.unit_status),
                    "concept_status": _enum_val(tr.concept_status),
                    "source_fact_created": bool(tr.source_fact_created),
                    "entity_scope": _enum_val(tr.entity_scope),
                }
            )
        # No target candidate is a search signal, NOT proof a reported row was lost.
        # ROW_NOT_FOUND requires independently reviewed source presence.
        row_not_found = []
        for metric in SOURCE_TARGET_METRICS:
            if metric not in metrics_seen:
                row_not_found.append(
                    {
                        "filing_version_id": filing_version_id,
                        "issuer_folder": issuer_folder,
                        "issuer_type": issuer_type,
                        "period": period,
                        "metric_code": metric,
                        "statement_type": "",
                        "first_failure_stage": "NO_TARGET_CANDIDATE",
                        "n18_family": "NO_TARGET_CANDIDATE",
                        "entity_status": "",
                        "period_status": "",
                        "duration_status": "",
                        "unit_status": "",
                        "concept_status": "",
                        "source_fact_created": False,
                        "entity_scope": "",
                    }
                )
        return {
            "ok": True,
            "filing_version_id": filing_version_id,
            "issuer_type": issuer_type,
            "period": period,
            "candidate_rows": candidates,
            "row_not_found": row_not_found,
            "layouts": layouts,
            "source_fact_count": len(result.source_facts),
            "trace_count": len(result.traces),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "filing_version_id": filing_version_id,
            "issuer_type": issuer_type,
            "period": period,
            "candidate_rows": [],
            "row_not_found": [],
            "layouts": [],
            "source_fact_count": 0,
            "trace_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-800:],
        }


def _write_count_csv(path: Path, counter: Counter[str], key_name: str = "key") -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[key_name, "count"])
        writer.writeheader()
        for key, count in counter.most_common():
            writer.writerow({key_name: key, "count": count})


def _cross_counts(rows: list[dict[str, Any]], dim: str) -> dict[str, dict[str, int]]:
    out: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        family = str(row.get("n18_family") or "")
        out[family][str(row.get(dim) or "")] += 1
    return {fam: dict(c) for fam, c in out.items()}


def aggregate(results: list[dict[str, Any]], out_dir: Path, freeze: Any) -> dict[str, Any]:
    candidate_rows: list[dict[str, Any]] = []
    slot_rows: list[dict[str, Any]] = []
    layouts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    ok = 0
    for res in results:
        if res.get("ok"):
            ok += 1
        else:
            errors.append(
                {
                    "filing_version_id": res.get("filing_version_id"),
                    "error": res.get("error"),
                }
            )
        candidate_rows.extend(res.get("candidate_rows") or [])
        slot_rows.extend(res.get("candidate_rows") or [])
        slot_rows.extend(res.get("row_not_found") or [])
        for layout in res.get("layouts") or []:
            layout = {
                **layout,
                "filing_version_id": res.get("filing_version_id"),
                "issuer_type": res.get("issuer_type"),
                "period": res.get("period"),
            }
            layouts.append(layout)

    n18_counts = Counter(r["n18_family"] for r in candidate_rows)
    n18_slot_counts = Counter(r["n18_family"] for r in slot_rows)
    stage_counts = Counter(r["first_failure_stage"] for r in candidate_rows)
    entity_status = Counter(r.get("entity_status") or "" for r in candidate_rows)
    layout_counts = Counter(r["layout_family"] for r in layouts)
    banner_mismatch = sum(1 for r in layouts if r.get("banner_count_ne_monetary_count"))
    continuation_layouts = sum(1 for r in layouts if r.get("continuation_inherited_entity_schema"))

    # Dual-entity prevalence (layout level) — proxy for WRONG_ENTITY risk, not truth.
    dual_group_company = layout_counts.get("GROUP_AND_COMPANY_BOTH_EXPLICIT", 0)
    dual_group_bank = layout_counts.get("GROUP_AND_BANK_BOTH_EXPLICIT", 0)

    summary = {
        "id": "e02-universe-candidate-trace",
        "recovery_step": "E02",
        "status": "COMPLETE",
        "engine_code_sha": freeze.actual_code_sha,
        "investigation_base_sha": freeze.investigation_base_sha,
        "periods": list(PERIODS),
        "filings_attempted": len(results),
        "filings_ok": ok,
        "filings_error": len(errors),
        "target_metric_candidate_rows": len(candidate_rows),
        "target_metric_slot_rows_including_row_not_found": len(slot_rows),
        "statement_layout_rows": len(layouts),
        "n18_taxonomy_counts_candidates": dict(n18_counts),
        "n18_taxonomy_counts_slots": dict(n18_slot_counts),
        "first_failure_stage_counts": dict(stage_counts),
        "entity_status_counts": dict(entity_status),
        "entity_layout_pattern_counts": dict(layout_counts),
        "entity_banner_count_ne_monetary_column_count": banner_mismatch,
        "continuation_with_inherited_entity_schema": continuation_layouts,
        "n18_comparison": {
            "note": (
                "WRONG_ENTITY cannot be counted from universe without source truth. "
                "Use N18 confirmed WRONG_ENTITY=7 and universe dual-entity layouts + "
                "ENTITY_UNRESOLVED as prevalence evidence."
            ),
            "n18_confirmed": N18_COMPARE,
            "universe_ENTITY_UNRESOLVED_candidates": n18_counts.get("ENTITY_UNRESOLVED", 0),
            "universe_ENTITY_UNRESOLVED_slots": n18_slot_counts.get("ENTITY_UNRESOLVED", 0),
            "universe_NO_TARGET_CANDIDATE_slots": n18_slot_counts.get("NO_TARGET_CANDIDATE", 0),
            "universe_GROUP_AND_COMPANY_both_explicit_statements": dual_group_company,
            "universe_GROUP_AND_BANK_both_explicit_statements": dual_group_bank,
            "entity_unresolved_status_on_target_candidates": entity_status.get("UNRESOLVED", 0),
            "green_light_entity_fix": bool(
                n18_counts.get("ENTITY_UNRESOLVED", 0) >= 100
                or dual_group_company + dual_group_bank >= 50
                or entity_status.get("UNRESOLVED", 0) >= 200
            ),
        },
        "by_metric": _cross_counts(slot_rows, "metric_code"),
        "by_issuer_type": _cross_counts(slot_rows, "issuer_type"),
        "by_statement_type": _cross_counts(candidate_rows, "statement_type"),
        "errors_sample": errors[:40],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "e02_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _write_count_csv(out_dir / "e02_n18_taxonomy_candidates.csv", n18_counts, "n18_family")
    _write_count_csv(out_dir / "e02_n18_taxonomy_slots.csv", n18_slot_counts, "n18_family")
    _write_count_csv(out_dir / "e02_entity_layout_patterns.csv", layout_counts, "layout_family")
    _write_count_csv(out_dir / "e02_first_failure_stage.csv", stage_counts, "first_failure_stage")

    # Compact candidate sample for inspection (not full dump — can be huge)
    sample_path = out_dir / "e02_target_candidate_sample.jsonl"
    with sample_path.open("w", encoding="utf-8") as fh:
        for row in candidate_rows[:5000]:
            fh.write(json.dumps(row) + "\n")

    layout_path = out_dir / "e02_entity_layouts.jsonl"
    with layout_path.open("w", encoding="utf-8") as fh:
        for row in layouts:
            fh.write(json.dumps(row) + "\n")

    # Mirror summary at universe root for convenience
    (ROOT / "tests/v2/universe/e02_universe_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="0 = all discovered filings")
    parser.add_argument(
        "--periods",
        default=",".join(PERIODS),
        help="Comma-separated period ends",
    )
    args = parser.parse_args()

    root = ROOT
    periods = tuple(p.strip() for p in args.periods.split(",") if p.strip())
    jobs = discover_jobs(root, periods)
    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]

    freeze = collect_investigation_freeze(root)
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / "e02_progress.jsonl"

    print(f"E02 filings={len(jobs)} workers={args.workers} periods={periods}")
    results: list[dict[str, Any]] = []
    job_dicts = [asdict(j) for j in jobs]

    if args.workers <= 1:
        for i, job in enumerate(job_dicts, 1):
            res = process_one(job)
            results.append(res)
            with progress_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "i": i,
                            "ok": res["ok"],
                            "filing": res.get("filing_version_id"),
                            "error": res.get("error"),
                        }
                    )
                    + "\n"
                )
            if i % 25 == 0 or i == len(job_dicts):
                print(f"  {i}/{len(job_dicts)} ok={sum(1 for r in results if r['ok'])}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(process_one, job): job for job in job_dicts}
            done = 0
            for fut in as_completed(futures):
                res = fut.result()
                results.append(res)
                done += 1
                with progress_path.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "i": done,
                                "ok": res["ok"],
                                "filing": res.get("filing_version_id"),
                                "error": res.get("error"),
                            }
                        )
                        + "\n"
                    )
                if done % 25 == 0 or done == len(job_dicts):
                    print(f"  {done}/{len(job_dicts)} ok={sum(1 for r in results if r['ok'])}")

    summary = aggregate(results, out_dir, freeze)
    print(json.dumps(summary["n18_comparison"], indent=2))
    print(json.dumps(summary["n18_taxonomy_counts_slots"], indent=2))
    print(json.dumps(summary["entity_layout_pattern_counts"], indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
