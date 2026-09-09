"""Production-only safety boundary around the stable quarterly ETL core.

The extraction/compiler/resolver logic is intentionally not reimplemented here.  This
module hardens the edges that differ between research execution and a governed
production run: time semantics, CSE request pacing, source revision retention,
historical-price provenance, legacy correction blocking, and acceptance-gated gold
activation.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import polars as pl
import yaml

from cse_financial_etl.config import infer_issuer_type, load_issuers
from cse_financial_etl.orchestration import pipeline as pipeline_module
from cse_financial_etl.sources import cse as cse_source
from cse_financial_etl.sources.cse import DownloadedFiling, Filing, Security
from cse_financial_etl.storage.repository import Repository

COLOMBO = ZoneInfo("Asia/Colombo")


@dataclass(slots=True)
class ProductionRunCapture:
    repository: Repository | None = None
    staging: Path | None = None
    status: str | None = None
    statistics: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.repository is not None and self.staging is not None


class _RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self.interval = 0.0 if requests_per_second <= 0 else 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.next_allowed = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_allowed - now)
            if delay:
                time.sleep(delay)
            now = time.monotonic()
            self.next_allowed = max(self.next_allowed, now) + self.interval


def _production_http_settings(project_root: Path) -> tuple[float, int, int]:
    path = project_root / "configs" / "app.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    payload = payload if isinstance(payload, dict) else {}
    http = payload.get("http") or {}
    return (
        float(http.get("requests_per_second", 0.5)),
        max(1, int(http.get("timeout_seconds", 30))),
        max(1, int(http.get("max_retries", 3))),
    )


def _make_rate_limited_post(
    *, requests_per_second: float, timeout_seconds: int, max_retries: int
) -> Callable[..., Any]:
    limiter = _RateLimiter(requests_per_second)

    def post(endpoint: str, data: bytes, content_type: str, timeout: int | None = None) -> Any:
        request = urllib.request.Request(
            f"{cse_source.API_BASE}/{endpoint}",
            data=data,
            method="POST",
            headers={
                "Accept": "application/json",
                "Accept-Language": "en",
                "Content-Type": content_type,
                "User-Agent": cse_source.USER_AGENT,
            },
        )
        last_error: Exception | None = None
        request_timeout = timeout_seconds if timeout is None else timeout
        for attempt in range(max_retries):
            limiter.wait()
            try:
                with urllib.request.urlopen(request, timeout=request_timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if attempt == max_retries - 1:
                    break
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = float(2**attempt)
                time.sleep(max(0.0, delay) + random.uniform(0.0, 0.25))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == max_retries - 1:
                    break
                time.sleep((2**attempt) + random.uniform(0.0, 0.25))
        raise RuntimeError(f"CSE request failed for {endpoint}: {last_error}")

    return post


def _strict_financial_metadata(
    securities: list[Security] | Any,
    cache_dir: Path,
    *,
    workers: int = 24,
    offline: bool = False,
) -> dict[str, list[Filing]]:
    """Never disguise a failed live metadata request as fresh production data.

    Offline mode is an explicit replay and may use the existing cache.  Online mode
    either gets fresh metadata for every issuer or fails the run; stale-cache fallback
    is not silent in production.
    """

    if offline:
        return cse_source.fetch_all_financial_metadata(
            securities, cache_dir, workers=workers, offline=True
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    representatives = cse_source.issuer_representatives(securities)
    results: dict[str, list[Filing]] = {}
    failures: list[str] = []

    def fetch_one(item: tuple[str, Security]) -> tuple[str, list[Filing]]:
        company_name, security = item
        filings, payload = cse_source.fetch_financials(security.symbol, company_name)
        cache_path = cache_dir / f"{security.security_id}_{security.symbol.replace('.', '_')}.json"
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(cache_path)
        return company_name, filings

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch_one, item): item[0] for item in representatives.items()}
        for future in as_completed(futures):
            company_name = futures[future]
            try:
                issuer_name, filings = future.result()
                results[issuer_name] = filings
            except Exception as exc:  # strict production boundary
                failures.append(f"{company_name}: {type(exc).__name__}: {exc}")

    if failures:
        evidence = cache_dir / "PRODUCTION_METADATA_FAILURES.json"
        evidence.write_text(json.dumps(sorted(failures), indent=2), encoding="utf-8")
        raise RuntimeError(
            f"Fresh CSE filing metadata failed for {len(failures)} issuer(s); "
            f"stale fallback is forbidden in production. See {evidence}."
        )
    return results


def _fetch_pdf_bytes(filing: Filing, *, timeout: int, max_file_bytes: int) -> bytes:
    request = urllib.request.Request(
        filing.source_url, headers={"User-Agent": cse_source.USER_AGENT}
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                payload = response.read(max_file_bytes + 1)
            if len(payload) > max_file_bytes:
                raise ValueError(
                    f"Filing exceeds max size {max_file_bytes} bytes ({len(payload)}+ bytes)"
                )
            if not payload.startswith(b"%PDF") and "pdf" not in content_type.lower():
                raise ValueError(f"Unexpected content type {content_type!r}")
            return payload
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep((2**attempt) + random.uniform(0.0, 0.25))
    raise RuntimeError(f"Download failed for {filing.source_url}: {last_error}")


def revision_safe_download_filing(
    filing: Filing,
    destination_root: Path,
    timeout: int = 180,
    *,
    max_file_bytes: int = 50 * 1024 * 1024,
    offline: bool = False,
) -> DownloadedFiling:
    """Persist immutable, content-addressed filing versions.

    Online execution always verifies the current remote bytes.  If CSE replaces or
    amends a filing, the new SHA gets a new file instead of silently reusing the old
    period/basename cache.  Offline replay follows the last verified pointer.
    """

    issuer_dir = destination_root / cse_source.safe_slug(filing.issuer_name)
    issuer_dir.mkdir(parents=True, exist_ok=True)
    pointer = issuer_dir / f"{filing.period_end.isoformat()}_{filing.filing_id}.current.json"

    if offline:
        candidates: list[Path] = []
        if pointer.exists():
            try:
                payload = json.loads(pointer.read_text(encoding="utf-8"))
                name = str(payload.get("filename") or "")
                if name:
                    candidates.append(issuer_dir / name)
            except (OSError, json.JSONDecodeError):
                pass
        candidates.extend(
            sorted(issuer_dir.glob(f"{filing.period_end.isoformat()}_{filing.filing_id}_*.pdf"))
        )
        legacy = issuer_dir / f"{filing.period_end.isoformat()}_{Path(filing.source_path).name}"
        candidates.append(legacy)
        destination = next((path for path in candidates if path.is_file() and path.stat().st_size), None)
        if destination is None:
            raise FileNotFoundError(
                f"Offline filing cache not found for filing_id={filing.filing_id}: {issuer_dir}"
            )
        payload = destination.read_bytes()
    else:
        payload = _fetch_pdf_bytes(
            filing, timeout=timeout, max_file_bytes=max_file_bytes
        )
        digest = hashlib.sha256(payload).hexdigest()
        destination = issuer_dir / (
            f"{filing.period_end.isoformat()}_{filing.filing_id}_{digest[:16]}.pdf"
        )
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_bytes(payload)
            temporary.replace(destination)
        pointer_payload = {
            "filing_id": filing.filing_id,
            "issuer_name": filing.issuer_name,
            "symbol": filing.symbol,
            "period_end": filing.period_end.isoformat(),
            "source_url": filing.source_url,
            "source_path": filing.source_path,
            "uploaded_at": filing.uploaded_at.isoformat() if filing.uploaded_at else None,
            "authorized_at": filing.authorized_at.isoformat() if filing.authorized_at else None,
            "sha256": digest,
            "filename": destination.name,
            "verified_at": datetime.now(UTC).isoformat(),
        }
        temporary_pointer = pointer.with_suffix(pointer.suffix + ".tmp")
        temporary_pointer.write_text(json.dumps(pointer_payload, indent=2), encoding="utf-8")
        temporary_pointer.replace(pointer)

    if len(payload) > max_file_bytes:
        raise RuntimeError(f"Cached filing exceeds max size {max_file_bytes} bytes: {destination}")
    digest = hashlib.sha256(payload).hexdigest()
    return DownloadedFiling(
        filing=filing,
        local_path=destination,
        sha256=digest,
        size_bytes=len(payload),
    )


def _parse_observation_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _file_observation_date(path: Path) -> date | None:
    if path.parent.name.startswith("date="):
        return _parse_observation_date(path.parent.name.removeprefix("date="))
    for prefix in ("historical_", "market_cap_"):
        if path.stem.startswith(prefix):
            parsed = _parse_observation_date(path.stem.removeprefix(prefix))
            if parsed is not None:
                return parsed
    return None


def _historical_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "data", "prices", "history"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _row_price(row: dict[str, Any]) -> Decimal | None:
    for key in ("price", "trade_price", "closing_price", "close"):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            value = Decimal(str(raw).replace(",", ""))
        except (InvalidOperation, ValueError):
            continue
        if value > 0:
            return value
    return None


def strict_resolve_quarter_end_price(
    project_root: Path, symbol: str, period_end: date
) -> tuple[Decimal, date, str] | None:
    """Resolve only from explicit historical CSE data, never a live market snapshot."""

    official_dir = project_root / "data" / "raw" / "market" / "historical_prices"
    if not official_dir.exists():
        return None
    candidates: list[tuple[date, Decimal]] = []
    for path in official_dir.rglob("*.json"):
        file_date = _file_observation_date(path)
        for row in _historical_rows(path):
            if str(row.get("symbol") or "").strip().upper() != symbol.strip().upper():
                continue
            observed = (
                _parse_observation_date(row.get("trade_date"))
                or _parse_observation_date(row.get("date"))
                or _parse_observation_date(row.get("observation_date"))
                or file_date
            )
            if observed is None or observed > period_end:
                continue
            value = _row_price(row)
            if value is not None:
                candidates.append((observed, value))
    if not candidates:
        return None
    observed, value = max(candidates, key=lambda item: item[0])
    return value, observed, "CSE_HISTORICAL"


def assert_production_as_of(as_of_date: date, *, offline: bool) -> None:
    """A live snapshot may only be labelled with the real Colombo observation date."""

    if offline:
        return
    today = datetime.now(COLOMBO).date()
    if as_of_date != today:
        raise ValueError(
            f"Online production run requested as_of={as_of_date.isoformat()} but the live "
            f"CSE observation date in Asia/Colombo is {today.isoformat()}. Historical "
            "backfills must use explicit offline/historical inputs."
        )


def _block_legacy_corrections(repository: Repository) -> None:
    path = repository.root / "curated" / "manual_corrections.parquet"
    if not path.exists():
        return
    try:
        frame = pl.read_parquet(path)
    except Exception as exc:
        raise RuntimeError(f"Cannot verify legacy corrections file {path}: {exc}") from exc
    if not frame.is_empty():
        raise RuntimeError(
            "Unsigned manual_corrections.parquet is disabled in production. Correct the "
            "source/extraction contract and rerun, or use the governed source-bound "
            "review process; production will not convert an unsigned override into CURATED/PASSED."
        )


def build_issuer_master(project_root: Path, as_of_date: date) -> Path:
    """Write the versioned issuer classification actually used for this universe."""

    market_path = project_root / "data" / "raw" / "api" / f"market_cap_{as_of_date.isoformat()}.json"
    rows = json.loads(market_path.read_text(encoding="utf-8")) if market_path.exists() else []
    rows = rows if isinstance(rows, list) else []
    configured = load_issuers(project_root)
    symbols: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("company_name") or row.get("name") or "").strip()
        symbol = str(row.get("symbol") or "").strip()
        if name and symbol and symbol not in symbols[name]:
            symbols[name].append(symbol)

    master: list[dict[str, Any]] = []
    for name in sorted(symbols):
        profile = configured.get(name.casefold())
        master.append(
            {
                "legal_name": name,
                "symbols": sorted(symbols[name]),
                "issuer_type": profile.issuer_type if profile else infer_issuer_type(name),
                "standalone_scope_label": (
                    profile.standalone_scope_label
                    if profile
                    else "BANK"
                    if infer_issuer_type(name) == "BANK"
                    else "COMPANY"
                ),
                "classification_source": "CONFIGURED" if profile else "DETERMINISTIC_INFERENCE",
                "as_of_date": as_of_date.isoformat(),
            }
        )
    destination = project_root / "outputs" / f"issuer_master_{as_of_date.isoformat()}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(master, indent=2), encoding="utf-8")
    return destination


def write_metric_definitions(project_root: Path, as_of_date: date) -> Path:
    """Make the legacy leverage code's accounting meaning explicit for consumers."""

    payload = {
        "DEBT_TO_EQUITY": {
            "display_name": "Liabilities / Equity",
            "formula": "TOTAL_LIABILITIES / TOTAL_EQUITY",
            "semantic_note": (
                "Legacy internal metric code. This is total-liabilities-to-equity, not "
                "interest-bearing corporate debt-to-equity and not the Basel bank leverage ratio."
            ),
        }
    }
    destination = project_root / "outputs" / f"metric_definitions_{as_of_date.isoformat()}.json"
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def relabel_workbook_leverage(path: Path) -> None:
    if not path.exists():
        return
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    changed = False
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.value == "Debt / Equity":
                    cell.value = "Liabilities / Equity"
                    changed = True
    if changed:
        workbook.save(path)


