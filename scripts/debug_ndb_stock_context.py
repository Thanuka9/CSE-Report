"""Targeted diagnostic for NDB's published 2026-06-30 statement of financial position.

This is an engineering diagnostic only. It never changes production facts or manual gold.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from pathlib import Path

from cse_financial_etl.config import (
    load_app_config,
    load_issuers,
    load_metric_catalog,
    load_unit_pattern_config,
)
from cse_financial_etl.extraction.semantic_matcher import apply_metric_catalog, get_semantic_matcher
from cse_financial_etl.extraction.statement_extractor import extract_filing
from cse_financial_etl.extraction.unit_detector import configure_unit_patterns
from cse_financial_etl.orchestration.pipeline import build_extract_kwargs

URL = "https://cdn.cse.lk/cmt/upload_report_file/386_1784717094209.pdf"
ISSUER = "NATIONAL DEVELOPMENT BANK PLC"
SYMBOL = "NDB.N0000"
PERIOD = date(2026, 6, 30)
TARGET_CODES = {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out = root / "outputs" / "ndb_debug"
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / "ndb_2026-06-30.pdf"
    if not pdf.exists():
        urllib.request.urlretrieve(URL, pdf)

    app = load_app_config(root)
    issuers = load_issuers(root)
    os.environ["CSE_ETL_USE_TRANSFORMER"] = "1" if app.use_transformer else "0"
    os.environ["CSE_ETL_SEMANTIC_MODEL"] = app.semantic_model
    apply_metric_catalog(load_metric_catalog(root))
    configure_unit_patterns(load_unit_pattern_config(root))
    get_semantic_matcher.cache_clear()

    diagnostics = out / "diagnostics"
    kwargs = build_extract_kwargs(
        app_config=app,
        issuers=issuers,
        text_cache_dir=out / "ocr",
        diagnostics_dir=diagnostics,
        compile_statements=True,
        run_tunnel_b_always=True,
    )
    facts = extract_filing(pdf, ISSUER, SYMBOL, PERIOD, **kwargs)
    selected = [fact.as_json() for fact in facts if fact.metric_code in TARGET_CODES]
    payload = {
        "issuer": ISSUER,
        "symbol": SYMBOL,
        "period_end": PERIOD.isoformat(),
        "target_facts": selected,
    }
    result = out / "ndb_stock_context.json"
    result.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
