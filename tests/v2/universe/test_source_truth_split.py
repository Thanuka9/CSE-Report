from __future__ import annotations

import json
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import AdjudicationStatus, EvidenceLevel, SourcePresence
from cse_financial_etl.v2.contracts.investigation import (
    DERIVED_METRICS,
    SOURCE_TARGET_METRICS,
    SourceTruthItem,
)
from cse_financial_etl.v2.diagnostics.real_filings import load_gold_lock

ROOT = Path(__file__).resolve().parents[3]
SPLIT_PATH = ROOT / "tests" / "v2" / "source_truth" / "split.json"
ITEMS_PATH = ROOT / "tests" / "v2" / "source_truth" / "items.jsonl"


def test_dev_holdout_queue_has_no_expected_values() -> None:
    payload = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    lock = load_gold_lock(root=ROOT)
    dev = payload["dev"]
    holdout = payload["holdout"]
    assert 20 <= len(dev) <= 25
    assert 10 <= len(holdout) <= 15
    assert not set(dev) & set(holdout)
    assert set(dev + holdout) == set(lock.scoring_symbols)
    assert "expected" not in payload
    assert "drop" not in payload
    assert ITEMS_PATH.read_text(encoding="utf-8").strip() == ""
    queue_path = ROOT / "tests" / "v2" / "source_truth" / "t10_review_queue.json"
    if queue_path.is_file():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        assert queue["items"]
        assert all("v1_value" not in item for item in queue["items"])
        assert all(item["source_truth_status"] == "NOT_ADJUDICATED" for item in queue["items"])
        assert ITEMS_PATH.read_text(encoding="utf-8").strip() == ""


def test_source_truth_item_is_source_not_policy() -> None:
    item = SourceTruthItem(
        filing_version_id="fv-1",
        pdf_sha256="a" * 64,
        issuer_id="JKH.N0000",
        metric_code="PAT",
        source_presence=SourcePresence.REPORTED,
        evidence_level=EvidenceLevel.CELL_EXPLICIT,
        adjudication_status=AdjudicationStatus.NOT_STARTED,
        split="DEV",
    )
    assert item.metric_code in SOURCE_TARGET_METRICS
    assert "ROE" in DERIVED_METRICS
    assert "LAST_TRADED_PRICE" not in SOURCE_TARGET_METRICS
