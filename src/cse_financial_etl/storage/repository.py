from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, QuarterPrice
from cse_financial_etl.sources.cse import DownloadedFiling, Security


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fact_id(filing_id: int, sha256: str, metric_code: str) -> str:
    payload = f"{filing_id}:{sha256}:{metric_code}".encode()
    return "fact_" + hashlib.sha256(payload).hexdigest()[:24]


def _atomic_parquet(path: Path, rows: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame = pl.DataFrame(rows, schema=schema, strict=False) if rows else pl.DataFrame(schema=schema)
    frame.write_parquet(temporary, compression="zstd", statistics=True)
    temporary.replace(path)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


MARKET_SCHEMA = {
    "as_of_date": pl.String,
    "security_id": pl.Int64,
    "company_name": pl.String,
    "symbol": pl.String,
    "price": pl.Float64,
    "issued_quantity": pl.Int64,
    "market_capitalization": pl.Float64,
    "market_cap_percentage": pl.Float64,
}
FILING_SCHEMA = {
    "filing_id": pl.Int64,
    "issuer_name": pl.String,
    "symbol": pl.String,
    "period_end": pl.String,
    "title": pl.String,
    "source_url": pl.String,
    "local_path": pl.String,
    "sha256": pl.String,
    "size_bytes": pl.Int64,
    "current_version": pl.Boolean,
    "ingested_at": pl.String,
}
FACT_SCHEMA = {
    "fact_id": pl.String,
    "filing_id": pl.Int64,
    "filing_sha256": pl.String,
    "issuer_name": pl.String,
    "symbol": pl.String,
    "period_end": pl.String,
    "period_type": pl.String,
    "duration_months": pl.Int64,
    "metric_code": pl.String,
    "metric_type": pl.String,
    "raw_text": pl.String,
    "raw_value": pl.String,
    "normalized_value": pl.String,
    "currency": pl.String,
    "scale_factor": pl.Int64,
    "entity_scope": pl.String,
    "comparison_role": pl.String,
    "source_page": pl.Int64,
    "source_line": pl.String,
    "source_bbox": pl.String,
    "unit_source_text": pl.String,
    "extraction_method": pl.String,
    "semantic_model": pl.String,
    "semantic_confidence": pl.Float64,
    "entity_confidence": pl.Float64,
    "period_confidence": pl.Float64,
    "unit_confidence": pl.Float64,
    "column_confidence": pl.Float64,
    "validation_confidence": pl.Float64,
    "overall_certainty": pl.Float64,
    "certainty_band": pl.String,
    "confidence": pl.String,
    "status": pl.String,
    "validation_status": pl.String,
    "review_status": pl.String,
    "missing_reason": pl.String,
    "extracted_at": pl.String,
}
PRICE_SCHEMA = {
    "issuer_name": pl.String,
    "symbol": pl.String,
    "period_end": pl.String,
    "value": pl.String,
    "source_method": pl.String,
    "source_page": pl.Int64,
    "source_line": pl.String,
    "source_bbox": pl.String,
    "filing_id": pl.Int64,
    "filing_sha256": pl.String,
    "confidence": pl.String,
    "confidence_score": pl.Float64,
    "certainty_band": pl.String,
    "status": pl.String,
    "validation_status": pl.String,
    "extracted_at": pl.String,
}
REVIEW_SCHEMA = {
    "run_id": pl.String,
    "issuer_name": pl.String,
    "symbol": pl.String,
    "period_end": pl.String,
    "metric_code": pl.String,
    "reason": pl.String,
    "detail": pl.String,
    "diagnostic_path": pl.String,
    "created_at": pl.String,
}
ISSUER_SCHEMA = {
    "issuer_id": pl.String,
    "legal_name": pl.String,
    "issuer_type": pl.String,
    "standalone_scope_label": pl.String,
}
DERIVED_METRIC_CODES = {"DEBT_TO_EQUITY", "ROE", "ROA", "NPM"}


class Repository:
    """Transactional Parquet/JSONL repository with atomic promotion."""

    def __init__(self, data_root: Path) -> None:
        self.root = data_root
        self.run_id: str | None = None
        self.as_of_date: date | None = None
        self.started_at: str | None = None
        self.market_rows: list[dict[str, Any]] = []
        self.filing_rows: list[dict[str, Any]] = []
        self.fact_rows: list[dict[str, Any]] = []
        self.price_rows: list[dict[str, Any]] = []
        self.review_rows: list[dict[str, Any]] = []
        self.evidence_rows: list[dict[str, Any]] = []

    def close(self) -> None:
        """File-backed storage has no connection to close."""

    def start_run(self, run_id: str, as_of_date: date) -> None:
        self.run_id = run_id
        self.as_of_date = as_of_date
        self.started_at = _now()
        (self.root / "staging" / run_id).mkdir(parents=True, exist_ok=True)

    def save_market(self, as_of_date: date, securities: Iterable[Security]) -> None:
        self.market_rows.extend(
            {
                "as_of_date": as_of_date.isoformat(),
                "security_id": security.security_id,
                "company_name": security.company_name,
                "symbol": security.symbol,
                "price": security.price,
                "issued_quantity": security.issued_quantity,
                "market_capitalization": security.market_capitalization,
                "market_cap_percentage": security.market_cap_percentage,
            }
            for security in securities
        )

    def save_filing_and_facts(
        self, downloaded: DownloadedFiling, facts: Iterable[ExtractedFact]
    ) -> None:
        ingested_at = _now()
        filing = downloaded.filing
        self.filing_rows.append(
            {
                "filing_id": filing.filing_id,
                "issuer_name": filing.issuer_name,
                "symbol": filing.symbol,
                "period_end": filing.period_end.isoformat(),
                "title": filing.title,
                "source_url": filing.source_url,
                "local_path": str(downloaded.local_path),
                "sha256": downloaded.sha256,
                "size_bytes": downloaded.size_bytes,
                "current_version": True,
                "ingested_at": ingested_at,
            }
        )
        for fact in facts:
            fact_id = _fact_id(filing.filing_id, downloaded.sha256, fact.metric_code)
            row = {
                "fact_id": fact_id,
                "filing_id": filing.filing_id,
                "filing_sha256": downloaded.sha256,
                "issuer_name": fact.issuer_name,
                "symbol": fact.symbol,
                "period_end": fact.period_end.isoformat(),
                "period_type": (
                    "QUARTER"
                    if fact.duration_months == 3
                    else "FY"
                    if fact.duration_months == 12
                    else "YTD"
                    if fact.duration_months in {6, 9}
                    else "AS_AT"
                ),
                "duration_months": fact.duration_months,
                "metric_code": fact.metric_code,
                "metric_type": fact.metric_type,
                "raw_text": fact.raw_text,
                "raw_value": str(fact.raw_value) if fact.raw_value is not None else None,
                "normalized_value": (
                    str(fact.normalized_value) if fact.normalized_value is not None else None
                ),
                "currency": fact.currency,
                "scale_factor": fact.scale_factor,
                "entity_scope": fact.entity_scope,
                "comparison_role": fact.comparison_role,
                "source_page": fact.source_page,
                "source_line": fact.source_line,
                "source_bbox": fact.source_bbox,
                "unit_source_text": fact.unit_source_text,
                "extraction_method": fact.extraction_method,
                "semantic_model": fact.semantic_model,
                "semantic_confidence": fact.semantic_confidence,
                "entity_confidence": fact.entity_confidence,
                "period_confidence": fact.period_confidence,
                "unit_confidence": fact.unit_confidence,
                "column_confidence": fact.column_confidence,
                "validation_confidence": fact.validation_confidence,
                "overall_certainty": fact.overall_certainty,
                "certainty_band": fact.certainty_band,
                "confidence": fact.confidence,
                "status": fact.status,
                "validation_status": fact.validation_status,
                "review_status": fact.review_status,
                "missing_reason": None if fact.status.startswith("EXTRACTED") else fact.status,
                "extracted_at": ingested_at,
            }
            self.fact_rows.append(row)
            if fact.evidence_json:
                try:
                    evidence = json.loads(fact.evidence_json)
                except json.JSONDecodeError:
                    evidence = {"raw": fact.evidence_json}
                self.evidence_rows.append(
                    {
                        "fact_id": fact_id,
                        "filing_id": filing.filing_id,
                        "filing_sha256": downloaded.sha256,
                        "issuer_name": fact.issuer_name,
                        "period_end": fact.period_end.isoformat(),
                        "metric_code": fact.metric_code,
                        "source_page": fact.source_page,
                        "evidence": evidence,
                    }
                )

    def save_quarter_prices(
        self, downloaded: DownloadedFiling, prices: Iterable[QuarterPrice]
    ) -> None:
        extracted_at = _now()
        for price in prices:
            self.price_rows.append(
                {
                    "issuer_name": price.issuer_name,
                    "symbol": price.symbol,
                    "period_end": price.period_end.isoformat(),
                    "value": str(price.value) if price.value is not None else None,
                    "source_method": price.source_method,
                    "source_page": price.source_page,
                    "source_line": price.source_line,
                    "source_bbox": price.source_bbox,
                    "filing_id": downloaded.filing.filing_id,
                    "filing_sha256": downloaded.sha256,
                    "confidence": price.confidence,
                    "confidence_score": price.confidence_score,
                    "certainty_band": price.certainty_band,
                    "status": price.status,
                    "validation_status": price.validation_status,
                    "extracted_at": extracted_at,
                }
            )

    def add_review(
        self,
        run_id: str,
        issuer_name: str,
        symbol: str,
        reason: str,
        *,
        period_end: date | None = None,
        metric_code: str | None = None,
        detail: str | None = None,
        diagnostic_path: str | None = None,
    ) -> None:
        self.review_rows.append(
            {
                "run_id": run_id,
                "issuer_name": issuer_name,
                "symbol": symbol,
                "period_end": period_end.isoformat() if period_end else None,
                "metric_code": metric_code,
                "reason": reason,
                "detail": detail,
                "diagnostic_path": diagnostic_path,
                "created_at": _now(),
            }
        )

    def _staging(self) -> Path:
        if self.run_id is None:
            raise RuntimeError("start_run must be called before persistence")
        return self.root / "staging" / self.run_id

    def _apply_curated_corrections(self) -> None:
        path = self.root / "curated" / "manual_corrections.parquet"
        if not path.exists():
            return
        try:
            frame = pl.read_parquet(path)
        except Exception:
            return
        if frame.is_empty():
            return
        lookup = {
            (str(row["issuer_name"]), str(row["period_end"]), str(row["metric_code"])): row
            for row in frame.to_dicts()
        }
        for fact in self.fact_rows:
            correction = lookup.get(
                (str(fact["issuer_name"]), str(fact["period_end"]), str(fact["metric_code"]))
            )
            if correction is None:
                continue
            fact["normalized_value"] = correction.get("corrected_value")
            fact["status"] = "EXTRACTED"
            fact["review_status"] = "CURATED"
            fact["validation_status"] = "PASSED"
            fact["missing_reason"] = None
            fact["extraction_method"] = "CURATED_OVERRIDE"

    def _write_staging(self, status: str, statistics: dict[str, Any]) -> Path:
        self._apply_curated_corrections()
        staging = self._staging()
        _atomic_parquet(staging / "financial_facts.parquet", self.fact_rows, FACT_SCHEMA)
        _atomic_parquet(staging / "market_prices.parquet", self.price_rows, PRICE_SCHEMA)
        _atomic_parquet(staging / "market_snapshot.parquet", self.market_rows, MARKET_SCHEMA)
        _atomic_parquet(staging / "filings.parquet", self.filing_rows, FILING_SCHEMA)
        _atomic_parquet(staging / "review_queue.parquet", self.review_rows, REVIEW_SCHEMA)
        issuer_rows = self._issuer_rows()
        _atomic_parquet(staging / "issuers.parquet", issuer_rows, ISSUER_SCHEMA)
        derived_rows = [
            row for row in self.fact_rows if str(row.get("metric_code")) in DERIVED_METRIC_CODES
        ]
        _atomic_parquet(staging / "derived_facts.parquet", derived_rows, FACT_SCHEMA)
        _atomic_text(
            staging / "evidence.jsonl",
            "".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in self.evidence_rows
            ),
        )
        manifest = {
            **statistics,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": _now(),
            "status": status,
            "storage": "PARQUET_JSONL",
            "staging_path": str(staging),
        }
        _atomic_text(staging / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        return staging

    @staticmethod
    def _promote_file(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)

    def _issuer_rows(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for row in self.market_rows:
            name = str(row["company_name"])
            key = name.casefold()
            if key in seen:
                continue
            upper = name.upper()
            issuer_type = "GENERAL"
            scope = "COMPANY"
            if "BANK" in upper and "FOOD" not in upper:
                issuer_type = "BANK"
                scope = "BANK"
            elif any(token in upper for token in ("INSURANCE", "ASSURANCE", "TAKAFUL")):
                issuer_type = "INSURANCE"
            elif any(token in upper for token in ("FINANCE", "LEASING", "MICROFINANCE")):
                issuer_type = "FINANCE_COMPANY"
            seen[key] = {
                "issuer_id": name,
                "legal_name": name,
                "issuer_type": issuer_type,
                "standalone_scope_label": scope,
            }
        return sorted(seen.values(), key=lambda row: str(row["legal_name"]))

    def _coverage_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        metrics = ["ALL", *sorted({str(row["metric_code"]) for row in self.fact_rows})]
        for metric in metrics:
            subset = (
                self.fact_rows
                if metric == "ALL"
                else [row for row in self.fact_rows if row["metric_code"] == metric]
            )
            total = len(subset)
            extracted = sum(str(row["status"]).startswith("EXTRACTED") for row in subset)
            rows.append(
                {
                    "metric_code": metric,
                    "total_count": total,
                    "extracted_count": extracted,
                    "coverage_rate": extracted / total if total else None,
                }
            )
        return rows

    def _certainty_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        validation: dict[str, Any] = {}
        if self.as_of_date is not None:
            validation_path = (
                self.root.parent
                / "outputs"
                / f"golden_validation_{self.as_of_date.isoformat()}.json"
            )
            if validation_path.exists():
                validation = json.loads(validation_path.read_text(encoding="utf-8"))
        metrics = ["ALL", *sorted({str(row["metric_code"]) for row in self.fact_rows})]
        for metric in metrics:
            subset = (
                self.fact_rows
                if metric == "ALL"
                else [row for row in self.fact_rows if row["metric_code"] == metric]
            )
            bands = Counter(str(row["certainty_band"]) for row in subset)
            scored = [float(row["overall_certainty"] or 0) for row in subset]
            validation_row = (
                validation if metric == "ALL" else validation.get("by_metric", {}).get(metric, {})
            )
            rows.append(
                {
                    "metric_code": metric,
                    "record_count": len(subset),
                    "high_count": bands["HIGH"],
                    "medium_count": bands["MEDIUM"],
                    "low_count": bands["LOW"],
                    "none_count": bands["NONE"],
                    "mean_certainty": sum(scored) / len(scored) if scored else None,
                    "measured_accuracy": validation_row.get("accuracy"),
                    "accuracy_sample_size": validation_row.get("sample_size", 0),
                    "accuracy_note": "Certainty is not accuracy; accuracy needs validated fixtures.",
                }
            )
        return rows

    def _promote(self, staging: Path) -> None:
        if self.run_id is None or self.as_of_date is None:
            raise RuntimeError("Run metadata is missing")
        short_run = self.run_id.split("-")[0]
        self._promote_file(
            staging / "market_snapshot.parquet",
            self.root
            / "silver"
            / "market_snapshots"
            / f"date={self.as_of_date.isoformat()}"
            / f"part-{short_run}.parquet",
        )
        self._promote_file(
            staging / "filings.parquet", self.root / "silver" / "filings" / "filings.parquet"
        )
        self._promote_file(
            staging / "issuers.parquet", self.root / "silver" / "issuers" / "issuers.parquet"
        )
        self._promote_file(
            staging / "market_snapshot.parquet",
            self.root / "silver" / "securities" / "securities.parquet",
        )
        for year in sorted({str(row["period_end"])[:4] for row in self.fact_rows}):
            fact_path = staging / f"financial_facts_{year}.parquet"
            year_facts = [row for row in self.fact_rows if str(row["period_end"]).startswith(year)]
            _atomic_parquet(fact_path, year_facts, FACT_SCHEMA)
            self._promote_file(
                fact_path,
                self.root
                / "silver"
                / "financial_facts"
                / f"year={year}"
                / f"part-{short_run}.parquet",
            )
            evidence_path = staging / f"evidence_{year}.jsonl"
            year_evidence = [
                row for row in self.evidence_rows if str(row["period_end"]).startswith(year)
            ]
            _atomic_text(
                evidence_path,
                "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in year_evidence),
            )
            self._promote_file(
                evidence_path,
                self.root / "silver" / "evidence" / f"year={year}" / f"part-{short_run}.jsonl",
            )
        for year in sorted({str(row["period_end"])[:4] for row in self.price_rows}):
            price_path = staging / f"market_prices_{year}.parquet"
            year_prices = [
                row for row in self.price_rows if str(row["period_end"]).startswith(year)
            ]
            _atomic_parquet(price_path, year_prices, PRICE_SCHEMA)
            self._promote_file(
                price_path,
                self.root
                / "silver"
                / "market_prices"
                / f"year={year}"
                / f"part-{short_run}.parquet",
            )
        derived_rows = [
            row for row in self.fact_rows if str(row.get("metric_code")) in DERIVED_METRIC_CODES
        ]
        for year in sorted({str(row["period_end"])[:4] for row in derived_rows}):
            derived_path = staging / f"derived_facts_{year}.parquet"
            year_derived = [row for row in derived_rows if str(row["period_end"]).startswith(year)]
            _atomic_parquet(derived_path, year_derived, FACT_SCHEMA)
            self._promote_file(
                derived_path,
                self.root
                / "silver"
                / "derived_facts"
                / f"year={year}"
                / f"part-{short_run}.parquet",
            )
        self._promote_file(
            staging / "financial_facts.parquet",
            self.root / "gold" / "current_financial_facts.parquet",
        )
        if (staging / "derived_facts.parquet").exists():
            self._promote_file(
                staging / "derived_facts.parquet",
                self.root / "gold" / "derived_metrics.parquet",
            )
        self._promote_file(
            staging / "market_prices.parquet",
            self.root / "gold" / "current_market_prices.parquet",
        )
        _atomic_parquet(
            self.root / "gold" / "extraction_coverage.parquet",
            self._coverage_rows(),
            {
                "metric_code": pl.String,
                "total_count": pl.Int64,
                "extracted_count": pl.Int64,
                "coverage_rate": pl.Float64,
            },
        )
        _atomic_parquet(
            self.root / "gold" / "accuracy_certainty.parquet",
            self._certainty_rows(),
            {
                "metric_code": pl.String,
                "record_count": pl.Int64,
                "high_count": pl.Int64,
                "medium_count": pl.Int64,
                "low_count": pl.Int64,
                "none_count": pl.Int64,
                "mean_certainty": pl.Float64,
                "measured_accuracy": pl.Float64,
                "accuracy_sample_size": pl.Int64,
                "accuracy_note": pl.String,
            },
        )
        self._promote_file(
            staging / "review_queue.parquet", self.root / "review" / "review_queue.parquet"
        )
        self._promote_file(
            staging / "manifest.json",
            self.root / "raw" / "manifests" / f"run_{self.run_id}.json",
        )
        corrections = self.root / "curated" / "manual_corrections.parquet"
        if not corrections.exists():
            _atomic_parquet(
                corrections,
                [],
                {
                    "issuer_name": pl.String,
                    "period_end": pl.String,
                    "metric_code": pl.String,
                    "corrected_value": pl.String,
                    "reason": pl.String,
                    "approved_by": pl.String,
                    "approved_at": pl.String,
                },
            )
        hints = self.root / "curated" / "extraction_hints.json"
        if not hints.exists():
            _atomic_text(hints, "{}\n")

    def finish_run(self, run_id: str, status: str, statistics: dict[str, Any]) -> None:
        if run_id != self.run_id:
            raise ValueError("Attempted to finish a different run")
        staging = self._write_staging(status, statistics)
        if status in {"COMPLETED", "COMPLETED_WITH_REVIEW"}:
            self._promote(staging)

    def _filing_lookup(self) -> dict[tuple[int, str], dict[str, Any]]:
        return {(row["filing_id"], row["sha256"]): row for row in self.filing_rows}

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def export_facts_csv(self, output_path: Path, period_ends: Iterable[date]) -> None:
        periods = {period.isoformat() for period in period_ends}
        filings = self._filing_lookup()
        rows: list[dict[str, Any]] = []
        for fact in self.fact_rows:
            if fact["period_end"] in periods:
                filing = filings.get((fact["filing_id"], fact["filing_sha256"]), {})
                rows.append(
                    {
                        **fact,
                        "filing_title": filing.get("title"),
                        "source_url": filing.get("source_url"),
                        "local_path": filing.get("local_path"),
                    }
                )
        rows.sort(key=lambda row: (row["issuer_name"], row["period_end"], row["metric_code"]))
        self._write_csv(
            output_path,
            rows,
            [*FACT_SCHEMA, "filing_title", "source_url", "local_path"],
        )

    def export_prices_csv(self, output_path: Path, period_ends: Iterable[date]) -> None:
        periods = {period.isoformat() for period in period_ends}
        filings = self._filing_lookup()
        rows: list[dict[str, Any]] = []
        for price in self.price_rows:
            if price["period_end"] in periods:
                filing = filings.get((price["filing_id"], price["filing_sha256"]), {})
                rows.append(
                    {
                        **price,
                        "filing_title": filing.get("title"),
                        "source_url": filing.get("source_url"),
                    }
                )
        rows.sort(key=lambda row: (row["issuer_name"], row["symbol"], row["period_end"]))
        self._write_csv(output_path, rows, [*PRICE_SCHEMA, "filing_title", "source_url"])

    def export_review_csv(self, output_path: Path, run_id: str) -> None:
        rows = [row for row in self.review_rows if row["run_id"] == run_id]
        rows.sort(
            key=lambda row: (
                row["issuer_name"],
                row["period_end"] or "",
                row["metric_code"] or "",
            )
        )
        self._write_csv(output_path, rows, list(REVIEW_SCHEMA))
