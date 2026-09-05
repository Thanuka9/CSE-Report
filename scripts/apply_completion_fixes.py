from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"Could not apply {label}")
    return text.replace(old, new, 1)


def patch_pipeline() -> None:
    path = "src/cse_financial_etl/orchestration/pipeline.py"
    text = read(path)
    pattern = r"def derive_cumulative_quarters\([\s\S]*?\n\nclass Pipeline:"
    replacement = '''def derive_cumulative_quarters(
    extracted_results: list[tuple[DownloadedFiling, list[ExtractedFact]]],
) -> list[tuple[DownloadedFiling, list[ExtractedFact]]]:
    """Compatibility no-op: cumulative/YTD values are never published as quarters."""

    return extracted_results


class Pipeline:'''
    if "CUMULATIVE_DELTA" in text:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError("Could not remove cumulative-quarter derivation")

    text = replace_once(
        text,
        '''        metadata = fetch_all_financial_metadata(
            securities,
            self.data / "raw" / "api" / "financials",
            workers=api_workers,
        )''',
        '''        metadata = fetch_all_financial_metadata(
            securities,
            self.data / "raw" / "api" / "financials",
            workers=api_workers,
            offline=offline,
        )''',
        "offline metadata propagation",
    )
    text = replace_once(
        text,
        '''                    max_file_bytes=self.app_config.max_file_bytes,
                ): filing''',
        '''                    max_file_bytes=self.app_config.max_file_bytes,
                    offline=offline,
                ): filing''',
        "offline download propagation",
    )
    write(path, text)


def patch_periods() -> None:
    write(
        "src/cse_financial_etl/domain/periods.py",
        '''from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def shift_quarter(period_end: date, quarters_back: int) -> date:
    total_months = period_end.year * 12 + period_end.month - 1 - quarters_back * 3
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    day = 31 if month in {3, 12} else 30
    return date(year, month, day)


def supporting_periods(display_periods: Iterable[date]) -> tuple[date, ...]:
    """Return only requested quarter ends; no TTM or cumulative-delta history is needed."""

    return tuple(sorted(set(display_periods)))
''',
    )


def patch_liabilities() -> None:
    path = "src/cse_financial_etl/extraction/statement_extractor.py"
    text = read(path)
    if 'source_line="Derived from normalized Total Assets minus Total Equity"' not in text:
        return
    pattern = (
        r"    fact_map = facts_by_code\(facts\)\n"
        r"    liabilities = fact_map\.get\(\"TOTAL_LIABILITIES\"\)[\s\S]*?"
        r"    diluted = fact_map\.get\(\"EPS_DILUTED\"\)"
    )
    replacement = '''    fact_map = facts_by_code(facts)
    # Total Liabilities remains source-backed. Assets - Equity is validation only.

    diluted = fact_map.get("EPS_DILUTED")'''
    text, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError("Could not remove derived liabilities publication")
    write(path, text)


def patch_sources() -> None:
    path = "src/cse_financial_etl/sources/cse.py"
    text = read(path)
    start = text.index("def fetch_all_financial_metadata(")
    end = text.index("\n\ndef choose_filing", start)
    replacement = '''def fetch_all_financial_metadata(
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
    return results'''
    text = text[:start] + replacement + text[end:]
    if "offline: bool = False" not in text[text.index("def download_filing("):]:
        text = replace_once(
            text,
            '''    *,
    max_file_bytes: int = 50 * 1024 * 1024,
) -> DownloadedFiling:''',
            '''    *,
    max_file_bytes: int = 50 * 1024 * 1024,
    offline: bool = False,
) -> DownloadedFiling:''',
            "download offline parameter",
        )
        text = replace_once(
            text,
            '''    if not destination.exists() or destination.stat().st_size == 0:
        request = urllib.request.Request''',
            '''    if not destination.exists() or destination.stat().st_size == 0:
        if offline:
            raise FileNotFoundError(f"Offline filing cache not found: {destination}")
        request = urllib.request.Request''',
            "offline filing guard",
        )
    write(path, text)


def patch_gate() -> None:
    path = "src/cse_financial_etl/validation/production_gates.py"
    text = read(path)
    if "DERIVED_FLOW_PUBLISHED" in text:
        return
    marker = '''            if (
                fact.metric_code in FLOW_CODES
                and fact.comparison_role != "CURRENT"
            ):'''
    gate = '''            if fact.metric_code in FLOW_CODES and fact.status == "EXTRACTED_DERIVED":
                hits.append(
                    GateHit(
                        "DERIVED_FLOW_PUBLISHED",
                        fact.issuer_name,
                        fact.symbol,
                        fact.period_end,
                        fact.metric_code,
                        f"flow fact published with extraction_method={fact.extraction_method}",
                    )
                )
            if (
                fact.metric_code in FLOW_CODES
                and fact.comparison_role != "CURRENT"
            ):'''
    text = replace_once(text, marker, gate, "derived flow gate")
    write(path, text)


