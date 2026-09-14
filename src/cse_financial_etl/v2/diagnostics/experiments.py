"""Locked-set diagnostic experiments (T10/T11/T14/T16). Do not publish from these."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import StatementType
from cse_financial_etl.v2.diagnostics.bakeoffs import pipeline_bakeoff
from cse_financial_etl.v2.diagnostics.discovery import discover_exact_aliases
from cse_financial_etl.v2.diagnostics.gate_ablation import g02_ablation
from cse_financial_etl.v2.diagnostics.page_routing import (
    empty_native_page_numbers,
    mixed_native_ocr_document,
)
from cse_financial_etl.v2.diagnostics.real_filings import RealFilingCase, load_real_filing_cases
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.statements.detector import detect_statement_regions

HIGH_RISK_CLASSES = (
    "VALUE_DISAGREEMENT",
    "REFERENCE_ONLY_DISAGREEMENT",
)


def page_empty_census(
    case: RealFilingCase, document: CanonicalDocument | None = None
) -> dict[str, Any]:
    document = document or read_native_pdf(case.pdf_path, filing_version_id=case.case_id)
    empty = empty_native_page_numbers(document)
    return {
        "case_id": case.case_id,
        "page_count": len(document.pages),
        "empty_native_pages": list(empty),
        "empty_native_page_count": len(empty),
        "mixed_native_ocr": mixed_native_ocr_document(document),
        "page_routing": "page",
        "production_router": "document",
        "ocr_status": "OCR_REQUIRED_NOT_AVAILABLE" if empty else "",
        "note": "P1 census only. Empty pages were not OCR'd. Production stays P0.",
    }


def discovery_census(
    case: RealFilingCase, document: CanonicalDocument | None = None
) -> dict[str, Any]:
    document = document or read_native_pdf(case.pdf_path, filing_version_id=case.case_id)
    regions = detect_statement_regions(document)
    statement_pages: set[int] = set()
    for region in regions:
        pages = range(region.page_start, region.page_end + 1)
        if region.statement_type is not StatementType.OTHER_FINANCIAL_STATEMENT:
            statement_pages.update(pages)
    hits = discover_exact_aliases(
        document,
        issuer_id=case.issuer_id,
        issuer_name=case.issuer_name,
        issuer_type=case.issuer_type,
    )
    on_statement = [hit for hit in hits if int(hit["page"]) in statement_pages]
    on_other = [hit for hit in hits if int(hit["page"]) not in statement_pages]
    metrics = Counter(str(hit["metric_code"]) for hit in hits)
    return {
        "case_id": case.case_id,
        "alias_hits": len(hits),
        "hits_on_statement_pages": len(on_statement),
        "hits_on_other_pages": len(on_other),
        "metrics": dict(metrics),
        "other_page_sample": [
            {
                "page": hit["page"],
                "metric_code": hit["metric_code"],
                "matched_alias": hit["matched_alias"],
            }
            for hit in on_other[:12]
        ],
        "note": "Discovery does not publish. Hits are not source truth.",
    }


def g02_census(
    case: RealFilingCase, document: CanonicalDocument | None = None
) -> dict[str, Any]:
    document = document or read_native_pdf(case.pdf_path, filing_version_id=case.case_id)
    result = g02_ablation(
        document,
        issuer_id=case.issuer_id,
        expected_entity_scope=case.entity_scope,
    )
    return {"case_id": case.case_id, **result}


def build_t10_review_queue(
    ledger_rows: Sequence[dict[str, object]],
    *,
    split: dict[str, list[str]],
    limit: int = 40,
) -> dict[str, object]:
    """Blind review pointers. Comparator values are omitted and are not gold."""

    dev = set(split.get("dev") or ())
    holdout = set(split.get("holdout") or ())
    ranked: list[tuple[int, int, str, str, dict[str, object]]] = []
    for row in ledger_rows:
        klass = str(row.get("disagreement_class") or "")
        if klass not in HIGH_RISK_CLASSES:
            continue
        issuer = str(row.get("issuer") or "")
        if issuer in dev:
            split_name = "DEV"
            split_rank = 0
        elif issuer in holdout:
            split_name = "HOLDOUT"
            split_rank = 1
        else:
            continue
        class_rank = 0 if klass == "VALUE_DISAGREEMENT" else 1
        ranked.append(
            (
                split_rank,
                class_rank,
                issuer,
                str(row.get("metric") or ""),
                {
                    "issue_id": row.get("issue_id"),
                    "pdf_sha": row.get("pdf_sha"),
                    "issuer": issuer,
                    "metric": row.get("metric"),
                    "page": row.get("page"),
                    "disagreement_class": klass,
                    "split": split_name,
                    "adjudication_status": "NOT_STARTED",
                    "source_truth_status": "NOT_ADJUDICATED",
                    "notes": (
                        "Blind PDF review. Do not copy V1 or V2 values. "
                        "Record source presence from the filing only."
                    ),
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    items = [item[4] for item in ranked[:limit]]
    return {
        "note": (
            "T10 blind review queue. Not source truth and not publication gold. "
            "items.jsonl stays empty until a human records source presence."
        ),
        "limit": limit,
        "item_count": len(items),
        "items": items,
    }


def load_existing_ledgers(out_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not out_dir.is_dir():
        return rows
    for path in sorted(out_dir.glob("*/ledger.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
    return rows


def run_locked_experiments(
    *,
    root: Path,
    out_dir: Path,
    ledger_dir: Path,
    split_path: Path,
    limit: int = 40,
) -> dict[str, Any]:
    cases = load_real_filing_cases(limit=limit, root=root, locked=True)
    g02_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    discovery_rows: list[dict[str, Any]] = []
    bakeoff_rows: list[dict[str, Any]] = []
    for case in cases:
        document = read_native_pdf(case.pdf_path, filing_version_id=case.case_id)
        g02_rows.append(g02_census(case, document))
        page_rows.append(page_empty_census(case, document))
        discovery_rows.append(discovery_census(case, document))
        bakeoff_rows.append(pipeline_bakeoff(case, document))
    split_payload = json.loads(split_path.read_text(encoding="utf-8"))
    t10 = build_t10_review_queue(load_existing_ledgers(ledger_dir), split=split_payload)
    lineage_totals: Counter[str] = Counter()
    h0_totals: Counter[str] = Counter()
    g03_totals: Counter[str] = Counter()
    g05_totals: Counter[str] = Counter()
    g08_totals: Counter[str] = Counter()
    u0_totals: Counter[str] = Counter()
    g01_unresolved = 0
    g01_document_cue = 0
    for row in bakeoff_rows:
        lineage_totals.update(row["lineage"])
        h0_totals.update(row["h0"])
        g03_totals.update(row["g03"])
        g05_totals.update(row["g05"])
        g08_totals.update(row["g08"])
        u0_totals.update(row["u0"])
        g01_unresolved += int(row["g01"]["unresolved_entity_columns"])
        g01_document_cue += int(row["g01"]["unresolved_with_document_entity_cue"])
    g02_totals = {
        "cascade_source_facts": sum(row["cascade_source_facts"] for row in g02_rows),
        "per_column_source_facts": sum(row["per_column_source_facts"] for row in g02_rows),
        "facts_suppressed_by_cascade": sum(row["facts_suppressed_by_cascade"] for row in g02_rows),
    }
    summary = {
        "case_count": len(cases),
        "g02": g02_totals,
        "g02_decision": "UNTESTED",
        "page_empty": {
            "mixed_native_ocr_filings": sum(1 for row in page_rows if row["mixed_native_ocr"]),
            "empty_native_pages": sum(row["empty_native_page_count"] for row in page_rows),
            "production_router": "document",
            "p1_ocr_applied": False,
        },
        "discovery": {
            "alias_hits": sum(row["alias_hits"] for row in discovery_rows),
            "hits_on_statement_pages": sum(row["hits_on_statement_pages"] for row in discovery_rows),
            "hits_on_other_pages": sum(row["hits_on_other_pages"] for row in discovery_rows),
        },
        "lineage": dict(lineage_totals),
        "h0": dict(h0_totals),
        "u0": dict(u0_totals),
        "g01": {
            "unresolved_entity_columns": g01_unresolved,
            "unresolved_with_document_entity_cue": g01_document_cue,
            "decision": "UNTESTED",
        },
        "g03": {**dict(g03_totals), "decision": "UNTESTED"},
        "g05": {**dict(g05_totals), "decision": "UNTESTED"},
        "g08": {**dict(g08_totals), "decision": "UNTESTED"},
        "prototypes": {"h2": False, "u2": False, "p2": False},
        "t10_queue_item_count": t10["item_count"],
        "note": (
            "Diagnostic only. Gates remain UNTESTED. P1 is not production. "
            "H2/U2/P2 are not built. Discovery does not publish. T10 queue is not gold."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "g02_ablation.json").write_text(
        json.dumps({"totals": g02_totals, "filings": g02_rows}, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "page_empty_census.json").write_text(
        json.dumps(page_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "discovery_census.json").write_text(
        json.dumps(discovery_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "lineage_after_cell_ref.json").write_text(
        json.dumps(
            {
                "totals": dict(lineage_totals),
                "filings": [
                    {
                        "case_id": row["case_id"],
                        "source_fact_count": row["source_fact_count"],
                        "lineage": row["lineage"],
                    }
                    for row in bakeoff_rows
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "bakeoffs.json").write_text(
        json.dumps(bakeoff_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    _write_section27_tables(out_dir, summary, g02_rows, page_rows, discovery_rows)
    (out_dir / "extraction_report.md").write_text(_extraction_report(summary), encoding="utf-8")
    return {"summary": summary, "t10": t10, "g02": g02_rows, "page": page_rows}


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_section27_tables(
    out_dir: Path,
    summary: dict[str, Any],
    g02_rows: list[dict[str, Any]],
    page_rows: list[dict[str, Any]],
    discovery_rows: list[dict[str, Any]],
) -> None:
    _write_csv(
        out_dir / "gate_ablation_results.csv",
        [
            {
                "gate": "G01",
                "decision": "UNTESTED",
                "metric": "unresolved_entity_columns",
                "value": summary["g01"]["unresolved_entity_columns"],
            },
            {
                "gate": "G02",
                "decision": "UNTESTED",
                "metric": "facts_suppressed_by_cascade",
                "value": summary["g02"]["facts_suppressed_by_cascade"],
            },
            {
                "gate": "G03",
                "decision": "UNTESTED",
                "metric": "flow_duration_missing",
                "value": summary["g03"].get("flow_duration_missing", 0),
            },
            {
                "gate": "G05",
                "decision": "UNTESTED",
                "metric": "explicit_continuation_regions",
                "value": summary["g05"].get("explicit_continuation_regions", 0),
            },
            {
                "gate": "G08",
                "decision": "UNTESTED",
                "metric": "duplicate_identity_groups",
                "value": summary["g08"].get("duplicate_identity_groups", 0),
            },
        ],
    )
    _write_csv(out_dir / "g02_ablation.csv", g02_rows)
    _write_csv(
        out_dir / "header_engine_bakeoff.csv",
        [{"engine": "H0", "prototype_h2": False, **summary["h0"]}],
    )
    _write_csv(
        out_dir / "unit_resolver_bakeoff.csv",
        [{"resolver": "U0", "prototype_u2": False, **summary["u0"]}],
    )
    _write_csv(
        out_dir / "continuation_bakeoff.csv",
        [{"variant": "explicit_marker_only", **{k: v for k, v in summary["g05"].items() if k != "decision"}}],
    )
    _write_csv(out_dir / "page_discovery_results.csv", discovery_rows)
    _write_csv(
        out_dir / "page_router_census.csv",
        [
            {
                "production": "P0",
                "p1_ocr_applied": summary["page_empty"]["p1_ocr_applied"],
                "mixed_native_ocr_filings": summary["page_empty"]["mixed_native_ocr_filings"],
                "empty_native_pages": summary["page_empty"]["empty_native_pages"],
            }
        ],
    )


def _extraction_report(summary: dict[str, Any]) -> str:
    lineage = summary.get("lineage") or {}
    return (
        "# V2 Extraction Investigation Report\n\n"
        "Diagnostic report for the locked 33. Not certification. Not source gold.\n"
        "Production engine remains V1. Coverage floor remains 8924.\n\n"
        f"- Cases: {summary.get('case_count')}\n"
        f"- Lineage complete: {lineage.get('LINEAGE_COMPLETE', 0)}\n"
        f"- Context incomplete: {lineage.get('CONTEXT_EVIDENCE_INCOMPLETE', 0)}\n"
        f"- SOURCE_VALUE_NOT_REPRODUCIBLE: {lineage.get('SOURCE_VALUE_NOT_REPRODUCIBLE', 0)}\n"
        f"- G02 cascade suppressed: {summary['g02']['facts_suppressed_by_cascade']}\n"
        f"- G03 FLOW duration missing: {summary['g03'].get('flow_duration_missing', 0)}\n"
        f"- P1 OCR applied: {summary['page_empty']['p1_ocr_applied']}\n"
        f"- T10 queue items: {summary.get('t10_queue_item_count')}\n"
        f"- Prototypes built: H2={summary['prototypes']['h2']} "
        f"U2={summary['prototypes']['u2']} P2={summary['prototypes']['p2']}\n\n"
        "Gates remain UNTESTED until T10 human source adjudication.\n"
        "T25–T29 (holdout, frozen universe, certification, cutover) are blocked.\n"
    )
