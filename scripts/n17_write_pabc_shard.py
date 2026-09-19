"""Write PABC N17 AI blind gold shard from PDF text evidence only."""

from __future__ import annotations

import json
from pathlib import Path

REVIEWER = "chatgpt-blind-source-review-2026-09-19"
SHA = "877a4a55b2a5d2bf2de36c98b7d0025c9874f47b53ae3652a3bff8b1900762ca"
FID = "PABC.N0000-2025-12-31"
ISSUER = "PABC.N0000"


def row(**kwargs):
    base = {
        "schema_version": "v2.0.0",
        "filing_version_id": FID,
        "pdf_sha256": SHA,
        "issuer_id": ISSUER,
        "bbox": None,
        "reviewer_1": REVIEWER,
        "reviewer_2": None,
        "adjudication_status": "AI_REVIEWER_1_COMPLETE",
        "split": "HOLDOUT",
    }
    base.update(kwargs)
    return base


ROWS = [
    row(
        metric_code="TOP_LINE",
        source_presence="NOT_REPORTED",
        raw_source_label=None,
        raw_source_value=None,
        normalized_value=None,
        entity_scope=None,
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency=None,
        scale=None,
        unit_dimension=None,
        page=7,
        evidence_text=(
            "Income Statement For the Quarter ended 31st December shows Interest Income "
            "and Total Operating Income; no Gross income line."
        ),
        evidence_level="STATEMENT_EXPLICIT",
        notes="BANK TOP_LINE requires Gross income. Interest/Total operating income not substituted.",
    ),
    row(
        metric_code="OPERATING_PROFIT",
        source_presence="REPORTED",
        raw_source_label="Operating Profit before Taxes on Financial Services",
        raw_source_value="1,943,397",
        normalized_value="1943397000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=7,
        evidence_text=(
            "Income Statement Quarter ended 31 Dec 2025: Operating Profit before Taxes on "
            "Financial Services 1,943,397 In Rupee Thousands."
        ),
        evidence_level="CELL_EXPLICIT",
        notes="Standalone Bank income statement. Page/text verified; bbox unavailable.",
    ),
    row(
        metric_code="PBT",
        source_presence="REPORTED",
        raw_source_label="Profit before Tax",
        raw_source_value="1,493,734",
        normalized_value="1493734000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=7,
        evidence_text="Quarter ended 31 Dec 2025: Profit before Tax 1,493,734 In Rupee Thousands.",
        evidence_level="CELL_EXPLICIT",
        notes="Page/text verified; bbox unavailable.",
    ),
    row(
        metric_code="PAT",
        source_presence="REPORTED",
        raw_source_label="Profit for the Period",
        raw_source_value="981,161",
        normalized_value="981161000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=7,
        evidence_text=(
            "Quarter ended 31 Dec 2025: Profit for the Period 981,161 In Rupee Thousands "
            "(year 4,005,578 not used)."
        ),
        evidence_level="CELL_EXPLICIT",
        notes="Q4 explicit; year not substituted.",
    ),
    row(
        metric_code="EPS_BASIC",
        source_presence="REPORTED",
        raw_source_label="Earnings Per Share - Basic/Diluted (Rs.)",
        raw_source_value="2.22",
        normalized_value="2.22",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1",
        unit_dimension="PER_SHARE",
        page=7,
        evidence_text="Quarter ended 31 Dec 2025: Earnings Per Share - Basic/Diluted (Rs.) 2.22.",
        evidence_level="CELL_EXPLICIT",
        notes="Per-share; Rs thousands not applied.",
    ),
    row(
        metric_code="EPS_DILUTED",
        source_presence="REPORTED",
        raw_source_label="Earnings Per Share - Basic/Diluted (Rs.)",
        raw_source_value="2.22",
        normalized_value="2.22",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1",
        unit_dimension="PER_SHARE",
        page=7,
        evidence_text="Same source line explicitly labels Basic/Diluted for quarter 2.22.",
        evidence_level="CELL_EXPLICIT",
        notes="Diluted co-labelled with basic on one source line.",
    ),
    row(
        metric_code="TOTAL_ASSETS",
        source_presence="REPORTED",
        raw_source_label="Total Assets",
        raw_source_value="308,015,795",
        normalized_value="308015795000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=9,
        evidence_text="As at 31/12/2025: Total Assets 308,015,795 In Rupee Thousands.",
        evidence_level="CELL_EXPLICIT",
        notes="Page/text verified; bbox unavailable.",
    ),
    row(
        metric_code="TOTAL_LIABILITIES",
        source_presence="REPORTED",
        raw_source_label="Total Liabilities",
        raw_source_value="277,625,625",
        normalized_value="277625625000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=9,
        evidence_text="As at 31/12/2025: Total Liabilities 277,625,625 In Rupee Thousands.",
        evidence_level="CELL_EXPLICIT",
        notes="Explicit total liabilities; not derived.",
    ),
    row(
        metric_code="TOTAL_EQUITY",
        source_presence="REPORTED",
        raw_source_label="Total Equity",
        raw_source_value="30,390,170",
        normalized_value="30390170000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=9,
        evidence_text="As at 31/12/2025: Total Equity 30,390,170 In Rupee Thousands.",
        evidence_level="CELL_EXPLICIT",
        notes="Page/text verified; bbox unavailable.",
    ),
    row(
        metric_code="NAVPS",
        source_presence="REPORTED",
        raw_source_label="Net Asset Value Per Share (Rs.)",
        raw_source_value="68.67",
        normalized_value="68.67",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1",
        unit_dimension="PER_SHARE",
        page=9,
        evidence_text="As at 31/12/2025: Net Asset Value Per Share (Rs.) 68.67.",
        evidence_level="CELL_EXPLICIT",
        notes="Per-share; Rs thousands not applied.",
    ),
]


def main() -> int:
    out = Path("outputs/n17_blind_partial/PABC.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in ROWS) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out} rows={len(ROWS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
