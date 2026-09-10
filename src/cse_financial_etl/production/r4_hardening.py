"""R4 regulatory and semantic hardening for the file-backed CSE production pipeline.

This layer deliberately keeps the existing no-database / no-XBRL architecture.  It adds
governed master-data, disclosure-calendar, accounting-regime and price semantics around
the proven extractor, and fails closed when an extracted row violates those contracts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import polars as pl

import cse_financial_etl.extraction.statement_extractor as statement_extractor
import cse_financial_etl.orchestration.pipeline as pipeline_module
import cse_financial_etl.sources.cse as cse_source
from cse_financial_etl.config import (
    infer_entity_scope,
    infer_issuer_type,
    issuer_profile_for_name,
    load_issuers,
    load_yaml,
)
from cse_financial_etl.documents.pdf_text import PdfPage, extract_layout_pages
from cse_financial_etl.extraction.statement_extractor import ExtractedFact, QuarterPrice
from cse_financial_etl.sources.cse import Security
from cse_financial_etl.storage.repository import Repository

PUBLISHABLE = {"EXTRACTED", "EXTRACTED_DERIVED"}
BASE_FLOW_METRICS = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "EPS_SELECTED",
}
Q4_REPORTED_ONLY_METRICS = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "EPS_BASIC",
    "EPS_DILUTED",
}
RATIO_DEFINITIONS = {
    "DEBT_TO_EQUITY": {
        "canonical_code": "LIABILITIES_TO_EQUITY",
        "display_name": "Liabilities / Equity",
        "formula": "Total liabilities / Total equity",
        "note": "Legacy internal code retained for backward compatibility; not corporate interest-bearing debt/equity or a Basel leverage ratio.",
    },
    "ROE": {
        "canonical_code": "ROE",
        "display_name": "ROE",
        "formula": "Same-quarter PAT / quarter-end total equity",
        "note": "Project analytic ratio; not annualised and does not use average equity.",
    },
    "ROA": {
        "canonical_code": "ROA",
        "display_name": "ROA",
        "formula": "Same-quarter PAT / quarter-end total assets",
        "note": "Project analytic ratio; not annualised and does not use average assets.",
    },
    "NPM": {
        "canonical_code": "NPM",
        "display_name": "NPM",
        "formula": "Same-quarter PAT / same-quarter top line",
        "note": "Top-line basis is sector/regime-specific and is emitted in fact semantics.",
    },
}

_LONG_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_LONG_MONTHS, key=len, reverse=True))


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def parse_period_end_strict(title: str) -> date | None:
    """Parse real CSE filing-title date variants without assuming US numeric dates."""

    text = " ".join(str(title).replace("\u00a0", " ").split())
    patterns = (
        re.compile(
            rf"(?:ended|ending|as\s*@|as\s+at|as\s+of|at|to)\s+"
            rf"(\d{{1,2}})(?:st|nd|rd|th)?[\s,./-]+({_MONTH_ALT})\.?[\s,./-]+"
            r"((?:19|20)\d{2})",
            re.I,
        ),
        re.compile(
            rf"(?:ended|ending|as\s*@|as\s+at|as\s+of|at|to)\s+"
            rf"({_MONTH_ALT})\.?[\s,./-]+(\d{{1,2}})(?:st|nd|rd|th)?[\s,./-]+"
            r"((?:19|20)\d{2})",
            re.I,
        ),
    )
    first = patterns[0].search(text)
    if first:
        return _safe_date(int(first.group(3)), _LONG_MONTHS[first.group(2).lower()], int(first.group(1)))
    second = patterns[1].search(text)
    if second:
        return _safe_date(int(second.group(3)), _LONG_MONTHS[second.group(1).lower()], int(second.group(2)))

    iso = re.search(
        r"(?:ended|ending|as\s*@|as\s+at|as\s+of|at|to)?\s*"
        r"((?:19|20)\d{2})[./-](\d{1,2})[./-](\d{1,2})\b",
        text,
        re.I,
    )
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    # Sri Lankan numeric convention is day/month/year.  Do not reinterpret it as US mm/dd.
    dmy = re.search(
        r"(?:ended|ending|as\s*@|as\s+at|as\s+of|at|to)?\s*"
        r"(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d{2})\b",
        text,
        re.I,
    )
    if dmy:
        return _safe_date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _schema_fingerprint(rows: list[dict[str, Any]]) -> str:
    shape = sorted(
        {
            (str(key), type(value).__name__)
            for row in rows
            for key, value in row.items()
            if key
        }
    )
    return hashlib.sha256(json.dumps(shape, separators=(",", ":")).encode("utf-8")).hexdigest()


def _exact_market_fetcher(project_root: Path, as_of: date) -> Callable[[], list[Security]]:
    """Return a fetcher that archives exact CSE response values and a schema fingerprint."""

    def fetch() -> list[Security]:
        payload = cse_source._post("list_by_market_cap", b"{}", "application/json")
        rows = payload.get("reqByMarketcap") or []
        if not isinstance(rows, list):
            raise RuntimeError("CSE list_by_market_cap response does not contain a row list")

        raw_dir = project_root / "data" / "raw" / "api" / "contracts"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"list_by_market_cap_{as_of.isoformat()}.json"
        raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        outputs = project_root / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        contract = {
            "endpoint": "list_by_market_cap",
            "as_of": as_of.isoformat(),
            "row_count": len(rows),
            "schema_fingerprint": _schema_fingerprint(
                [row for row in rows if isinstance(row, dict)]
            ),
            "observed_fields": sorted(
                {str(key) for row in rows if isinstance(row, dict) for key in row}
            ),
            "raw_evidence_path": str(raw_path),
            "numeric_policy": "raw JSON preserved exactly; runtime compatibility conversion happens only after archival",
        }
        (outputs / f"cse_api_contract_{as_of.isoformat()}.json").write_text(
            json.dumps(contract, indent=2), encoding="utf-8"
        )

        result: list[Security] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            result.append(
                Security(
                    security_id=int(raw["id"]),
                    company_name=str(raw["name"]).strip(),
                    symbol=str(raw["symbol"]).strip(),
                    price=float(raw["price"]) if raw.get("price") is not None else None,
                    issued_quantity=(
                        int(raw["issuedQTY"]) if raw.get("issuedQTY") is not None else None
                    ),
                    market_capitalization=(
                        float(raw["marketCap"]) if raw.get("marketCap") is not None else None
                    ),
                    market_cap_percentage=(
                        float(raw["marketCapPercentage"])
                        if raw.get("marketCapPercentage") is not None
                        else None
                    ),
                    logo_path=raw.get("logoUrl"),
                )
            )
        return result

    return fetch


def _historical_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "history", "trades"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _row_trade_date(row: dict[str, Any], fallback: date | None) -> date | None:
    for key in ("trade_date", "tradeDate", "date", "traded_date", "tradedDate"):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        text = str(raw)[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            parsed = parse_period_end_strict(f"at {raw}")
            if parsed:
                return parsed
    return fallback


def _file_observation_date(path: Path) -> date | None:
    match = re.search(r"((?:19|20)\d{2}-\d{2}-\d{2})", path.name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _last_traded_value(row: dict[str, Any]) -> Decimal | None:
    """Require trade/last-traded semantics; a generic close is never sufficient."""

    for key in ("last_traded_price", "lastTradedPrice", "last_trade_price", "trade_price"):
        value = _decimal(row.get(key))
        if value is not None and value > 0:
            return value

    price_type = str(
        row.get("price_type")
        or row.get("priceType")
        or row.get("observation_type")
        or ""
    ).strip().upper().replace("-", "_").replace(" ", "_")
    if price_type in {"LAST_TRADED", "LAST_TRADE", "TRADE", "TRADED"}:
        value = _decimal(row.get("price"))
        if value is not None and value > 0:
            return value

    # Some official trade-history payloads use a plain `price` but carry a trade date.
    # That is still trade evidence; `closing_price` / `close` are intentionally rejected.
    if any(row.get(key) not in (None, "") for key in ("trade_date", "tradeDate", "traded_date", "tradedDate")):
        value = _decimal(row.get("price"))
        if value is not None and value > 0:
            return value
    return None


def strict_last_traded_history(
    project_root: Path, symbol: str, period_end: date
) -> tuple[Decimal, date, str] | None:
    """Resolve only official trade/last-traded evidence on or before the target date."""

    official = project_root / "data" / "raw" / "market" / "historical_prices"
    if not official.exists():
        return None
    candidates: list[tuple[date, Decimal]] = []
    for path in sorted(official.glob("*.json")):
        fallback_date = _file_observation_date(path)
        for row in _historical_rows(path):
            if str(row.get("symbol") or "").strip().upper() != symbol.strip().upper():
                continue
            trade_date = _row_trade_date(row, fallback_date)
            if trade_date is None or trade_date > period_end:
                continue
            value = _last_traded_value(row)
            if value is not None:
                candidates.append((trade_date, value))
    if not candidates:
        return None
    trade_date, value = max(candidates, key=lambda item: item[0])
    return value, trade_date, "CSE_LAST_TRADED_HISTORY"


def _context_for_price(
    pdf_path: Path, source_page: int | None, source_line: str | None, cache: Path | None
) -> str:
    if source_page is None or not source_line:
        return ""
    try:
        pages = extract_layout_pages(pdf_path, cache)
    except Exception:
        return source_line
    target = " ".join(source_line.split()).casefold()
    for page in pages:
        if page.number != source_page:
            continue
        lines = [line for line in page.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if " ".join(line.split()).casefold() == target:
                return " ".join(lines[max(0, index - 10) : index + 3])
        return page.text
    return source_line


def _strict_price_extractor(
    original: Callable[..., list[QuarterPrice]],
) -> Callable[..., list[QuarterPrice]]:
    def wrapped(
        pdf_path: Path,
        issuer_name: str,
        symbols: Iterable[str],
        period_end: date,
        text_cache_dir: Path | None = None,
    ) -> list[QuarterPrice]:
        prices = original(pdf_path, issuer_name, symbols, period_end, text_cache_dir)
        result: list[QuarterPrice] = []
        for price in prices:
            if price.status != "EXTRACTED" or price.value is None:
                result.append(price)
                continue
            context = _context_for_price(
                pdf_path, price.source_page, price.source_line, text_cache_dir
            ).casefold()
            last_traded = bool(
                re.search(r"\blast\s+trad(?:e|ed|ing)(?:\s+(?:market\s+)?price)?\b", context)
            )
            explicit_close = bool(
                re.search(r"\bclosing\s+(?:share\s+|market\s+)?price\b|\bclosing\s+price\b", context)
            )
            if last_traded:
                result.append(
                    replace(
                        price,
                        source_method="FILING_LAST_TRADED",
                        validation_status="PASSED",
                    )
                )
            elif explicit_close:
                result.append(
                    replace(
                        price,
                        value=None,
                        source_method="FILING_CLOSING_PRICE_REJECTED",
                        confidence="NONE",
                        confidence_score=0.0,
                        certainty_band="NONE",
                        status="PRICE_SEMANTIC_MISMATCH",
                        validation_status="REVIEW",
                    )
                )
            else:
                # Ambiguous "market price" rows are not proof of the CSE last-traded field.
                result.append(
                    replace(
                        price,
                        value=None,
                        source_method="FILING_PRICE_SEMANTIC_UNVERIFIED",
                        confidence="NONE",
                        confidence_score=0.0,
                        certainty_band="NONE",
                        status="PRICE_SEMANTIC_UNVERIFIED",
                        validation_status="REVIEW",
                    )
                )
        return result

    return wrapped


def _statement_unit_from_page(page: PdfPage) -> tuple[str | None, int | None, str | None]:
    try:
        return statement_extractor._statement_unit(page)
    except Exception:
        return None, None, None


def _bank_nil_recover(
    facts: list[ExtractedFact],
    pdf_path: Path,
    period_end: date,
    text_cache_dir: Path | None,
) -> list[ExtractedFact]:
    """Recover an explicit CBSL-style `nil` only on a verified 3M Bank statement.

    A generic dash/blank is never zero.  We also do not recover nil on 6M/9M/YTD pages.
    """

    try:
        pages = extract_layout_pages(pdf_path, text_cache_dir)
    except Exception:
        return facts
    aliases: dict[str, tuple[re.Pattern[str], ...]] = {
        "TOP_LINE": (
            re.compile(r"^\s*gross\s+income\b", re.I),
            re.compile(r"^\s*total\s+operating\s+income\b", re.I),
        ),
        "OPERATING_PROFIT": (
            re.compile(
                r"^\s*operating\s+profit\s+before\s+tax(?:es|ation)?\s+on\s+financial\s+services\b",
                re.I,
            ),
        ),
        "PBT": (re.compile(r"^\s*profit\s+before\s+(?:income\s+)?tax", re.I),),
        "PAT": (re.compile(r"^\s*profit\s+for\s+the\s+(?:period|quarter)", re.I),),
    }
    by_code = {fact.metric_code: fact for fact in facts}
    replacements: dict[str, ExtractedFact] = {}
    for page in pages:
        header = page.text.upper()
        if "BANK" not in header:
            continue
        if not statement_extractor._is_exact_quarter_text(page.text):
            continue
        if re.search(r"\b(?:SIX|NINE|TWELVE|0?6|0?9|12)\s+MONTHS?\b", header) and not re.search(
            r"\b(?:THREE|03|3)\s+MONTHS?\b|\bQUARTER\s+(?:ENDED|TO)\b", header
        ):
            continue
        currency, scale, unit_text = _statement_unit_from_page(page)
        if currency is None or scale is None:
            continue
        for line in page.text.splitlines():
            if not re.search(r"\bnil\b", line, re.I):
                continue
            # Multiple numeric values would make current/comparative binding ambiguous.
            numeric = [
                token
                for token in re.findall(r"(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?\)?", line)
                if not re.fullmatch(r"(?:19|20)\d{2}", token.strip("()"))
            ]
            if numeric:
                continue
            for code, patterns in aliases.items():
                existing = by_code.get(code)
                if existing is None or existing.status in PUBLISHABLE:
                    continue
                if not any(pattern.search(line) for pattern in patterns):
                    continue
                replacements[code] = replace(
                    existing,
                    raw_text="nil",
                    raw_value=Decimal("0"),
                    normalized_value=Decimal("0"),
                    currency=currency,
                    scale_factor=scale,
                    entity_scope="BANK",
                    source_page=page.number,
                    source_line=line.strip(),
                    unit_source_text=unit_text,
                    confidence="HIGH",
                    status="EXTRACTED",
                    raw_label=line.strip(),
                    extraction_method="CBSL_EXPLICIT_NIL",
                    semantic_model="regulatory-template",
                    semantic_confidence=1.0,
                    entity_confidence=1.0,
                    period_confidence=1.0,
                    unit_confidence=1.0,
                    column_confidence=0.95,
                    validation_confidence=0.95,
                    overall_certainty=0.97,
                    certainty_band="HIGH",
                    comparison_role="CURRENT",
                    duration_months=3,
                    validation_status="PASSED",
                    review_status="REVIEW",
                    evidence_json=json.dumps(
                        {
                            "policy": "CBSL_EXPLICIT_NIL_ONLY",
                            "raw_token": "nil",
                            "blank_or_dash_is_zero": False,
                        },
                        separators=(",", ":"),
                    ),
                )
    return [replacements.get(fact.metric_code, fact) for fact in facts]


def _harden_extracted_facts(
    facts: list[ExtractedFact],
    *,
    issuer_name: str,
    pdf_path: Path,
    period_end: date,
    text_cache_dir: Path | None,
) -> list[ExtractedFact]:
    issuer_type = infer_issuer_type(issuer_name)
    if issuer_type == "BANK":
        facts = _bank_nil_recover(facts, pdf_path, period_end, text_cache_dir)

    result: list[ExtractedFact] = []
    for fact in facts:
        if fact.status not in PUBLISHABLE:
            result.append(fact)
            continue
        if fact.metric_code in BASE_FLOW_METRICS:
            if fact.duration_months != 3:
                result.append(
                    replace(
                        fact,
                        normalized_value=None,
                        status="NON_QUARTER_FLOW_WITHHELD",
                        validation_status="REVIEW",
                        review_status="REVIEW",
                        confidence="LOW",
                    )
                )
                continue
            if fact.metric_code in Q4_REPORTED_ONLY_METRICS and fact.status == "EXTRACTED_DERIVED":
                result.append(
                    replace(
                        fact,
                        normalized_value=None,
                        status="DERIVED_Q4_NOT_PUBLISHABLE",
                        validation_status="REVIEW",
                        review_status="REVIEW",
                        confidence="LOW",
                    )
                )
                continue
        if (
            issuer_type == "BANK"
            and fact.metric_code == "OPERATING_PROFIT"
            and fact.source_line
            and re.search(
                r"operating\s+profit.*\bafter\s+tax(?:es|ation)?\s+on\s+financial\s+services",
                fact.source_line,
                re.I,
            )
            and not re.search(r"\bbefore\s+tax", fact.source_line, re.I)
        ):
            result.append(
                replace(
                    fact,
                    normalized_value=None,
                    status="BANK_OPERATING_PROFIT_BASIS_MISMATCH",
                    validation_status="REVIEW",
                    review_status="REVIEW",
                    confidence="LOW",
                )
            )
            continue
        result.append(fact)
    return result


def _strict_fact_extractor(
    original: Callable[..., list[ExtractedFact]],
) -> Callable[..., list[ExtractedFact]]:
    def wrapped(
        pdf_path: Path,
        issuer_name: str,
        symbol: str,
        period_end: date,
        *args: Any,
        **kwargs: Any,
    ) -> list[ExtractedFact]:
        facts = original(pdf_path, issuer_name, symbol, period_end, *args, **kwargs)
        text_cache_dir = kwargs.get("text_cache_dir")
        if text_cache_dir is None and args:
            candidate_cache = args[0]
            if isinstance(candidate_cache, Path) or candidate_cache is None:
                text_cache_dir = candidate_cache
        return _harden_extracted_facts(
            facts,
            issuer_name=issuer_name,
            pdf_path=pdf_path,
            period_end=period_end,
            text_cache_dir=text_cache_dir,
        )

    return wrapped


@contextmanager
def r4_runtime_guards(project_root: Path, as_of: date) -> Iterator[None]:
    """Install guarded production callables without changing the extractor architecture."""

    original_market = pipeline_module.fetch_market_capitalization
    original_price = pipeline_module.extract_quarter_prices
    original_history = pipeline_module.resolve_quarter_end_price
    original_extract = pipeline_module.extract_filing
    original_parser = cse_source.parse_period_end
    pipeline_module.fetch_market_capitalization = _exact_market_fetcher(project_root, as_of)  # type: ignore[assignment]
    pipeline_module.extract_quarter_prices = _strict_price_extractor(original_price)  # type: ignore[assignment]
    pipeline_module.resolve_quarter_end_price = strict_last_traded_history
    pipeline_module.extract_filing = _strict_fact_extractor(original_extract)  # type: ignore[assignment]
    cse_source.parse_period_end = parse_period_end_strict
    try:
        yield
    finally:
        pipeline_module.fetch_market_capitalization = original_market  # type: ignore[assignment]
        pipeline_module.extract_quarter_prices = original_price  # type: ignore[assignment]
        pipeline_module.resolve_quarter_end_price = original_history
        pipeline_module.extract_filing = original_extract  # type: ignore[assignment]
        cse_source.parse_period_end = original_parser


def _load_policy(project_root: Path) -> dict[str, Any]:
    return load_yaml(project_root / "configs" / "regulatory_policy.yml")


def _raw_market_rows(project_root: Path, as_of: date) -> list[dict[str, Any]]:
    path = project_root / "data" / "raw" / "api" / "contracts" / f"list_by_market_cap_{as_of.isoformat()}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows = payload.get("reqByMarketcap") if isinstance(payload, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _board_from_raw(row: dict[str, Any]) -> str | None:
    for key in (
        "listingSegment",
        "listing_segment",
        "board",
        "boardName",
        "market",
        "marketType",
    ):
        value = str(row.get(key) or "").strip().upper()
        if not value:
            continue
        if "EMPOWER" in value:
            return "EMPOWER"
        if "MAIN" in value:
            return "MAIN"
        return value
    return None


def build_canonical_master(
    project_root: Path, as_of: date, repository: Repository
) -> tuple[Path, dict[str, Any]]:
    """Build a persistent issuer/security identity master without a database.

    Identity is anchored to CSE security IDs/symbol history, not mutable legal names.
    Existing IDs are retained across legal-name or symbol changes.
    """

    load_issuers(project_root)
    master_dir = project_root / "data" / "master"
    master_dir.mkdir(parents=True, exist_ok=True)
    persistent_path = master_dir / "issuer_security_master.json"
    previous: dict[str, Any] = {}
    if persistent_path.exists():
        try:
            parsed = json.loads(persistent_path.read_text(encoding="utf-8"))
            previous = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            previous = {}

    previous_issuers = [
        row for row in previous.get("issuers", []) if isinstance(row, dict)
    ]
    previous_securities = [
        row for row in previous.get("securities", []) if isinstance(row, dict)
    ]
    issuer_by_security_id: dict[int, str] = {}
    issuer_by_symbol: dict[str, str] = {}
    security_history_by_id: dict[int, dict[str, Any]] = {}
    for security in previous_securities:
        try:
            sid = int(security["security_id"])
        except (KeyError, TypeError, ValueError):
            continue
        security_history_by_id[sid] = security
        issuer_id = str(security.get("issuer_id") or "")
        if issuer_id:
            issuer_by_security_id[sid] = issuer_id
        for symbol in [security.get("symbol"), *(security.get("symbol_history") or [])]:
            if symbol:
                issuer_by_symbol[str(symbol).upper()] = issuer_id

    current_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in repository.market_rows:
        current_by_name.setdefault(str(row.get("company_name") or ""), []).append(row)

    raw_lookup: dict[int, dict[str, Any]] = {}
    for raw in _raw_market_rows(project_root, as_of):
        try:
            raw_lookup[int(raw["id"])] = raw
        except (KeyError, TypeError, ValueError):
            continue

    policy = _load_policy(project_root)
    segment_overrides = policy.get("issuer_listing_segments") or {}
    issuer_rows: list[dict[str, Any]] = []
    security_rows: list[dict[str, Any]] = []
    for legal_name, securities in sorted(current_by_name.items()):
        existing_ids = {
            issuer_by_security_id.get(int(row["security_id"]))
            or issuer_by_symbol.get(str(row["symbol"]).upper())
            for row in securities
        }
        existing_ids.discard(None)
        if len(existing_ids) == 1:
            issuer_id = str(next(iter(existing_ids)))
        else:
            anchor = min(int(row["security_id"]) for row in securities)
            issuer_id = f"CSE-ISSUER-{anchor}"

        configured = issuer_profile_for_name(legal_name)
        symbols = sorted(str(row["symbol"]) for row in securities)
        segment = None
        for symbol in symbols:
            override = segment_overrides.get(symbol) if isinstance(segment_overrides, dict) else None
            if override:
                segment = str(override).upper()
                break
        if segment is None and isinstance(segment_overrides, dict):
            override = segment_overrides.get(legal_name)
            if override:
                segment = str(override).upper()
        if segment is None:
            for row in securities:
                raw = raw_lookup.get(int(row["security_id"]), {})
                segment = _board_from_raw(raw)
                if segment:
                    break
        segment = segment or "UNKNOWN"

        issuer_rows.append(
            {
                "issuer_id": issuer_id,
                "legal_name": legal_name,
                "issuer_type": (
                    configured.issuer_type if configured is not None else infer_issuer_type(legal_name)
                ),
                "standalone_scope_label": (
                    configured.standalone_scope_label
                    if configured is not None
                    else infer_entity_scope(legal_name)
                ),
                "fiscal_year_end_month": (
                    configured.fiscal_year_end_month if configured is not None else None
                ),
                "listing_segment": segment,
                "symbols": symbols,
                "active_from": as_of.isoformat(),
                "active_to": None,
            }
        )
        for row in securities:
            sid = int(row["security_id"])
            symbol = str(row["symbol"])
            old = security_history_by_id.get(sid, {})
            history = [str(item) for item in old.get("symbol_history", []) if item]
            old_symbol = old.get("symbol")
            if old_symbol and str(old_symbol) != symbol and str(old_symbol) not in history:
                history.append(str(old_symbol))
            raw = raw_lookup.get(sid, {})
            security_rows.append(
                {
                    "security_id": sid,
                    "issuer_id": issuer_id,
                    "symbol": symbol,
                    "symbol_history": history,
                    "security_class": (
                        "NON_VOTING" if ".X" in symbol.upper() else "VOTING_OR_ORDINARY"
                    ),
                    "trading_currency": str(
                        raw.get("currency") or raw.get("tradingCurrency") or "LKR"
                    ).upper(),
                    "active_from": str(old.get("active_from") or as_of.isoformat()),
                    "active_to": None,
                }
            )

    current_ids = {row["issuer_id"] for row in issuer_rows}
    for old in previous_issuers:
        if old.get("issuer_id") not in current_ids:
            retired = dict(old)
            retired["active_to"] = retired.get("active_to") or as_of.isoformat()
            issuer_rows.append(retired)
    current_security_ids = {int(row["security_id"]) for row in security_rows}
    for old in previous_securities:
        try:
            sid = int(old["security_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if sid not in current_security_ids:
            retired = dict(old)
            retired["active_to"] = retired.get("active_to") or as_of.isoformat()
            security_rows.append(retired)

    payload = {
        "schema_version": 1,
        "as_of": as_of.isoformat(),
        "identity_policy": "stable issuer_id anchored to CSE security identity; names/symbols are effective-dated attributes",
        "issuers": sorted(issuer_rows, key=lambda row: str(row.get("issuer_id"))),
        "securities": sorted(security_rows, key=lambda row: int(row.get("security_id") or 0)),
    }
    persistent_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    output = project_root / "outputs" / f"issuer_security_master_{as_of.isoformat()}.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output, payload


def _quarter_number(period_end: date, fy_end_month: int | None) -> int:
    fy_end = fy_end_month or 12
    months_from_start = (period_end.month - (fy_end % 12 + 1)) % 12
    return months_from_start // 3 + 1


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    import calendar

    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_disclosure_calendar(
    project_root: Path,
    as_of: date,
    periods: Iterable[date],
    master: dict[str, Any],
) -> Path:
    """Materialise what the system is entitled to expect from each listing segment."""

    rows: list[dict[str, Any]] = []
    for issuer in master.get("issuers", []):
        if issuer.get("active_to") and str(issuer["active_to"]) < as_of.isoformat():
            continue
        segment = str(issuer.get("listing_segment") or "UNKNOWN").upper()
        fy_end = issuer.get("fiscal_year_end_month")
        for period_end in periods:
            q = _quarter_number(period_end, int(fy_end) if fy_end else None)
            if segment == "MAIN":
                requirement = "FULL_INTERIM_REQUIRED"
                due = _add_months(period_end, 2) if q == 4 else date.fromordinal(period_end.toordinal() + 45)
            elif segment == "EMPOWER":
                if q in {2, 4}:
                    requirement = "FULL_INTERIM_REQUIRED"
                    due = _add_months(period_end, 2)
                else:
                    requirement = "SUPPLEMENTARY_DISCLOSURE_REQUIRED"
                    due = date.fromordinal(period_end.toordinal() + 45)
            else:
                requirement = "SEGMENT_UNKNOWN_REVIEW_REQUIRED"
                due = None
            status = "UNKNOWN"
            if due is not None:
                status = "NOT_YET_DUE" if as_of <= due else "DUE_OR_OVERDUE"
            rows.append(
                {
                    "issuer_id": issuer.get("issuer_id"),
                    "legal_name": issuer.get("legal_name"),
                    "listing_segment": segment,
                    "period_end": period_end.isoformat(),
                    "fiscal_quarter": q,
                    "requirement": requirement,
                    "due_date": due.isoformat() if due else None,
                    "as_of_status": status,
                }
            )
    path = project_root / "outputs" / f"expected_disclosures_{as_of.isoformat()}.json"
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return path


def _source_metric_basis(row: dict[str, Any], issuer_type: str) -> str | None:
    if str(row.get("metric_code")) != "TOP_LINE":
        return None
    source = str(row.get("source_line") or "").casefold()
    rules = (
        ("insurance revenue", "INSURANCE_REVENUE"),
        ("gross written premium", "GROSS_WRITTEN_PREMIUM"),
        ("net earned premium", "NET_EARNED_PREMIUM"),
        ("gross income", "GROSS_INCOME"),
        ("total operating income", "TOTAL_OPERATING_INCOME"),
        ("revenue", "REVENUE"),
        ("turnover", "TURNOVER"),
        ("net sales", "NET_SALES"),
        ("total income", "TOTAL_INCOME"),
    )
    for needle, code in rules:
        if needle in source:
            return code
    return f"{issuer_type}_TOP_LINE_UNRESOLVED"


def _accounting_regime(row: dict[str, Any], issuer_type: str) -> str:
    if issuer_type != "INSURANCE":
        return "SLFRS_GENERAL_PRESENTATION"
    try:
        year = date.fromisoformat(str(row.get("period_end"))).year
    except ValueError:
        return "INSURANCE_REGIME_UNKNOWN"
    source = str(row.get("source_line") or "").casefold()
    if "insurance revenue" in source:
        return "SLFRS17_PRESENTATION_EVIDENCE"
    if year == 2026 and (
        "gross written premium" in source or "net earned premium" in source
    ):
        return "SLFRS4_OR_2026_SOAT_PRESENTATION_EVIDENCE"
    if year >= 2027:
        return "INSURANCE_REGIME_REQUIRES_EXPLICIT_SOURCE_EVIDENCE"
    return "SLFRS4_PRESENTATION_EVIDENCE"


def write_fact_semantics(
    project_root: Path, as_of: date, repository: Repository
) -> Path:
    path = project_root / "outputs" / f"fact_semantics_{as_of.isoformat()}.jsonl"
    lines: list[str] = []
    for row in repository.fact_rows:
        issuer_type = infer_issuer_type(str(row.get("issuer_name") or ""))
        metric = str(row.get("metric_code") or "")
        payload = {
            "fact_id": row.get("fact_id"),
            "filing_id": row.get("filing_id"),
            "filing_sha256": row.get("filing_sha256"),
            "issuer_name": row.get("issuer_name"),
            "symbol": row.get("symbol"),
            "period_end": row.get("period_end"),
            "metric_code": metric,
            "canonical_metric_code": (
                "LIABILITIES_TO_EQUITY" if metric == "DEBT_TO_EQUITY" else metric
            ),
            "source_metric_code": _source_metric_basis(row, issuer_type),
            "accounting_regime": _accounting_regime(row, issuer_type),
            "ratio_definition": RATIO_DEFINITIONS.get(metric),
        }
        lines.append(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def write_metric_definition_contract(project_root: Path, as_of: date) -> Path:
    """Write the authoritative R4 human-facing metric semantics."""

    path = project_root / "outputs" / f"metric_definitions_{as_of.isoformat()}.json"
    payload = {
        "schema_version": 2,
        "DEBT_TO_EQUITY": RATIO_DEFINITIONS["DEBT_TO_EQUITY"],
        "LIABILITIES_TO_EQUITY": {
            **RATIO_DEFINITIONS["DEBT_TO_EQUITY"],
            "alias_of_legacy_internal_code": "DEBT_TO_EQUITY",
        },
        "ROE": RATIO_DEFINITIONS["ROE"],
        "ROA": RATIO_DEFINITIONS["ROA"],
        "NPM": RATIO_DEFINITIONS["NPM"],
        "TOTAL_LIABILITIES": {
            "display_name": "Total Liabilities",
            "publication_rule": "explicit standalone Total Liabilities source row only",
            "reconciliation_only": "Total assets - Total equity",
        },
        "MARKET_PRICE_QUARTER_END": {
            "display_name": "Last Traded Price for the Interim Period",
            "publication_rule": "filing-disclosed last traded price or official trade history on/before period end",
            "not_equivalent_to": ["closing price", "closing market price", "generic market price"],
        },
        "QUARTER_FLOW_POLICY": {
            "publication_rule": "explicitly reported standalone three-month value only",
            "derived_q4": "analytic/audit use only; not publishable as the reported quarter",
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _rewrite_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        fieldnames = sorted({str(key) for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _harden_repository_rows(repository: Repository) -> dict[str, int]:
    counts: Counter[str] = Counter()
    reviews: list[tuple[dict[str, Any], str, str]] = []
    for row in repository.fact_rows:
        status = str(row.get("status") or "")
        if status not in PUBLISHABLE:
            continue
        metric = str(row.get("metric_code") or "")
        issuer_type = infer_issuer_type(str(row.get("issuer_name") or ""))
        if metric in BASE_FLOW_METRICS:
            duration = row.get("duration_months")
            try:
                duration_int = int(duration) if duration is not None else None
            except (TypeError, ValueError):
                duration_int = None
            if duration_int != 3:
                row["normalized_value"] = None
                row["status"] = "NON_QUARTER_FLOW_WITHHELD"
                row["validation_status"] = "REVIEW"
                row["review_status"] = "REVIEW"
                row["missing_reason"] = "NON_QUARTER_FLOW_WITHHELD"
                counts["non_quarter_flow_withheld"] += 1
                reviews.append((row, "NON_QUARTER_FLOW_WITHHELD", "Published flow must be an explicitly reported three-month quarter."))
                continue
            if metric in Q4_REPORTED_ONLY_METRICS and status == "EXTRACTED_DERIVED":
                row["normalized_value"] = None
                row["status"] = "DERIVED_Q4_NOT_PUBLISHABLE"
                row["validation_status"] = "REVIEW"
                row["review_status"] = "REVIEW"
                row["missing_reason"] = "DERIVED_Q4_NOT_PUBLISHABLE"
                counts["derived_q4_withheld"] += 1
                reviews.append((row, "DERIVED_Q4_NOT_PUBLISHABLE", "Derived Q4 analytics cannot populate the reported-quarter output."))
                continue
        if (
            issuer_type == "BANK"
            and metric == "OPERATING_PROFIT"
            and re.search(
                r"operating\s+profit.*\bafter\s+tax(?:es|ation)?\s+on\s+financial\s+services",
                str(row.get("source_line") or ""),
                re.I,
            )
            and not re.search(r"\bbefore\s+tax", str(row.get("source_line") or ""), re.I)
        ):
            row["normalized_value"] = None
            row["status"] = "BANK_OPERATING_PROFIT_BASIS_MISMATCH"
            row["validation_status"] = "REVIEW"
            row["review_status"] = "REVIEW"
            row["missing_reason"] = "BANK_OPERATING_PROFIT_BASIS_MISMATCH"
            counts["bank_operating_profit_basis_withheld"] += 1
            reviews.append((row, "BANK_OPERATING_PROFIT_BASIS_MISMATCH", "Required bank operating-profit basis is before taxes on financial services."))

    for row, reason, detail in reviews:
        repository.add_review(
            repository.run_id or "UNKNOWN",
            str(row.get("issuer_name") or ""),
            str(row.get("symbol") or ""),
            reason,
            period_end=(
                date.fromisoformat(str(row.get("period_end")))
                if row.get("period_end")
                else None
            ),
            metric_code=str(row.get("metric_code") or ""),
            detail=detail,
        )

    for row in repository.price_rows:
        if str(row.get("status") or "") not in {"EXTRACTED", "RESOLVED_HISTORICAL"}:
            continue
        method = str(row.get("source_method") or "")
        source = str(row.get("source_line") or "")
        if method.startswith("FILING") and method != "FILING_LAST_TRADED":
            row["value"] = None
            row["status"] = "PRICE_SEMANTIC_UNVERIFIED"
            row["validation_status"] = "REVIEW"
            counts["filing_price_semantic_withheld"] += 1
        if method in {"CSE_HISTORICAL", "LAST_TRADE_ON_OR_BEFORE_QUARTER_END"}:
            # Old generic historical methods may have originated from a close field.
            row["value"] = None
            row["status"] = "PRICE_SEMANTIC_UNVERIFIED"
            row["validation_status"] = "REVIEW"
            counts["legacy_historical_price_withheld"] += 1
        if "closing_price" in source.casefold() or "closing price" in source.casefold():
            row["value"] = None
            row["status"] = "PRICE_SEMANTIC_MISMATCH"
            row["validation_status"] = "REVIEW"
            counts["closing_price_withheld"] += 1
    return dict(counts)


def _manifest_path(project_root: Path, as_of: date) -> Path:
    return project_root / "outputs" / "manifests" / f"run_manifest_{as_of.isoformat()}.json"


def _rewrite_manifest(project_root: Path, as_of: date, repository: Repository, hardening: dict[str, Any]) -> None:
    path = _manifest_path(project_root, as_of)
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fact_status_counts"] = dict(
        Counter(str(row.get("status") or "UNKNOWN") for row in repository.fact_rows)
    )
    payload["pipeline_error_count"] = len(
        json.loads(
            (project_root / "outputs" / f"pipeline_errors_{as_of.isoformat()}.json").read_text(
                encoding="utf-8"
            )
        )
    ) if (project_root / "outputs" / f"pipeline_errors_{as_of.isoformat()}.json").exists() else 0
    payload["r4_hardening"] = hardening
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_canonical_issuers_to_staging(staging: Path, master: dict[str, Any]) -> None:
    rows = [
        {
            "issuer_id": row.get("issuer_id"),
            "legal_name": row.get("legal_name"),
            "issuer_type": row.get("issuer_type"),
            "standalone_scope_label": row.get("standalone_scope_label"),
        }
        for row in master.get("issuers", [])
        if not row.get("active_to")
    ]
    schema = {
        "issuer_id": pl.String,
        "legal_name": pl.String,
        "issuer_type": pl.String,
        "standalone_scope_label": pl.String,
    }
    frame = pl.DataFrame(rows, schema=schema, strict=False) if rows else pl.DataFrame(schema=schema)
    temporary = staging / "issuers.parquet.tmp"
    frame.write_parquet(temporary, compression="zstd", statistics=True)
    temporary.replace(staging / "issuers.parquet")


def _timeout_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("issuer_name") or "").strip().casefold(),
        str(row.get("symbol") or "").strip().upper(),
        str(row.get("period_end") or "").strip(),
    )


def _current_pointer_for_timeout(
    project_root: Path, issuer_name: str, period_end: str
) -> dict[str, Any] | None:
    slug = cse_source.safe_slug(issuer_name)
    issuer_dir = project_root / "data" / "raw" / "filings" / slug
    if not issuer_dir.exists():
        return None
    pointers = sorted(issuer_dir.glob(f"{period_end}_*.current.json"))
    for pointer in reversed(pointers):
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("sha256"):
            return payload
    return None


def enforce_hash_bound_quarantines(project_root: Path, as_of: date) -> dict[str, Any]:
    """Bind known timeout exceptions to the exact filing ID and SHA-256 artifact."""

    baseline = load_yaml(project_root / "configs" / "coverage_baseline.yml")
    allowed = {
        _timeout_identity(row): row
        for row in baseline.get("quarantined_extraction_timeouts") or []
        if isinstance(row, dict)
    }
    errors_path = project_root / "outputs" / f"pipeline_errors_{as_of.isoformat()}.json"
    if not errors_path.exists():
        return {"checked": 0, "mismatches": 0}
    errors = json.loads(errors_path.read_text(encoding="utf-8"))
    if not isinstance(errors, list):
        return {"checked": 0, "mismatches": 0}

    pins_path = project_root / "data" / "quarantine" / "known_timeout_pins.json"
    pins_path.parent.mkdir(parents=True, exist_ok=True)
    if pins_path.exists():
        try:
            pins = json.loads(pins_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pins = {}
    else:
        pins = {}
    if not isinstance(pins, dict):
        pins = {}

    checked = 0
    mismatches: list[dict[str, Any]] = []
    for row in list(errors):
        identity = _timeout_identity(row)
        if identity not in allowed:
            continue
        if str(row.get("stage") or "") != "EXTRACTION" or "process tree was terminated" not in str(
            row.get("error") or ""
        ):
            continue
        checked += 1
        pointer = _current_pointer_for_timeout(
            project_root,
            str(row.get("issuer_name") or ""),
            str(row.get("period_end") or ""),
        )
        if pointer is None:
            mismatches.append(
                {
                    **row,
                    "stage": "QUARANTINE_INTEGRITY",
                    "error": "Known timeout has no verified current filing pointer; hash-bound quarantine cannot be proven",
                }
            )
            continue
        key = "|".join(identity)
        current_pin = {
            "issuer_name": row.get("issuer_name"),
            "symbol": row.get("symbol"),
            "period_end": row.get("period_end"),
            "filing_id": pointer.get("filing_id"),
            "sha256": pointer.get("sha256"),
        }
        old = pins.get(key)
        if old is None:
            pins[key] = current_pin
        elif (
            str(old.get("sha256") or "") != str(current_pin.get("sha256") or "")
            or str(old.get("filing_id") or "") != str(current_pin.get("filing_id") or "")
        ):
            mismatches.append(
                {
                    **row,
                    "stage": "QUARANTINE_INTEGRITY",
                    "error": (
                        "Known timeout filing revision changed; old quarantine is invalid "
                        f"(pinned filing_id={old.get('filing_id')} sha256={old.get('sha256')}, "
                        f"current filing_id={current_pin.get('filing_id')} sha256={current_pin.get('sha256')})"
                    ),
                }
            )
    if mismatches:
        errors.extend(mismatches)
        errors_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")
    pins_path.write_text(json.dumps(pins, indent=2, sort_keys=True), encoding="utf-8")
    output = project_root / "outputs" / f"quarantine_integrity_{as_of.isoformat()}.json"
    payload = {
        "checked": checked,
        "mismatches": len(mismatches),
        "pins_path": str(pins_path),
        "mismatch_rows": mismatches,
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def apply_r4_hardening(
    project_root: Path,
    as_of: date,
    periods: Iterable[date],
    repository: Repository,
    *,
    run_status: str,
    statistics: dict[str, Any],
) -> dict[str, Any]:
    """Apply R4 policies to in-memory rows, output CSVs, and the staged generation."""

    row_changes = _harden_repository_rows(repository)
    master_path, master = build_canonical_master(project_root, as_of, repository)
    disclosure_path = build_disclosure_calendar(project_root, as_of, periods, master)
    semantics_path = write_fact_semantics(project_root, as_of, repository)
    metric_definitions_path = write_metric_definition_contract(project_root, as_of)
    quarantine = enforce_hash_bound_quarantines(project_root, as_of)

    facts_csv = project_root / "outputs" / f"normalized_facts_{as_of.isoformat()}.csv"
    prices_csv = project_root / "outputs" / f"quarter_end_prices_{as_of.isoformat()}.csv"
    review_csv = project_root / "outputs" / f"review_queue_{as_of.isoformat()}.csv"
    _rewrite_csv(facts_csv, repository.fact_rows)
    _rewrite_csv(prices_csv, repository.price_rows)
    _rewrite_csv(review_csv, repository.review_rows)

    summary = {
        "schema_version": 1,
        "no_database": True,
        "xbrl": "NOT_IMPLEMENTED_UNTIL_OFFICIALLY_AVAILABLE",
        "row_changes": row_changes,
        "canonical_master": str(master_path),
        "expected_disclosures": str(disclosure_path),
        "fact_semantics": str(semantics_path),
        "metric_definitions": str(metric_definitions_path),
        "quarantine_integrity": quarantine,
        "reported_q4_only": True,
        "price_semantic": "LAST_TRADED_ONLY",
        "bank_nil_policy": "explicit nil on verified exact-quarter Bank statement only; blank/dash never zero",
    }

    # Re-write the candidate generation after semantic withholding, then replace its
    # issuer table with stable canonical IDs.  This keeps gold fail-closed.
    hardened_statistics = dict(statistics)
    hardened_statistics["fact_status_counts"] = dict(
        Counter(str(row.get("status") or "UNKNOWN") for row in repository.fact_rows)
    )
    hardened_statistics["review_count"] = len(repository.review_rows)
    staging = repository._write_staging(run_status, hardened_statistics)
    _write_canonical_issuers_to_staging(staging, master)

    _rewrite_manifest(project_root, as_of, repository, summary)
    summary_path = project_root / "outputs" / f"r4_hardening_{as_of.isoformat()}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
