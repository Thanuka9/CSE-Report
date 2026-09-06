"""Finalize Phase One universe outputs from the persisted lake after a gate crash."""

from __future__ import annotations

import json
import shutil
import uuid
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from cse_financial_etl.config import (
    code_version,
    config_hash,
    git_identity,
    load_app_config,
    load_coverage_baseline,
    load_issuers,
)
from cse_financial_etl.extraction.semantic_matcher import get_semantic_matcher
from cse_financial_etl.extraction.statement_extractor import ExtractedFact, QuarterPrice
from cse_financial_etl.reporting.dashboard import generate_run_dashboard
from cse_financial_etl.reporting.excel import generate_excel
from cse_financial_etl.sources.cse import DownloadedFiling, Filing
from cse_financial_etl.storage.run_archive import MANIFESTS_DIRNAME, run_output_dir
from cse_financial_etl.validation.golden import validate_golden
from cse_financial_etl.validation.production_gates import (
    evaluate_production_gates,
    run_status_from_gates,
)


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    return Decimal(text)


def _fact_from_row(row: dict[str, object]) -> ExtractedFact:
    period = date.fromisoformat(str(row["period_end"]))
    duration = row.get("duration_months")
    return ExtractedFact(
        issuer_name=str(row["issuer_name"]),
        symbol=str(row["symbol"]),
        period_end=period,
        metric_code=str(row["metric_code"]),
        metric_type=str(row.get("metric_type") or "MONETARY_ABSOLUTE"),
        raw_text=str(row.get("raw_text") or ""),
        raw_value=_dec(row.get("raw_value")),
        normalized_value=_dec(row.get("normalized_value")),
        currency=(str(row["currency"]) if row.get("currency") else None),
        scale_factor=int(row["scale_factor"]) if row.get("scale_factor") is not None else None,
        entity_scope=str(row.get("entity_scope") or "COMPANY"),
        source_page=int(row["source_page"]) if row.get("source_page") is not None else None,
        source_line=(str(row["source_line"]) if row.get("source_line") else None),
        unit_source_text=(str(row["unit_source_text"]) if row.get("unit_source_text") else None),
        confidence=str(row.get("certainty_band") or row.get("confidence") or "NONE"),
        status=str(row.get("status") or "NOT_FOUND_BY_PARSER"),
        comparison_role=str(row.get("comparison_role") or "CURRENT"),
        duration_months=int(duration) if duration is not None else None,
        validation_status=str(row.get("validation_status") or "NOT_VALIDATED"),
        review_status=str(row.get("review_status") or "REVIEW"),
        extraction_method=(str(row["extraction_method"]) if row.get("extraction_method") else None),
        overall_certainty=float(row["overall_certainty"])
        if row.get("overall_certainty") is not None
        else 0.0,
        certainty_band=str(row.get("certainty_band") or "NONE"),
        source_bbox=(str(row["source_bbox"]) if row.get("source_bbox") else None),
        evidence_json=None,
    )