def patch_docs() -> None:
    path = "README.md"
    text = read(path)
    text = text.replace(
        "Both basic and diluted EPS remain in audit storage. Flow facts use the explicitly reported standalone three-month/quarter column, including `4Q`. If a filing genuinely supplies cumulative data only, eligible Q4 flow metrics may be derived from compatible normalized FY and prior standalone quarters; EPS is never derived this way and every derived value carries formula lineage.",
        "Both basic and diluted EPS remain in audit storage. Flow facts use only an explicitly reported standalone three-month/quarter column, including `4Q`. Cumulative 6M/9M/YTD/FY values remain review evidence and are never converted into a quarter.",
    )
    text = text.replace(
        "| Transformation | `Decimal` arithmetic, deterministic period/entity/unit rules and audited cumulative deltas |",
        "| Transformation | `Decimal` arithmetic and deterministic exact-quarter/entity/unit rules |",
    )
    text = text.replace(
        "- Exact quarter: flows recognize three-month, quarter and `1Q`-`4Q` headers. Compatible cumulative-only flows can be derived with full evidence; incompatible inputs remain in review.",
        "- Exact quarter: flows recognize three-month, quarter and `1Q`-`4Q` headers. Cumulative-only 6M/9M/YTD/FY values remain review evidence and are never published as a quarter.",
    )
    text = text.replace(
        "- Liabilities: use the explicit standalone total; if absent but assets and equity are source-backed, derive `Assets - Equity` and record `EXTRACTED_DERIVED` lineage.",
        "- Liabilities: publish only the explicit standalone Total Liabilities value. `Assets - Equity` is a reconciliation check only.",
    )
    write(path, text)

    write(
        "docs/metric_methodology.md",
        '''# Metric methodology

## Periods

Flow metrics use only explicitly reported standalone three-month/current-quarter values. Stock metrics use the standalone balance at period end. Q4 requires an explicitly reported standalone three-month/`4Q` value. Annual, 6M, 9M and YTD columns are never copied or differenced into a quarter. Cumulative-only values remain review evidence.

EPS output selects diluted EPS when the exact current quarter reports it, otherwise basic EPS. Both remain in audit storage. Total liabilities must be explicitly extracted from the standalone statement; `Total Assets - Total Equity` is used only as a reconciliation check.

## Ratios

- ROE: same-quarter PAT divided by that quarter's total equity.
- ROA: same-quarter PAT divided by that quarter's total assets.
- NPM: same-quarter PAT divided by that quarter's top line.
- Debt to equity: total liabilities divided by total equity, expressed as a multiple (`x`).

No ratio is emitted when required inputs are missing, incompatible or have an invalid denominator. There is no TTM logic.
''',
    )

    path = "src/cse_financial_etl/reporting/excel.py"
    text = read(path)
    text = text.replace(
        '"Explicit 4Q preferred; compatible cumulative-only flows may use an audited delta; EPS never derived",',
        '"Only an explicitly reported standalone 3M/4Q flow is publishable; cumulative/FY deltas are never used",',
    )
    write(path, text)


def patch_tests() -> None:
    path = "tests/unit/test_pipeline_gaps.py"
    text = read(path)
    old = '''def test_supporting_periods_include_prior_quarters_for_q4_delta() -> None:
    assert shift_quarter(date(2026, 6, 30), 1) == date(2026, 3, 31)
    periods = supporting_periods([date(2026, 6, 30)])
    assert date(2025, 9, 30) in periods
    assert date(2025, 6, 30) not in periods
    assert date(2026, 6, 30) in periods
'''
    new = '''def test_supporting_periods_are_exact_requested_window() -> None:
    assert shift_quarter(date(2026, 6, 30), 1) == date(2026, 3, 31)
    periods = supporting_periods([date(2026, 6, 30), date(2026, 3, 31)])
    assert periods == (date(2026, 3, 31), date(2026, 6, 30))
'''
    if old in text:
        text = text.replace(old, new, 1)
    write(path, text)

    path = "tests/unit/test_production_gates.py"
    text = read(path)
    if "test_derived_flow_is_a_hard_stop" not in text:
        anchor = "\ndef test_comparative_published_as_current_is_a_hard_stop"
        test = '''\ndef test_derived_flow_is_a_hard_stop(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(status="EXTRACTED_DERIVED", extraction_method="CUMULATIVE_DELTA")])]
    )
    assert [hit.code for hit in hits] == ["DERIVED_FLOW_PUBLISHED"]
    assert run_status_from_gates(hits, has_errors=False, has_review=False) == "VALIDATION_REQUIRED"

'''
        text = replace_once(text, anchor, test + anchor, "derived flow gate test")
    write(path, text)

    path = "tests/regression/test_structure_benchmark.py"
    text = read(path)
    if "test_cumulative_only_flow_is_never_published_as_quarter" not in text:
        text += '''

def test_cumulative_only_flow_is_never_published_as_quarter(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "cumulative_only.pdf",
        "Statement of profit or loss - Company\n"
        "For the six months ended 30 June 2025\n"
        "Rs.'000\n"
        "Profit for the period 12,500 10,000",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    pat = facts_by_code(facts)["PAT"]
    assert pat.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}


def test_total_liabilities_is_never_assets_minus_equity_fallback(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "no_liabilities.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 300 250\n"
        "Total equity 100 90",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert liabilities.status != "EXTRACTED_DERIVED"
    assert liabilities.normalized_value is None
'''
    write(path, text)


def main() -> None:
    patch_pipeline()
    patch_periods()
    patch_liabilities()
    patch_sources()
    patch_gate()
    patch_docs()
    patch_tests()
    frozen = read("docs/CSE_ETL_Final_Frozen_Architecture_NoDB_NoLLM.md")
    assert "Q4 is calculated as FY minus 9M" in frozen
    assert "a cumulative 6M/9M/YTD value is used" in frozen
    print("Frozen-contract completion fixes applied.")


if __name__ == "__main__":
    main()
