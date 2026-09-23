"""Locked-set V2 A/B baseline, V1 comparator, lineage, and ledger (T05-T09)."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.diagnostics.candidate_trace import write_candidate_trace
from cse_financial_etl.v2.diagnostics.canonical_outputs import (
    fact_rows,
    stamp_identity,
    write_json,
    write_jsonl,
    write_parquet,
    write_run_level_canonical_outputs,
)
from cse_financial_etl.v2.diagnostics.discovery import discover_exact_aliases
from cse_financial_etl.v2.diagnostics.investigation_freeze import (
    InvestigationFreeze,
    collect_investigation_freeze,
    freeze_run_identity,
)
from cse_financial_etl.v2.diagnostics.issue_ledger import build_issue_ledger
from cse_financial_etl.v2.diagnostics.lineage import audit_derived_fact, audit_source_fact
from cse_financial_etl.v2.diagnostics.page_routing import mixed_native_ocr_document
from cse_financial_etl.v2.diagnostics.real_filings import RealFilingCase, load_real_filing_cases
from cse_financial_etl.v2.diagnostics.regime_audit import audit_issuer_regime
from cse_financial_etl.v2.diagnostics.replay import (
    documents_are_deterministic,
    facts_are_deterministic,
    pipeline_results_are_deterministic,
)
from cse_financial_etl.v2.diagnostics.serialization import (
    derived_fact_to_mapping,
    source_fact_to_mapping,
)
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline


@dataclass(frozen=True)
class FilingBaseline:
    case_id: str
    pdf_sha256: str
    deterministic: bool
    source_fact_count: int
    derived_fact_count: int
    lineage: dict[str, int]
    derived_audit: dict[str, int]
    mixed_native_ocr: bool
    alias_hits: int
    v1_error: str | None
    disagreement: dict[str, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _v1_rows(case: RealFilingCase) -> tuple[list[dict[str, object]], str | None]:
    try:
        from cse_financial_etl.extraction.statement_extractor import extract_filing

        facts = extract_filing(
            case.pdf_path,
            case.issuer_name,
            case.issuer_id,
            case.period_end,
            ocr_enabled=False,
        )
        return [fact.as_json() for fact in facts], None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def run_filing_baseline(
    case: RealFilingCase,
    *,
    out_dir: Path | None = None,
    include_v1: bool = True,
    run_id: str | None = None,
    code_sha: str | None = None,
    identity: dict[str, str] | None = None,
) -> FilingBaseline:
    pdf_sha = _sha256(case.pdf_path)
    first_document = read_document(case.pdf_path, filing_version_id=case.case_id)
    first = run_filing_pipeline(
        first_document,
        issuer_id=case.issuer_id,
        expected_entity_scope=case.entity_scope,
        target_period_end=case.period_end,
        issuer_name=case.issuer_name,
        issuer_type=case.issuer_type,
        run_id=run_id,
        code_sha=code_sha,
    )
    second_document = read_document(case.pdf_path, filing_version_id=case.case_id)
    second = run_filing_pipeline(
        second_document,
        issuer_id=case.issuer_id,
        expected_entity_scope=case.entity_scope,
        target_period_end=case.period_end,
        issuer_name=case.issuer_name,
        issuer_type=case.issuer_type,
        run_id=run_id,
        code_sha=code_sha,
    )
    source = first.source_facts
    derived = first.derived_facts
    left = tuple(source_fact_to_mapping(fact) for fact in source)
    right = tuple(source_fact_to_mapping(fact) for fact in second.source_facts)
    derived_left = tuple(derived_fact_to_mapping(item) for item in derived)
    derived_right = tuple(derived_fact_to_mapping(item) for item in second.derived_facts)
    deterministic = (
        documents_are_deterministic(first_document, second_document)
        and pipeline_results_are_deterministic(first, second)
        and facts_are_deterministic(left, right)
        and derived_left == derived_right
    )
    traces = first.traces
    lineage = Counter(
        audit_source_fact(fact, document=first_document, expected_pdf_sha=pdf_sha).value
        for fact in source
    )
    derived_audit = Counter(audit_derived_fact(fact, source).value for fact in derived)
    v1_rows: list[dict[str, object]] = []
    v1_error = None
    if include_v1:
        v1_rows, v1_error = _v1_rows(case)
    ledger = build_issue_ledger(
        pdf_sha=pdf_sha,
        issuer=case.issuer_id,
        sector=case.issuer_type,
        v1_rows=v1_rows,
        v2_facts=source,
    )
    disagreement = Counter(row.disagreement_class.value for row in ledger)
    alias_hits = discover_exact_aliases(
        first_document,
        issuer_id=case.issuer_id,
        issuer_name=case.issuer_name,
        issuer_type=case.issuer_type,
    )
    if out_dir is not None:
        case_dir = out_dir / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        stamp = identity or {}
        write_candidate_trace(case_dir / "candidate_trace.parquet", traces, stamp)
        source_rows = fact_rows(source, stamp)
        derived_rows = fact_rows(derived, stamp)
        selected_rows = fact_rows(first.production_selected_source, stamp, selected=True)
        selected_rows.extend(
            fact_rows(first.production_selected_derived, stamp, selected=True)
        )
        ledger_rows = stamp_identity(
            [row.model_dump(mode="json") for row in ledger], stamp
        )
        write_json(case_dir / "source_facts.json", source_rows)
        write_jsonl(case_dir / "source_facts.jsonl", source_rows)
        write_parquet(case_dir / "source_facts.parquet", source_rows)
        write_json(case_dir / "derived_facts.json", derived_rows)
        write_jsonl(case_dir / "derived_facts.jsonl", derived_rows)
        write_parquet(case_dir / "derived_facts.parquet", derived_rows)
        write_parquet(case_dir / "production_selection.parquet", selected_rows)
        write_json(case_dir / "ledger.json", ledger_rows)
        write_parquet(case_dir / "issue_ledger.parquet", ledger_rows)
        write_json(case_dir / "alias_hits.json", stamp_identity(list(alias_hits), stamp))
    return FilingBaseline(
        case_id=case.case_id,
        pdf_sha256=pdf_sha,
        deterministic=deterministic,
        source_fact_count=len(source),
        derived_fact_count=len(derived),
        lineage=dict(lineage),
        derived_audit=dict(derived_audit),
        mixed_native_ocr=mixed_native_ocr_document(first_document),
        alias_hits=len(alias_hits),
        v1_error=v1_error,
        disagreement=dict(disagreement),
    )


def run_locked_baseline(
    *,
    root: Path,
    out_dir: Path,
    include_v1: bool = True,
    limit: int = 40,
    freeze: InvestigationFreeze | None = None,
) -> dict[str, Any]:
    freeze = freeze or collect_investigation_freeze(root)
    run_id = f"locked-baseline-{freeze.actual_code_sha}"
    identity = freeze_run_identity(freeze, run_id=run_id)
    summary_identity = {
        **identity,
        "code_sha": freeze.code_sha,
        "uv_lock_sha256": freeze.uv_lock_sha256,
        "pymupdf_version": freeze.pymupdf_version,
        "tesseract_version": freeze.tesseract_version,
        "pytesseract_version": freeze.pytesseract_version,
        "extraction_engine": freeze.extraction_engine,
    }
    cases = load_real_filing_cases(limit=limit, root=root, locked=True)
    results = [
        run_filing_baseline(
            case,
            out_dir=out_dir,
            include_v1=include_v1,
            run_id=run_id,
            code_sha=freeze.actual_code_sha,
            identity=identity,
        )
        for case in cases
    ]
    regimes = [
        audit_issuer_regime(
            issuer_id=case.issuer_id,
            issuer_name=case.issuer_name,
            issuer_type=case.issuer_type,
        )
        for case in cases
    ]
    summary = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        **summary_identity,
        "working_tree_dirty": freeze.working_tree_dirty,
        "case_count": len(results),
        "all_deterministic": all(item.deterministic for item in results),
        "source_facts": sum(item.source_fact_count for item in results),
        "derived_facts": sum(item.derived_fact_count for item in results),
        "mixed_native_ocr_filings": sum(1 for item in results if item.mixed_native_ocr),
        "v1_errors": sum(1 for item in results if item.v1_error),
        "lineage": _merge_counts(item.lineage for item in results),
        "derived_audit": _merge_counts(item.derived_audit for item in results),
        "disagreement": _merge_counts(item.disagreement for item in results),
        "filings": [asdict(item) for item in results],
        "regime_audit": regimes,
        "include_v1": include_v1,
        "note": (
            "V1 rows are comparator-only. Disagreements are not source truth. "
            "source_truth_status remains NOT_ADJUDICATED."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "run_manifest.json", summary)
    _write_csv(out_dir / "issue_summary.csv", results, identity)
    write_json(out_dir / "regime_audit.json", {"identity": identity, "filings": regimes})
    write_run_level_canonical_outputs(out_dir)
    return summary


def _merge_counts(items: Iterable[dict[str, int]]) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for item in items:
        merged.update(item)
    return dict(merged)


def _write_csv(
    path: Path,
    results: list[FilingBaseline],
    identity: dict[str, str] | None = None,
) -> None:
    stamp = identity or {}
    fieldnames = [
        *stamp.keys(),
        "case_id",
        "deterministic",
        "source_fact_count",
        "derived_fact_count",
        "mixed_native_ocr",
        "alias_hits",
        "v1_error",
        *sorted({key for item in results for key in item.disagreement}),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in results:
            row: dict[str, object] = {
                **stamp,
                "case_id": item.case_id,
                "deterministic": item.deterministic,
                "source_fact_count": item.source_fact_count,
                "derived_fact_count": item.derived_fact_count,
                "mixed_native_ocr": item.mixed_native_ocr,
                "alias_hits": item.alias_hits,
                "v1_error": item.v1_error or "",
            }
            row.update(item.disagreement)
            writer.writerow(row)


def build_locked_source_manifest(root: Path) -> list[dict[str, object]]:
    cases = load_real_filing_cases(limit=40, root=root, locked=True)
    rows: list[dict[str, object]] = []
    for case in cases:
        path = case.pdf_path
        try:
            local_file = path.relative_to(root).as_posix()
        except ValueError:
            local_file = str(path)
        rows.append(
            {
                "filing_version_id": case.case_id,
                "issuer_id": case.issuer_id,
                "symbol": case.issuer_id,
                "period": case.period_end.isoformat(),
                "local_file": local_file,
                "pdf_sha256": _sha256(path),
                "file_size": path.stat().st_size,
                "issuer_type": case.issuer_type,
            }
        )
    return rows
