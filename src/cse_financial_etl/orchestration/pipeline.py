from __future__ import annotations

import json
import os
import shutil
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.config import (
    code_version,
    config_hash,
    git_identity,
    load_app_config,
    load_coverage_baseline,
    load_issuers,
    load_metric_catalog,
    load_unit_pattern_config,
)
from cse_financial_etl.domain.periods import supporting_periods
from cse_financial_etl.extraction.semantic_matcher import apply_metric_catalog, get_semantic_matcher
from cse_financial_etl.extraction.statement_extractor import (
    ExtractedFact,
    QuarterPrice,
    extract_filing,
    extract_quarter_prices,
    facts_by_code,
)
from cse_financial_etl.extraction.unit_detector import configure_unit_patterns
from cse_financial_etl.reporting.dashboard import generate_run_dashboard
from cse_financial_etl.reporting.excel import generate_excel
from cse_financial_etl.sources.cse import (
    DownloadedFiling,
    Filing,
    Security,
    choose_filing,
    configure_http,
    download_filing,
    fetch_all_financial_metadata,
    fetch_market_capitalization,
    issuer_representatives,
    load_market_capitalization_cache,
    serialize_security,
)
from cse_financial_etl.sources.historical_prices import resolve_quarter_end_price
from cse_financial_etl.storage.repository import Repository
from cse_financial_etl.storage.run_archive import (
    MANIFESTS_DIRNAME,
    archive_pipeline_artifacts,
    preserve_current_run_folder,
    run_output_dir,
    utc_stamp,
)
from cse_financial_etl.transformation.ratios import derive_ratio_facts
from cse_financial_etl.validation.cross_filing import flag_cross_filing_mismatches
from cse_financial_etl.validation.equation_engine import ValidationOutcome
from cse_financial_etl.validation.golden import validate_golden
from cse_financial_etl.validation.production_gates import (
    evaluate_production_gates,
    run_status_from_gates,
)
from cse_financial_etl.validation.registry import build_default_equation_engine
from cse_financial_etl.validation.retry_controller import RetryController

DEFAULT_PERIODS = (date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30))


def derive_cumulative_quarters(
    extracted_results: list[tuple[DownloadedFiling, list[ExtractedFact]]],
) -> list[tuple[DownloadedFiling, list[ExtractedFact]]]:
    """Compatibility no-op: cumulative/YTD values are never published as quarters."""

    return extracted_results


def _previous_fact_status_counts(preserved: Path | None) -> dict[str, int] | None:
    if preserved is None:
        return None
    manifest = preserved / "run_manifest.json"
    if not manifest.exists():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    counts = payload.get("fact_status_counts")
    if not isinstance(counts, dict):
        return None
    return {str(key): int(value) for key, value in counts.items() if str(value).isdigit() or isinstance(value, int)}


