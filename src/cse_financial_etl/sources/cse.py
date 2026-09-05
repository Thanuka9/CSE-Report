from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

API_BASE = "https://www.cse.lk/api"
CDN_BASE = "https://cdn.cse.lk/"
USER_AGENT = "CSE-Financial-Data-Platform/1.0 (+public regulatory research)"
HTTP_TIMEOUT_SECONDS = 30
HTTP_MAX_RETRIES = 3


def configure_http(*, timeout_seconds: int, max_retries: int) -> None:
    global HTTP_TIMEOUT_SECONDS, HTTP_MAX_RETRIES
    HTTP_TIMEOUT_SECONDS = max(1, timeout_seconds)
    HTTP_MAX_RETRIES = max(1, max_retries)


@dataclass(frozen=True, slots=True)
class Security:
    security_id: int
    company_name: str
    symbol: str
    price: float | None
    issued_quantity: int | None
    market_capitalization: float | None
    market_cap_percentage: float | None
    logo_path: str | None


@dataclass(frozen=True, slots=True)
class Filing:
    issuer_name: str
    symbol: str
    filing_id: int
    period_end: date
    title: str
    source_path: str
    source_url: str
    uploaded_at: datetime | None
    authorized_at: datetime | None


@dataclass(frozen=True, slots=True)
class DownloadedFiling:
    filing: Filing
    local_path: Path
    sha256: str
    size_bytes: int


def _millis_to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _post(endpoint: str, data: bytes, content_type: str, timeout: int | None = None) -> Any:
    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Accept-Language": "en",
            "Content-Type": content_type,
            "User-Agent": USER_AGENT,
        },
    )
    last_error: Exception | None = None
    attempts = HTTP_MAX_RETRIES
    request_timeout = HTTP_TIMEOUT_SECONDS if timeout is None else timeout
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"CSE request failed for {endpoint}: {last_error}")


def fetch_market_capitalization() -> list[Security]:
    payload = _post("list_by_market_cap", b"{}", "application/json")
    rows = payload.get("reqByMarketcap") or []
    return [
        Security(
            security_id=int(row["id"]),
            company_name=str(row["name"]).strip(),
            symbol=str(row["symbol"]).strip(),
            price=float(row["price"]) if row.get("price") is not None else None,
            issued_quantity=int(row["issuedQTY"]) if row.get("issuedQTY") is not None else None,
            market_capitalization=(
                float(row["marketCap"]) if row.get("marketCap") is not None else None
            ),
            market_cap_percentage=(
                float(row["marketCapPercentage"])
                if row.get("marketCapPercentage") is not None
                else None
            ),
            logo_path=row.get("logoUrl"),
        )
        for row in rows
    ]


def load_market_capitalization_cache(cache_path: Path) -> list[Security]:
    rows = json.loads(cache_path.read_text(encoding="utf-8"))
    return [
        Security(
            security_id=int(row["security_id"]),
            company_name=str(row["company_name"]),
            symbol=str(row["symbol"]),
            price=float(row["price"]) if row.get("price") is not None else None,
            issued_quantity=(
                int(row["issued_quantity"]) if row.get("issued_quantity") is not None else None
            ),
            market_capitalization=(
                float(row["market_capitalization"])
                if row.get("market_capitalization") is not None
                else None
            ),
            market_cap_percentage=(
                float(row["market_cap_percentage"])
                if row.get("market_cap_percentage") is not None
                else None
            ),
            logo_path=row.get("logo_path"),
        )
        for row in rows
    ]


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_period_end(title: str) -> date | None:
    match = re.search(
        r"(?:ended|as\s*@|as\s+at|at)\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{4})",
        title,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))


def _cdn_url(path: str) -> str:
    if path.startswith(("https://", "http://")):
        parsed = urllib.parse.urlsplit(path)
        return urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                urllib.parse.quote(parsed.path, safe="/%:@"),
                parsed.query,
                parsed.fragment,
            )
        )
    encoded_path = urllib.parse.quote(path.lstrip("/"), safe="/%:@")
    return urllib.parse.urljoin(CDN_BASE, encoded_path)


def fetch_financials(symbol: str, issuer_name: str) -> tuple[list[Filing], dict[str, Any]]:
    encoded = urllib.parse.urlencode({"symbol": symbol}).encode("ascii")
    payload = _post("financials", encoded, "application/x-www-form-urlencoded")
    filings: list[Filing] = []
    for row in payload.get("infoQuarterlyData") or []:
        title = str(row.get("fileText") or "").strip()
        period_end = parse_period_end(title)
        source_path = str(row.get("path") or "").strip()
        if not period_end or not source_path.lower().endswith(".pdf"):
            continue
        filings.append(
            Filing(
                issuer_name=issuer_name,
                symbol=symbol,
                filing_id=int(row.get("id") or 0),
                period_end=period_end,
                title=title,
                source_path=source_path,
                source_url=_cdn_url(source_path),
                uploaded_at=_millis_to_datetime(row.get("uploadedDate")),
                authorized_at=_millis_to_datetime(row.get("authorizedDate")),
            )
        )
    return filings, payload