def _price_from_row(row: dict[str, object]) -> QuarterPrice:
    return QuarterPrice(
        issuer_name=str(row["issuer_name"]),
        symbol=str(row["symbol"]),
        period_end=date.fromisoformat(str(row["period_end"])),
        value=_dec(row.get("value")),
        source_page=int(row["source_page"]) if row.get("source_page") is not None else None,
        source_line=(str(row["source_line"]) if row.get("source_line") else None),
        source_method=str(row.get("source_method") or "FILING"),
        confidence=str(row.get("certainty_band") or "NONE"),
        status=str(row.get("status") or "NOT_FOUND"),
        confidence_score=float(row["confidence_score"])
        if row.get("confidence_score") is not None
        else 0.0,
        certainty_band=str(row.get("certainty_band") or "NONE"),
        source_bbox=(str(row["source_bbox"]) if row.get("source_bbox") else None),
        validation_status=str(row.get("validation_status") or "NOT_VALIDATED"),
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    outputs = root / "outputs"
    as_of = date(2026, 9, 5)
    periods = [date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]
    run_id = str(uuid.uuid4())

    facts_df = pl.read_parquet(data / "gold" / "current_financial_facts.parquet")
    prices_df = pl.read_parquet(data / "gold" / "current_market_prices.parquet")
    facts = [_fact_from_row(row) for row in facts_df.to_dicts()]
    prices = [_price_from_row(row) for row in prices_df.to_dicts()]

    # Group facts by issuer/period for gate iteration shape.
    grouped: dict[tuple[str, str, str], list[ExtractedFact]] = {}
    for fact in facts:
        key = (fact.issuer_name, fact.symbol, fact.period_end.isoformat())
        grouped.setdefault(key, []).append(fact)

    extracted_results: list[tuple[DownloadedFiling, list[ExtractedFact]]] = []
    for (issuer, symbol, period_text), group in grouped.items():
        period = date.fromisoformat(period_text)
        filing = Filing(
            issuer_name=issuer,
            symbol=symbol,
            filing_id=0,
            period_end=period,
            title=f"{issuer} {period_text}",
            source_path="",
            source_url="",
            uploaded_at=None,
            authorized_at=None,
        )
        downloaded = DownloadedFiling(
            filing=filing,
            local_path=root / "data" / "raw" / "filings" / "_finalize_placeholder.pdf",
            sha256=f"finalize-{symbol}-{period_text}",
            size_bytes=0,
        )
        extracted_results.append((downloaded, group))

    golden = validate_golden(root, as_of)
    issuers = load_issuers(root)
    scope_by_issuer = {
        str(name): str(profile.standalone_scope_label) for name, profile in issuers.items()
    }
    assert isinstance(scope_by_issuer, dict)

    gate_hits = evaluate_production_gates(
        extracted_results,
        prices,
        golden_validation=golden,
        required_scope=scope_by_issuer,
        coverage_baseline=load_coverage_baseline(root),
    )
    status_counts = Counter(fact.status for fact in facts)
    price_status_counts = Counter(price.status for price in prices)
    run_status = run_status_from_gates(gate_hits, has_errors=False, has_review=True)

    facts_csv = outputs / f"normalized_facts_{as_of.isoformat()}.csv"
    review_csv = outputs / f"review_queue_{as_of.isoformat()}.csv"
    prices_csv = outputs / f"quarter_end_prices_{as_of.isoformat()}.csv"
    run_dir = run_output_dir(root, as_of.isoformat(), run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    for path in (facts_csv, review_csv, prices_csv):
        if path.exists():
            shutil.copy2(path, run_dir / path.name)

    app = load_app_config(root)
    statistics: dict[str, object] = {
        "run_id": run_id,
        "as_of_date": as_of.isoformat(),
        "target_periods": [period.isoformat() for period in periods],
        "security_count": len({fact.symbol for fact in facts}),
        "issuer_count": len({fact.issuer_name for fact in facts}),
        "extracted_filing_count": len(extracted_results),
        "fact_status_counts": dict(status_counts),
        "price_status_counts": dict(price_status_counts),
        "pipeline_error_count": 0,
        "golden_validation_sample_size": golden["sample_size"],
        "golden_validation_accuracy": golden["accuracy"],
        "run_status": run_status,
        "production_gates": {
            "status": run_status,
            "hit_count": len(gate_hits),
            "hits": [
                {
                    "code": hit.code,
                    "issuer_name": hit.issuer_name,
                    "symbol": hit.symbol,
                    "period_end": hit.period_end.isoformat() if hit.period_end else None,
                    "metric_code": hit.metric_code,
                    "detail": hit.detail,
                }
                for hit in gate_hits
            ],
        },
        "facts_csv": str(facts_csv),
        "review_csv": str(review_csv),
        "prices_csv": str(prices_csv),
        "run_dir": str(run_dir),
        "storage": "Parquet + JSONL",
        "code_version": code_version(),
        "config_hash": config_hash(root),
        **git_identity(root).as_dict(),
        "finalize_from_lake": True,
        "ocr_enabled": app.ocr_enabled,
        "use_transformer": False,
        "semantic_model": get_semantic_matcher().model_name,
        "current_facts_parquet": str(data / "gold" / "current_financial_facts.parquet"),
        "current_prices_parquet": str(data / "gold" / "current_market_prices.parquet"),
    }

    workbook_path = generate_excel(root, as_of, periods, run_id)
    statistics["workbook"] = str(workbook_path)
    dashboard_path = generate_run_dashboard(root, as_of, periods, run_id, run_dir, statistics)
    statistics["dashboard"] = str(dashboard_path)

    manifests_dir = outputs / MANIFESTS_DIRNAME
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"run_manifest_{as_of.isoformat()}.json"
    dated_manifest = manifests_dir / f"{as_of.isoformat()}_{run_id}.json"
    statistics["manifest"] = str(manifest_path)
    statistics["run_manifest"] = str(dated_manifest)
    payload = json.dumps(statistics, indent=2)
    manifest_path.write_text(payload, encoding="utf-8")
    dated_manifest.write_text(payload, encoding="utf-8")
    shutil.copy2(manifest_path, run_dir / "run_manifest.json")
    golden_path = outputs / f"golden_validation_{as_of.isoformat()}.json"
    if golden_path.exists():
        shutil.copy2(golden_path, run_dir / "golden_validation.json")
    shutil.copy2(workbook_path, run_dir / "CSE_Financial_Snapshot.xlsx")

    summary = {
        "run_status": run_status,
        "gate_hit_count": len(gate_hits),
        "gate_codes": sorted({hit.code for hit in gate_hits}),
        "fact_status_counts": dict(status_counts),
        "golden_accuracy": golden["accuracy"],
        "golden_sample_size": golden["sample_size"],
        "manifest": str(manifest_path),
        "workbook": str(workbook_path),
        "dashboard": str(dashboard_path),
        "run_dir": str(run_dir),
    }
    (outputs / "PHASE_ONE_UNIVERSE_SUMMARY.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