class Pipeline:
    def __init__(self, project_root: Path, progress: Callable[[str], None] = print) -> None:
        self.root = project_root
        self.data = project_root / "data"
        self.outputs = project_root / "outputs"
        self.progress = progress
        self.repository = Repository(self.data)
        self.app_config = load_app_config(project_root)
        self.issuers = load_issuers(project_root)
        configure_http(
            timeout_seconds=self.app_config.http_timeout_seconds,
            max_retries=self.app_config.http_max_retries,
        )
        os.environ["CSE_ETL_USE_TRANSFORMER"] = "1" if self.app_config.use_transformer else "0"
        os.environ["CSE_ETL_SEMANTIC_MODEL"] = self.app_config.semantic_model
        apply_metric_catalog(load_metric_catalog(project_root))
        configure_unit_patterns(load_unit_pattern_config(project_root))
        get_semantic_matcher.cache_clear()

    def close(self) -> None:
        self.repository.close()

    def run(
        self,
        as_of_date: date,
        periods: Iterable[date] = DEFAULT_PERIODS,
        *,
        api_workers: int = 24,
        download_workers: int = 20,
        extraction_workers: int = 8,
        issuer_limit: int | None = None,
        offline: bool = False,
        skip_excel: bool = False,
    ) -> dict[str, object]:
        target_periods = tuple(periods)
        extraction_periods = supporting_periods(target_periods)
        run_id = str(uuid.uuid4())
        self.repository.start_run(run_id, as_of_date)
        errors: list[dict[str, str]] = []
        archive_stamp = utc_stamp()
        archived = archive_pipeline_artifacts(self.root, as_of_date.isoformat(), archive_stamp)
        preserved = preserve_current_run_folder(self.root, as_of_date.isoformat())
        if archived:
            self.progress(f"      archived {len(archived)} prior-run files under history/archive")
        if preserved is not None:
            self.progress(f"      preserved prior run folder {preserved.name}")

        self.progress("[1/7] Fetching live CSE market-capitalization universe")
        market_path = self.data / "raw" / "api" / f"market_cap_{as_of_date.isoformat()}.json"
        if offline:
            if not market_path.exists():
                raise FileNotFoundError(
                    f"Offline market snapshot not found: {market_path}. Run once online first."
                )
            securities = load_market_capitalization_cache(market_path)
            self.progress(f"      reused cached market snapshot {market_path.name}")
        else:
            try:
                securities = fetch_market_capitalization()
            except RuntimeError:
                if not market_path.exists():
                    raise
                securities = load_market_capitalization_cache(market_path)
                self.progress(f"      live request failed; reused {market_path.name}")
        # Persist the complete canonical universe before applying a smoke-test limit.
        # Otherwise a four-issuer test can silently shrink the next offline full run.
        market_path.parent.mkdir(parents=True, exist_ok=True)
        market_path.write_text(
            json.dumps([serialize_security(security) for security in securities], indent=2),
            encoding="utf-8",
        )
        if issuer_limit is not None:
            allowed = set(list(issuer_representatives(securities))[:issuer_limit])
            securities = [security for security in securities if security.company_name in allowed]
        self.repository.save_market(as_of_date, securities)
        self._validate_market_snapshot(run_id, securities)

        representatives = issuer_representatives(securities)
        self.progress(
            f"[2/7] Fetching filing metadata for {len(representatives)} issuers "
            f"({len(securities)} securities)"
        )
        metadata = fetch_all_financial_metadata(
            securities,
            self.data / "raw" / "api" / "financials",
            workers=api_workers,
            offline=offline,
        )

        selected: list[Filing] = []
        for issuer_name, representative in representatives.items():
            filings = metadata.get(issuer_name, [])
            for period_end in extraction_periods:
                filing = choose_filing(filings, period_end)
                if filing is None:
                    self.repository.add_review(
                        run_id,
                        issuer_name,
                        representative.symbol,
                        "PENDING_FILING",
                        period_end=period_end,
                        detail="No quarterly PDF matching the target period was exposed by CSE.",
                    )
                else:
                    selected.append(filing)

        self.progress(f"[3/7] Downloading and hashing {len(selected)} official CSE PDFs")
        downloaded: list[DownloadedFiling] = []
        with ThreadPoolExecutor(max_workers=download_workers) as executor:
            download_futures = {
                executor.submit(
                    download_filing,
                    filing,
                    self.data / "raw" / "filings",
                    max_file_bytes=self.app_config.max_file_bytes,
                    offline=offline,
                ): filing
                for filing in selected
            }
            for index, download_future in enumerate(as_completed(download_futures), start=1):
                filing = download_futures[download_future]
                try:
                    downloaded.append(download_future.result())
                except Exception as exc:
                    errors.append(
                        {
                            "issuer_name": filing.issuer_name,
                            "symbol": filing.symbol,
                            "period_end": filing.period_end.isoformat(),
                            "stage": "DOWNLOAD",
                            "error": str(exc),
                        }
                    )
                    self.repository.add_review(
                        run_id,
                        filing.issuer_name,
                        filing.symbol,
                        "DOWNLOAD_FAILED",
                        period_end=filing.period_end,
                        detail=str(exc),
                    )
                if index % 50 == 0 or index == len(download_futures):
                    self.progress(f"      downloaded {index}/{len(download_futures)}")

        self.progress(f"[4/7] Extracting statements from {len(downloaded)} PDFs")
        extracted_results: list[tuple[DownloadedFiling, list[ExtractedFact]]] = []

        def extract_one(item: DownloadedFiling) -> tuple[DownloadedFiling, list[ExtractedFact]]:
            diagnostics_dir = self.data / "tmp" / run_id / item.sha256[:16]
            facts = extract_filing(
                item.local_path,
                item.filing.issuer_name,
                item.filing.symbol,
                item.filing.period_end,
                self.data / "bronze" / "ocr" / item.local_path.parent.name,
                ocr_enabled=self.app_config.ocr_enabled,
                issuers=self.issuers,
                diagnostics_dir=(
                    diagnostics_dir if self.app_config.keep_review_diagnostics else None
                ),
                auto_approve_threshold=self.app_config.auto_approve_threshold,
                manual_review_threshold=self.app_config.manual_review_threshold,
            )
            quality_path = diagnostics_dir / "document_quality.json"
            if quality_path.exists():
                bronze_path = (
                    self.data / "bronze" / "document_metadata" / f"{item.sha256[:16]}.json"
                )
                bronze_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(quality_path, bronze_path)
            return item, facts

        with ThreadPoolExecutor(max_workers=extraction_workers) as executor:
            extraction_futures = {executor.submit(extract_one, item): item for item in downloaded}
            for index, extraction_future in enumerate(as_completed(extraction_futures), start=1):
                item = extraction_futures[extraction_future]
                try:
                    downloaded_item, facts = extraction_future.result()
                    extracted_results.append((downloaded_item, facts))
                except Exception as exc:
                    errors.append(
                        {
                            "issuer_name": item.filing.issuer_name,
                            "symbol": item.filing.symbol,
                            "period_end": item.filing.period_end.isoformat(),
                            "stage": "EXTRACTION",
                            "error": str(exc),
                        }
                    )
                    self.repository.add_review(
                        run_id,
                        item.filing.issuer_name,
                        item.filing.symbol,
                        "EXTRACTION_FAILED",
                        period_end=item.filing.period_end,
                        detail=str(exc),
                    )
                if index % 50 == 0 or index == len(extraction_futures):
                    self.progress(f"      extracted {index}/{len(extraction_futures)}")

        extracted_results = derive_cumulative_quarters(extracted_results)
        extracted_results = derive_ratio_facts(extracted_results, display_periods=target_periods)
        for downloaded_item, facts in extracted_results:
            self.repository.save_filing_and_facts(downloaded_item, facts)

        self.progress("[5/7] Extracting quarter-end prices disclosed in the filings")
        symbols_by_issuer: dict[str, list[str]] = {}
        for security in securities:
            symbols_by_issuer.setdefault(security.company_name, []).append(security.symbol)
        price_status_counts: Counter[str] = Counter()
        published_prices: list[QuarterPrice] = []
        price_items = [
            item for item, _facts in extracted_results if item.filing.period_end in target_periods
        ]

        def extract_prices(
            item: DownloadedFiling,
        ) -> tuple[DownloadedFiling, list[QuarterPrice]]:
            return (
                item,
                extract_quarter_prices(
                    item.local_path,
                    item.filing.issuer_name,
                    symbols_by_issuer.get(item.filing.issuer_name, [item.filing.symbol]),
                    item.filing.period_end,
                    self.data / "bronze" / "text" / item.local_path.parent.name,
                ),
            )

        with ThreadPoolExecutor(max_workers=extraction_workers) as executor:
            price_futures = {executor.submit(extract_prices, item): item for item in price_items}
            for index, future in enumerate(as_completed(price_futures), start=1):
                item = price_futures[future]
                try:
                    downloaded_item, prices = future.result()
                    filled: list[QuarterPrice] = []
                    for price in prices:
                        if price.status == "EXTRACTED" and price.value is not None:
                            filled.append(price)
                            continue
                        resolved = resolve_quarter_end_price(
                            self.root, price.symbol, price.period_end
                        )
                        if resolved is None:
                            filled.append(price)
                            continue
                        value, price_date, method = resolved
                        filled.append(
                            replace(
                                price,
                                value=value,
                                source_line=(
                                    f"price_date={price_date.isoformat()}; never live snapshot "
                                    "after quarter end"
                                ),
                                source_method=method,
                                confidence="MEDIUM",
                                status="EXTRACTED",
                                confidence_score=0.8,
                                certainty_band="MEDIUM",
                                validation_status="PASSED",
                            )
                        )
                    self.repository.save_quarter_prices(downloaded_item, filled)
                    published_prices.extend(filled)
                    for price in filled:
                        price_status_counts[price.status] += 1
                        if price.status != "EXTRACTED":
                            self.repository.add_review(
                                run_id,
                                price.issuer_name,
                                price.symbol,
                                price.status,
                                period_end=price.period_end,
                                metric_code="MARKET_PRICE_QUARTER_END",
                                detail=price.source_line,
                            )
                except Exception as exc:
                    errors.append(
                        {
                            "issuer_name": item.filing.issuer_name,
                            "symbol": item.filing.symbol,
                            "period_end": item.filing.period_end.isoformat(),
                            "stage": "PRICE_EXTRACTION",
                            "error": str(exc),
                        }
                    )
                if index % 50 == 0 or index == len(price_futures):
                    self.progress(f"      prices {index}/{len(price_futures)}")

        self.progress("[6/7] Applying validation and review rules")
        status_counts: Counter[str] = Counter()
        equation_engine = build_default_equation_engine(
            balance_sheet_relative=self.app_config.balance_sheet_relative
        )
        retry_controller = RetryController(max_rounds=2)
        equation_summary: Counter[str] = Counter()
        retry_summary = {"attempts": 0, "recovered": 0, "filings": 0}

        def _validate_fact_list(fact_list: list[ExtractedFact]):
            return equation_engine.evaluate(facts_by_code(fact_list))

        refreshed_results: list[tuple[DownloadedFiling, list[ExtractedFact]]] = []
        for item, facts in extracted_results:
            for fact in facts:
                if fact.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}:
                    diagnostic_path = (
                        self.data / "tmp" / run_id / item.sha256[:16] / "diagnostics.json"
                    )
                    self.repository.add_review(
                        run_id,
                        fact.issuer_name,
                        fact.symbol,
                        fact.status,
                        period_end=fact.period_end,
                        metric_code=fact.metric_code,
                        detail=fact.source_line,
                        diagnostic_path=str(diagnostic_path) if diagnostic_path.exists() else None,
                    )
            results = _validate_fact_list(facts)
            for result in results:
                equation_summary[result.outcome.value] += 1
            failures = [
                result for result in results if result.outcome == ValidationOutcome.FAIL
            ]
            if failures:
                lineage_dir = self.data / "tmp" / run_id / item.sha256[:16]
                outcome = retry_controller.run(
                    facts,
                    pdf_path=item.local_path,
                    issuer_name=item.filing.issuer_name,
                    symbol=item.filing.symbol,
                    period_end=item.filing.period_end,
                    validate=_validate_fact_list,
                    extract=extract_filing,
                    lineage_dir=lineage_dir,
                )
                retry_summary["filings"] += 1
                retry_summary["attempts"] += len(outcome.attempts)
                if outcome.recovered:
                    retry_summary["recovered"] += 1
                if outcome.attempts and outcome.facts is not facts:
                    facts = outcome.facts
                    self.repository.save_filing_and_facts(item, facts)
                results = outcome.final_results
            for result in results:
                if result.outcome != ValidationOutcome.FAIL:
                    continue
                reason = {
                    "BALANCE_SHEET_IDENTITY": "BALANCE_SHEET_RECONCILIATION_FAILED",
                    "BALANCE_SHEET_SANITY": "BALANCE_SHEET_SANITY_FAILED",
                    "CROSS_METRIC_CONTEXT_INCONSISTENT": "CROSS_METRIC_CONTEXT_INCONSISTENT",
                    "PAT_TAX_BRIDGE": "PAT_TAX_BRIDGE_MISMATCH",
                    "EPS_RECONCILIATION": "EPS_RECONCILIATION_FAILED",
                    "NAVPS_RECONCILIATION": "NAVPS_RECONCILIATION_FAILED",
                }.get(result.rule_id, result.rule_id)
                self.repository.add_review(
                    run_id,
                    item.filing.issuer_name,
                    item.filing.symbol,
                    reason,
                    period_end=item.filing.period_end,
                    detail=result.detail,
                )
            failed_metrics: set[str] = set()
            for result in results:
                if result.outcome != ValidationOutcome.FAIL:
                    continue
                failed_metrics.update(
                    {
                        "BALANCE_SHEET_IDENTITY": {
                            "TOTAL_ASSETS",
                            "TOTAL_LIABILITIES",
                            "TOTAL_EQUITY",
                        },
                        "BALANCE_SHEET_SANITY": {"TOTAL_ASSETS", "TOTAL_EQUITY"},
                        "CROSS_METRIC_CONTEXT_INCONSISTENT": {
                            "TOP_LINE",
                            "OPERATING_PROFIT",
                            "PBT",
                            "PAT",
                            "EPS_BASIC",
                            "EPS_DILUTED",
                        },
                        "PAT_TAX_BRIDGE": {"PBT", "PAT"},
                        "EPS_RECONCILIATION": {
                            "PAT",
                            "EPS_BASIC",
                            "EPS_DILUTED",
                            "EPS_SELECTED",
                        },
                        "NAVPS_RECONCILIATION": {"TOTAL_EQUITY", "NAVPS"},
                    }.get(result.rule_id, set())
                )
            stamped: list[ExtractedFact] = []
            for fact in facts:
                if fact.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}:
                    stamped.append(fact)
                    continue
                if fact.metric_code in failed_metrics:
                    evidence = {}
                    if fact.evidence_json:
                        try:
                            parsed = json.loads(fact.evidence_json)
                            evidence = parsed if isinstance(parsed, dict) else {}
                        except json.JSONDecodeError:
                            evidence = {}
                    evidence["equation_failures"] = sorted(failed_metrics)
                    stamped.append(
                        replace(
                            fact,
                            validation_status="FAILED",
                            evidence_json=json.dumps(evidence, separators=(",", ":")),
                        )
                    )
                elif fact.validation_status in {"NOT_VALIDATED", "REVIEW"}:
                    stamped.append(replace(fact, validation_status="PASSED"))
                else:
                    stamped.append(fact)
            facts = stamped
            refreshed_results.append((item, facts))
        extracted_results = refreshed_results
        status_counts = Counter(
            fact.status for _item, facts in extracted_results for fact in facts
        )
        for mismatch in flag_cross_filing_mismatches(
            extracted_results,
            self.data / "gold" / "current_financial_facts.parquet",
        ):
            self.repository.add_review(
                run_id,
                mismatch.issuer_name,
                mismatch.symbol,
                "CROSS_FILING_MISMATCH",
                period_end=mismatch.period_end,
                metric_code=mismatch.metric_code,
                detail=mismatch.detail,
            )

        self.progress("[7/7] Exporting normalized facts, prices, review queue, and manifest")
        self.outputs.mkdir(parents=True, exist_ok=True)
        run_dir = run_output_dir(self.root, as_of_date.isoformat(), run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        facts_csv = self.outputs / f"normalized_facts_{as_of_date.isoformat()}.csv"
        review_csv = self.outputs / f"review_queue_{as_of_date.isoformat()}.csv"
        prices_csv = self.outputs / f"quarter_end_prices_{as_of_date.isoformat()}.csv"
        self.repository.export_facts_csv(facts_csv, extraction_periods)
        self.repository.export_prices_csv(prices_csv, target_periods)
        self.repository.export_review_csv(review_csv, run_id)
        error_path = self.outputs / f"pipeline_errors_{as_of_date.isoformat()}.json"
        error_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")
        shutil.copy2(facts_csv, run_dir / "normalized_facts.csv")
        shutil.copy2(review_csv, run_dir / "review_queue.csv")
        shutil.copy2(prices_csv, run_dir / "quarter_end_prices.csv")
        shutil.copy2(error_path, run_dir / "pipeline_errors.json")
        golden_validation = validate_golden(self.root, as_of_date)
        gate_hits = evaluate_production_gates(
            extracted_results,
            published_prices,
            golden_validation=golden_validation,
            required_scope={
                name: profile.standalone_scope_label for name, profile in self.issuers.items()
            },
            previous_status_counts=_previous_fact_status_counts(preserved),
            coverage_baseline=load_coverage_baseline(self.root),
        )
        for hit in gate_hits:
            self.repository.add_review(
                run_id,
                hit.issuer_name,
                hit.symbol,
                hit.code,
                period_end=hit.period_end,
                metric_code=hit.metric_code,
                detail=hit.detail,
            )
        run_status = run_status_from_gates(
            gate_hits,
            has_errors=bool(errors),
            has_review=bool(self.repository.review_rows),
        )

        statistics: dict[str, object] = {
            "run_id": run_id,
            "as_of_date": as_of_date.isoformat(),
            "target_periods": [period.isoformat() for period in target_periods],
            "supporting_periods": [period.isoformat() for period in extraction_periods],
            "security_count": len(securities),
            "issuer_count": len(representatives),
            "selected_filing_count": len(selected),
            "downloaded_filing_count": len(downloaded),
            "extracted_filing_count": len(extracted_results),
            "fact_status_counts": dict(status_counts),
            "price_status_counts": dict(price_status_counts),
            "pipeline_error_count": len(errors),
            "golden_validation_sample_size": golden_validation["sample_size"],
            "golden_validation_accuracy": golden_validation["accuracy"],
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
            "config_hash": config_hash(self.root),
            **git_identity(self.root).as_dict(),
            "equation_validation": dict(equation_summary),
            "retry_summary": retry_summary,
            "ocr_enabled": self.app_config.ocr_enabled,
            "use_transformer": self.app_config.use_transformer,
            "semantic_model": get_semantic_matcher().model_name,
            "archived_prior_run_files": [str(path) for path in archived],
            "current_facts_parquet": str(self.data / "gold" / "current_financial_facts.parquet"),
            "current_prices_parquet": str(self.data / "gold" / "current_market_prices.parquet"),
        }
        workbook_path: Path | None = None
        if not skip_excel:
            workbook_path = generate_excel(self.root, as_of_date, target_periods, run_id)
            statistics["workbook"] = str(workbook_path)
        dashboard_path = generate_run_dashboard(
            self.root, as_of_date, target_periods, run_id, run_dir, statistics
        )
        statistics["dashboard"] = str(dashboard_path)
        manifests_dir = self.outputs / MANIFESTS_DIRNAME
        manifests_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifests_dir / f"run_manifest_{as_of_date.isoformat()}.json"
        dated_manifest = manifests_dir / f"{as_of_date.isoformat()}_{run_id}.json"
        statistics["manifest"] = str(manifest_path)
        statistics["run_manifest"] = str(dated_manifest)
        payload = json.dumps(statistics, indent=2)
        manifest_path.write_text(payload, encoding="utf-8")
        dated_manifest.write_text(payload, encoding="utf-8")
        shutil.copy2(manifest_path, run_dir / "run_manifest.json")
        golden_path = self.outputs / f"golden_validation_{as_of_date.isoformat()}.json"
        if golden_path.exists():
            shutil.copy2(golden_path, run_dir / "golden_validation.json")
        if workbook_path is not None:
            shutil.copy2(workbook_path, run_dir / "CSE_Financial_Snapshot.xlsx")
        self.repository.finish_run(run_id, run_status, statistics)
        return statistics

    def _validate_market_snapshot(self, run_id: str, securities: list[Security]) -> None:
        share_total = Decimal(0)
        priced = 0
        for security in securities:
            if security.market_cap_percentage is not None:
                share_total += Decimal(str(security.market_cap_percentage))
            if security.price in (None, 0) or security.issued_quantity in (None, 0):
                continue
            if security.market_capitalization is None:
                continue
            priced += 1
            expected = Decimal(str(security.price)) * Decimal(str(security.issued_quantity))
            difference = abs(expected - Decimal(str(security.market_capitalization)))
            if difference > Decimal("1"):
                self.repository.add_review(
                    run_id,
                    security.company_name,
                    security.symbol,
                    "VALIDATION_FAILED",
                    detail=(
                        f"Market capitalization {security.market_capitalization} differs from "
                        f"price × issued quantity {expected} by {difference}."
                    ),
                    metric_code="MARKET_CAPITALIZATION",
                )
        if priced and abs(share_total - Decimal(100)) > Decimal("0.05"):
            self.repository.add_review(
                run_id,
                "MARKET",
                "ALL",
                "VALIDATION_FAILED",
                detail=f"Market-cap shares sum to {share_total}%; expected approximately 100%.",
                metric_code="MARKET_CAP_SHARE",
            )