@contextmanager
def production_runtime(
    project_root: Path, *, as_of_date: date, offline: bool
) -> Iterator[ProductionRunCapture]:
    """Patch only the production process, leaving the stable ETL core unchanged."""

    root = project_root.resolve()
    assert_production_as_of(as_of_date, offline=offline)
    requests_per_second, timeout_seconds, max_retries = _production_http_settings(root)
    capture = ProductionRunCapture()

    original_post = cse_source._post
    original_metadata = pipeline_module.fetch_all_financial_metadata
    original_download = pipeline_module.download_filing
    original_price_resolver = pipeline_module.resolve_quarter_end_price
    original_finish_run = Repository.finish_run
    original_apply_corrections = Repository._apply_curated_corrections

    cse_source._post = _make_rate_limited_post(
        requests_per_second=requests_per_second,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    pipeline_module.fetch_all_financial_metadata = _strict_financial_metadata
    pipeline_module.download_filing = revision_safe_download_filing
    pipeline_module.resolve_quarter_end_price = strict_resolve_quarter_end_price

    def blocked_corrections(self: Repository) -> None:
        _block_legacy_corrections(self)

    def stage_only_finish(
        self: Repository, run_id: str, status: str, statistics: dict[str, Any]
    ) -> None:
        if run_id != self.run_id:
            raise ValueError("Attempted to finish a different run")
        staging = self._write_staging(status, statistics)
        capture.repository = self
        capture.staging = staging
        capture.status = status
        capture.statistics = dict(statistics)

    Repository._apply_curated_corrections = blocked_corrections
    Repository.finish_run = stage_only_finish
    try:
        yield capture
    finally:
        cse_source._post = original_post
        pipeline_module.fetch_all_financial_metadata = original_metadata
        pipeline_module.download_filing = original_download
        pipeline_module.resolve_quarter_end_price = original_price_resolver
        Repository.finish_run = original_finish_run
        Repository._apply_curated_corrections = original_apply_corrections


def promote_staged_run(
    capture: ProductionRunCapture,
    acceptance: dict[str, Any],
    *,
    release_mode: str,
) -> dict[str, Any]:
    """Move CURRENT only after universe acceptance has succeeded.

    DRAFT may activate after engineering acceptance while independent proof is still
    pending. OFFICIAL requires both engineering acceptance and completion of all
    external proof gates.
    """

    if not capture.ready:
        return {"promoted": False, "reason": "NO_STAGED_RUN"}
    status = str(acceptance.get("acceptance") or "")
    if status == "ENGINEERING_FAILURES_PRESENT":
        return {"promoted": False, "reason": "ENGINEERING_FAILURES_PRESENT"}
    mode = release_mode.strip().upper()
    proof_gates = list(acceptance.get("external_proof_gates") or [])
    if mode == "OFFICIAL" and proof_gates:
        return {"promoted": False, "reason": "OFFICIAL_EXTERNAL_PROOF_PENDING"}
    if mode not in {"DRAFT", "OFFICIAL"}:
        return {"promoted": False, "reason": f"UNKNOWN_RELEASE_MODE:{mode}"}

    assert capture.repository is not None
    assert capture.staging is not None
    capture.repository._promote(capture.staging)
    return {
        "promoted": True,
        "reason": (
            "DRAFT_ENGINEERING_ACCEPTED"
            if mode == "DRAFT" and proof_gates
            else f"{mode}_ACCEPTED"
        ),
        "run_id": capture.repository.run_id,
    }
