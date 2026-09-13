"""Load V1-adjudicated CSE filings for V2 golden/shadow runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.diagnostics.golden import GoldenFact

FLOW_METRICS = frozenset({"PAT", "PBT", "OPERATING_PROFIT", "TOP_LINE", "EPS_BASIC", "EPS_DILUTED"})
REVIEWER = "v1-adjudicated-golden-json"
REVIEW_DATE = date(2026, 9, 13)
GoldRole = Literal["scoring", "regression"]
LOCK_RELATIVE = Path("tests/v2/golden/real_filings_lock.json")
GOLD_RELATIVE = Path("tests/fixtures/golden_financial_facts.json")
OVERLAY_RELATIVE = Path("tests/v2/golden/adjudication_round1.json")


@dataclass(frozen=True)
class GoldLock:
    lock_id: str
    note: str
    scoring_symbols: tuple[str, ...]
    regression_symbols: tuple[str, ...]
    known_timeout_symbols: tuple[str, ...]
    required_manual_qa_symbols: tuple[str, ...]


@dataclass(frozen=True)
class RealFilingCase:
    case_id: str
    pdf_path: Path
    issuer_id: str
    issuer_name: str
    entity_scope: EntityScope
    period_end: date
    expected: tuple[GoldenFact, ...]
    issuer_type: str = ""
    verification_status: str = ""
    gold_role: GoldRole = "scoring"


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError("pyproject.toml not found")


def load_gold_lock(*, root: Path | None = None) -> GoldLock:
    root = root or project_root()
    payload = json.loads((root / LOCK_RELATIVE).read_text(encoding="utf-8"))
    scoring = tuple(str(item) for item in payload["scoring_symbols"])
    if not 25 <= len(scoring) <= 40:
        raise ValueError(f"scoring lock must contain 25-40 symbols, got {len(scoring)}")
    return GoldLock(
        lock_id=str(payload["id"]),
        note=str(payload["note"]),
        scoring_symbols=scoring,
        regression_symbols=tuple(str(item) for item in payload.get("regression_symbols") or ()),
        known_timeout_symbols=tuple(
            str(item) for item in payload.get("known_timeout_symbols") or ()
        ),
        required_manual_qa_symbols=tuple(
            str(item) for item in payload.get("required_manual_qa_symbols") or ()
        ),
    )


def resolve_filing_pdf(relative: str, *, root: Path | None = None) -> Path | None:
    root = root or project_root()
    rel = Path(relative)
    candidates = [
        root / rel,
        root / "tests" / "fixtures" / "pdf" / rel.name,
        root / "data" / "raw" / "filings" / rel.name,
    ]
    if len(rel.parts) >= 2:
        candidates.append(root / "data" / "raw" / "filings" / rel.parts[-2] / rel.name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_adjudication_overlay(*, root: Path | None = None) -> dict[str, object]:
    root = root or project_root()
    path = root / OVERLAY_RELATIVE
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _overlay_for_symbol(symbol: str, *, root: Path) -> dict[str, object] | None:
    payload = load_adjudication_overlay(root=root)
    symbols = payload.get("symbols")
    if not isinstance(symbols, dict):
        return None
    row = symbols.get(symbol)
    return row if isinstance(row, dict) else None


def _golden_payload(*, root: Path) -> list[dict[str, object]]:
    payload = json.loads((root / GOLD_RELATIVE).read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)]


def _apply_overlay(
    expected: tuple[GoldenFact, ...],
    overlay: dict[str, object] | None,
) -> tuple[GoldenFact, ...]:
    if overlay is None:
        return expected
    action = str(overlay.get("action") or "")
    if action == "drop_all_expected":
        return ()
    drop = overlay.get("drop")
    drop_codes = {str(item) for item in drop} if isinstance(drop, list) else set()
    expected = tuple(item for item in expected if item.metric_code not in drop_codes)
    replacements = overlay.get("replace") if action == "replace" else None
    if not isinstance(replacements, dict) or not replacements:
        return expected
    reviewer = str(overlay.get("reviewer") or "v2-pdf-heading-adjudication")
    review_date_raw = overlay.get("review_date")
    review_date = (
        date.fromisoformat(str(review_date_raw))
        if review_date_raw
        else date(2026, 9, 13)
    )
    updated: list[GoldenFact] = []
    for fact in expected:
        replacement = replacements.get(fact.metric_code)
        if replacement is None:
            updated.append(fact)
            continue
        value = Decimal(str(replacement))
        updated.append(
            fact.model_copy(
                update={
                    "raw_value": value,
                    "normalized_value": value,
                    "reviewer": reviewer,
                    "review_date": review_date,
                }
            )
        )
    return tuple(updated)


def _facts_from_item(
    item: dict[str, object], *, entity: EntityScope, period_end: date
) -> tuple[GoldenFact, ...]:
    contexts = item.get("fact_context") if isinstance(item.get("fact_context"), dict) else {}
    facts_raw = item.get("facts") or {}
    if not isinstance(facts_raw, dict):
        return ()
    expected: list[GoldenFact] = []
    for code, value in facts_raw.items():
        if str(code) == "LAST_TRADED_PRICE":
            continue
        raw_ctx = contexts.get(str(code)) if isinstance(contexts, dict) else None
        ctx: dict[str, object] = raw_ctx if isinstance(raw_ctx, dict) else {}
        entity_name = str(ctx.get("entity_scope") or entity.value)
        fact_entity = EntityScope[entity_name]
        duration_raw = ctx.get("duration_months")
        duration: int | None
        if duration_raw is None and str(code) in FLOW_METRICS:
            duration = 3
        elif duration_raw is None:
            duration = None
        else:
            duration = int(str(duration_raw))
        scale = ctx.get("scale_factor")
        period_raw = ctx.get("period_end")
        fact_period = date.fromisoformat(str(period_raw)) if period_raw else period_end
        expected.append(
            GoldenFact(
                metric_code=str(code),
                raw_value=Decimal(str(value)),
                normalized_value=Decimal(str(value)),
                entity_scope=fact_entity,
                period_end=fact_period,
                duration_months=duration,
                unit_scale=Decimal(str(scale)) if scale not in {None, ""} else None,
                page=1,
                reviewer=REVIEWER,
                review_date=REVIEW_DATE,
            )
        )
    return tuple(expected)


def _case_from_item(
    item: dict[str, object],
    *,
    root: Path,
    gold_role: GoldRole,
) -> RealFilingCase | None:
    pdf = resolve_filing_pdf(str(item.get("pdf") or ""), root=root)
    if pdf is None:
        return None
    period_end = date.fromisoformat(str(item["period_end"]))
    entity = EntityScope[str(item["entity_scope"])]
    symbol = str(item.get("symbol") or pdf.stem)
    overlay = _overlay_for_symbol(symbol, root=root)
    expected = _apply_overlay(
        _facts_from_item(item, entity=entity, period_end=period_end),
        overlay,
    )
    if not expected and str((overlay or {}).get("action") or "") != "drop_all_expected":
        return None
    return RealFilingCase(
        case_id=f"{symbol}-{period_end.isoformat()}",
        pdf_path=pdf,
        issuer_id=symbol,
        issuer_name=str(item.get("issuer_name") or symbol),
        entity_scope=entity,
        period_end=period_end,
        expected=expected,
        issuer_type=str(item.get("issuer_type") or ""),
        verification_status=str(item.get("verification_status") or ""),
        gold_role=gold_role,
    )


def load_real_filing_cases(
    *,
    limit: int = 40,
    root: Path | None = None,
    locked: bool = True,
    include_regression: bool = False,
) -> tuple[RealFilingCase, ...]:
    root = root or project_root()
    items = _golden_payload(root=root)
    by_symbol: dict[str, dict[str, object]] = {}
    for item in items:
        symbol = str(item.get("symbol") or "")
        if symbol and symbol not in by_symbol:
            by_symbol[symbol] = item
    lock = load_gold_lock(root=root)
    ordered: list[tuple[str, GoldRole]]
    if locked:
        ordered = [(symbol, "scoring") for symbol in lock.scoring_symbols]
        if include_regression:
            ordered.extend((symbol, "regression") for symbol in lock.regression_symbols)
    else:
        ordered = [(str(item.get("symbol") or ""), "scoring") for item in items]
    cases: list[RealFilingCase] = []
    seen: set[str] = set()
    for symbol, role in ordered:
        if not symbol or symbol in seen:
            continue
        row = by_symbol.get(symbol)
        if row is None:
            continue
        case = _case_from_item(row, root=root, gold_role=role)
        if case is None:
            continue
        seen.add(symbol)
        cases.append(case)
        if len(cases) >= limit:
            break
    return tuple(cases)