def issuer_representatives(securities: Iterable[Security]) -> dict[str, Security]:
    representatives: dict[str, Security] = {}
    for security in securities:
        current = representatives.get(security.company_name)
        if current is None or (current.price in (None, 0) and security.price not in (None, 0)):
            representatives[security.company_name] = security
    return representatives


def fetch_all_financial_metadata(
    securities: Iterable[Security],
    cache_dir: Path,
    *,
    workers: int = 24,
    offline: bool = False,
) -> dict[str, list[Filing]]:
    """Fetch fresh metadata online; use cache only as fallback or in offline mode."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    representatives = issuer_representatives(securities)
    results: dict[str, list[Filing]] = {}

    def from_payload(payload: dict[str, Any], company_name: str, security: Security) -> list[Filing]:
        filings: list[Filing] = []
        for row in payload.get("infoQuarterlyData") or []:
            title = str(row.get("fileText") or "").strip()
            period_end = parse_period_end(title)
            source_path = str(row.get("path") or "").strip()
            if period_end and source_path.lower().endswith(".pdf"):
                filings.append(
                    Filing(
                        issuer_name=company_name,
                        symbol=security.symbol,
                        filing_id=int(row.get("id") or 0),
                        period_end=period_end,
                        title=title,
                        source_path=source_path,
                        source_url=_cdn_url(source_path),
                        uploaded_at=_millis_to_datetime(row.get("uploadedDate")),
                        authorized_at=_millis_to_datetime(row.get("authorizedDate")),
                    )
                )
        return filings

    def fetch_one(item: tuple[str, Security]) -> tuple[str, list[Filing]]:
        company_name, security = item
        cache_path = cache_dir / f"{security.security_id}_{security.symbol.replace('.', '_')}.json"
        if offline:
            if not cache_path.exists():
                return company_name, []
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return company_name, from_payload(payload, company_name, security)
        try:
            filings, payload = fetch_financials(security.symbol, company_name)
            cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return company_name, filings
        except Exception:
            if cache_path.exists():
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                return company_name, from_payload(payload, company_name, security)
            raise

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_one, item): item[0] for item in representatives.items()}
        for future in as_completed(futures):
            company_name = futures[future]
            try:
                issuer_name, filings = future.result()
                results[issuer_name] = filings
            except Exception as exc:
                results[company_name] = []
                (cache_dir / f"ERROR_{re.sub(r'[^A-Za-z0-9]+', '_', company_name)}.txt").write_text(
                    str(exc), encoding="utf-8"
                )
    return results

def choose_filing(filings: Iterable[Filing], period_end: date) -> Filing | None:
    matches = [filing for filing in filings if filing.period_end == period_end]
    if not matches:
        return None
    return max(
        matches,
        key=lambda filing: (
            filing.authorized_at or datetime.min.replace(tzinfo=UTC),
            filing.uploaded_at or datetime.min.replace(tzinfo=UTC),
            filing.filing_id,
        ),
    )


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:80]


def download_filing(
    filing: Filing,
    destination_root: Path,
    timeout: int = 180,
    *,
    max_file_bytes: int = 50 * 1024 * 1024,
    offline: bool = False,
) -> DownloadedFiling:
    issuer_dir = destination_root / safe_slug(filing.issuer_name)
    issuer_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{filing.period_end.isoformat()}_{Path(filing.source_path).name}"
    destination = issuer_dir / filename
    if not destination.exists() or destination.stat().st_size == 0:
        if offline:
            raise FileNotFoundError(f"Offline filing cache not found: {destination}")
        request = urllib.request.Request(filing.source_url, headers={"User-Agent": USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    content_type = response.headers.get("Content-Type", "")
                    payload = response.read()
                if len(payload) > max_file_bytes:
                    raise ValueError(
                        f"Filing exceeds max size {max_file_bytes} bytes ({len(payload)} bytes)"
                    )
                if not payload.startswith(b"%PDF") and "pdf" not in content_type.lower():
                    raise ValueError(f"Unexpected content type {content_type!r}")
                destination.write_bytes(payload)
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt == 3:
                    raise RuntimeError(
                        f"Download failed for {filing.source_url}: {last_error}"
                    ) from exc
                time.sleep(2**attempt)
    if destination.stat().st_size > max_file_bytes:
        raise RuntimeError(f"Cached filing exceeds max size {max_file_bytes} bytes: {destination}")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return DownloadedFiling(
        filing=filing,
        local_path=destination,
        sha256=digest,
        size_bytes=destination.stat().st_size,
    )


def serialize_security(security: Security) -> dict[str, Any]:
    return asdict(security)
