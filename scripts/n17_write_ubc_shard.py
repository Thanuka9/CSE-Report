"""UBC N17 AI blind gold shard — PDF text only."""

from __future__ import annotations

import json
from pathlib import Path

REVIEWER = "chatgpt-blind-source-review-2026-09-19"
SHA = "0760adbaa3ff8a7dee3da318604aee2c5939c58962d88cfe8ae31db6a4becc1d"
FID = "UBC.N0000-2025-12-31"
ISSUER = "UBC.N0000"


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


# Bank Q4 = 2nd value block on IS (Bank year, Bank quarter, Group year, Group quarter)
ROWS = [
    row(
        metric_code="TOP_LINE",
        source_presence="REPORTED",
        raw_source_label="Gross Income",
        raw_source_value="5,035,935",
        normalized_value="5035935000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=3,
        evidence_text="Statement of Profit or Loss BANK For the quarter ended 31.12.2025: Gross Income 5,035,935 LKR '000.",
        evidence_level="CELL_EXPLICIT",
        notes="Bank quarter column (not Group).",
    ),
    row(
        metric_code="OPERATING_PROFIT",
        source_presence="REPORTED",
        raw_source_label="Results from operating activities",
        raw_source_value="733,950",
        normalized_value="733950000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=3,
        evidence_text="BANK quarter: Results from operating activities 733,950 LKR '000.",
        evidence_level="CELL_EXPLICIT",
        notes="Allowed OP variant.",
    ),
    row(
        metric_code="PBT",
        source_presence="REPORTED",
        raw_source_label="Profit before tax",
        raw_source_value="555,016",
        normalized_value="555016000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=3,
        evidence_text="BANK quarter: Profit before tax 555,016 LKR '000.",
        evidence_level="CELL_EXPLICIT",
        notes="Page/text verified; bbox unavailable.",
    ),
    row(
        metric_code="PAT",
        source_presence="REPORTED",
        raw_source_label="Profit after tax",
        raw_source_value="311,748",
        normalized_value="311748000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=3,
        evidence_text="BANK quarter: Profit after tax 311,748 LKR '000 (not attributable line).",
        evidence_level="CELL_EXPLICIT",
        notes="Total-entity after-tax line.",
    ),
    row(
        metric_code="EPS_BASIC",
        source_presence="REPORTED",
        raw_source_label="Earnings per share - Basic",
        raw_source_value="0.3",
        normalized_value="0.3",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1",
        unit_dimension="PER_SHARE",
        page=3,
        evidence_text="BANK quarter: Earnings per share - Basic 0.3.",
        evidence_level="CELL_EXPLICIT",
        notes="Per-share; LKR '000 not applied.",
    ),
    row(
        metric_code="EPS_DILUTED",
        source_presence="REPORTED",
        raw_source_label="Earnings per share - Diluted",
        raw_source_value="0.3",
        normalized_value="0.3",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=3,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1",
        unit_dimension="PER_SHARE",
        page=3,
        evidence_text="BANK quarter: Earnings per share - Diluted 0.3.",
        evidence_level="CELL_EXPLICIT",
        notes="Separate diluted line present.",
    ),
    row(
        metric_code="TOTAL_ASSETS",
        source_presence="REPORTED",
        raw_source_label="Total assets",
        raw_source_value="172,633,303",
        normalized_value="172633303000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=5,
        evidence_text="SOFP As at 31 Dec 2025 BANK: Total assets 172,633,303 LKR '000.",
        evidence_level="CELL_EXPLICIT",
        notes="Bank column not Group.",
    ),
    row(
        metric_code="TOTAL_LIABILITIES",
        source_presence="REPORTED",
        raw_source_label="Total liabilities",
        raw_source_value="152,311,733",
        normalized_value="152311733000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=5,
        evidence_text="SOFP BANK: Total liabilities 152,311,733 LKR '000.",
        evidence_level="CELL_EXPLICIT",
        notes="Explicit; not derived.",
    ),
    row(
        metric_code="TOTAL_EQUITY",
        source_presence="REPORTED",
        raw_source_label="Total equity",
        raw_source_value="20,321,570",
        normalized_value="20321570000",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1000",
        unit_dimension="MONETARY",
        page=6,
        evidence_text="SOFP BANK: Total equity 20,321,570 LKR '000.",
        evidence_level="CELL_EXPLICIT",
        notes="Uses Total equity line (equals attributable for Bank).",
    ),
    row(
        metric_code="NAVPS",
        source_presence="REPORTED",
        raw_source_label="Net asset value per share ( LKR )",
        raw_source_value="18.8",
        normalized_value="18.8",
        entity_scope="BANK",
        period_end="2025-12-31",
        duration_months=None,
        comparison_role="CURRENT",
        currency="LKR",
        scale="1",
        unit_dimension="PER_SHARE",
        page=6,
        evidence_text="SOFP BANK: Net asset value per share ( LKR ) 18.8.",
        evidence_level="CELL_EXPLICIT",
        notes="Per-share.",
    ),
]


def main() -> int:
    # verify SHA from manifest
    identity = json.loads(
        Path("tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    sha = next(it["pdf_sha256"] for it in identity["items"] if it["filing_version_id"] == FID)
    for r in ROWS:
        r["pdf_sha256"] = sha
    out = Path("outputs/n17_blind_partial/UBC.jsonl")
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ROWS) + "\n", encoding="utf-8")
    print("wrote", out, len(ROWS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
