from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.config import config_hash, git_identity
from cse_financial_etl.extraction.resilient_runner import (
    extract_filing_resilient,
    extract_quarter_prices_resilient,
)
from cse_financial_etl.orchestration import pipeline as pipeline_module
from cse_financial_etl.orchestration.pipeline import Pipeline


@contextmanager
def _patched_resilient_extractors(
    *,
    project_root: Path,
    process_timeout_seconds: float,
    cache_namespace: str,
) -> Iterator[None]:
    """Patch only the current process while ``Pipeline.run`` is executing.

    Pipeline retries read ``extract_filing`` from the orchestration module at runtime,
    so the same wrapper covers the primary pass and all retry strategies. Completed
    filing/price results persist under ``data/cache/resilient`` and are reused on a
    later run only when source SHA + code/config namespace + extraction options match.
    """

    original_extract = pipeline_module.extract_filing
    original_prices = pipeline_module.extract_quarter_prices
    financial_cache = project_root / "data" / "cache" / "resilient" / "financial"
    price_cache = project_root / "data" / "cache" / "resilient" / "prices"

    def resilient_extract(
        pdf_path: Path,
        issuer_name: str,
        symbol: str,
        period_end: date,
        text_cache_dir: Path | None = None,
        **kwargs: Any,
    ):
        return extract_filing_resilient(
            pdf_path,
            issuer_name,
            symbol,
            period_end,
            text_cache_dir,
            project_root=project_root,
            result_cache_dir=financial_cache,
            process_timeout_seconds=process_timeout_seconds,
            cache_namespace=cache_namespace,
            **kwargs,
        )

    def resilient_prices(
        pdf_path: Path,
        issuer_name: str,
        symbols: list[str],
        period_end: date,
        text_cache_dir: Path | None = None,
    ):
        return extract_quarter_prices_resilient(
            pdf_path,
            issuer_name,
            symbols,
            period_end,
            text_cache_dir,
            result_cache_dir=price_cache,
            process_timeout_seconds=process_timeout_seconds,
            cache_namespace=cache_namespace,
        )

    pipeline_module.extract_filing = resilient_extract  # type: ignore[assignment]
    pipeline_module.extract_quarter_prices = resilient_prices
    try:
        yield
    finally:
        pipeline_module.extract_filing = original_extract
        pipeline_module.extract_quarter_prices = original_prices


def run_resilient_pipeline(
    project_root: Path,
    *,
    as_of_date: date,
    periods: tuple[date, ...],
    process_timeout_seconds: float = 180.0,
    api_workers: int = 24,
    download_workers: int = 20,
    extraction_workers: int = 8,
    issuer_limit: int | None = None,
    offline: bool = False,
    skip_excel: bool = False,
    compile_statements: bool = True,
    run_tunnel_b_always: bool = False,
    progress: Any = print,
) -> dict[str, object]:
    """Run the normal ETL with per-PDF process isolation and resumable result caches."""

    root = project_root.resolve()
    identity = git_identity(root)
    revision = identity.commit_sha or "no-git-sha"
    namespace = f"{revision}:{config_hash(root)}:resilient-v1"
    pipeline = Pipeline(root, progress=progress)
    try:
        with _patched_resilient_extractors(
            project_root=root,
            process_timeout_seconds=process_timeout_seconds,
            cache_namespace=namespace,
        ):
            result = pipeline.run(
                as_of_date,
                periods,
                api_workers=api_workers,
                download_workers=download_workers,
                extraction_workers=extraction_workers,
                issuer_limit=issuer_limit,
                offline=offline,
                skip_excel=skip_excel,
                compile_statements=compile_statements,
                run_tunnel_b_always=run_tunnel_b_always,
            )
    finally:
        pipeline.close()
    result["resilient_processing"] = {
        "enabled": True,
        "per_pdf_timeout_seconds": process_timeout_seconds,
        "cache_namespace": namespace,
        "financial_cache": str(root / "data" / "cache" / "resilient" / "financial"),
        "price_cache": str(root / "data" / "cache" / "resilient" / "prices"),
    }
    return result
