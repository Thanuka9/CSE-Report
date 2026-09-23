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
    assert len(dev) == 33
    assert 10 <= len(holdout) <= 15
    assert not set(dev) & set(holdout)
    assert set(dev) == set(lock.scoring_symbols)
    assert not set(holdout) & set(lock.scoring_symbols)
    assert "expected" not in payload
    assert "drop" not in payload
    queue_path = ROOT / "tests" / "v2" / "source_truth" / "t10_review_queue.json"
    if queue_path.is_file():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        items = queue.get("items", [])
        assert queue["item_count"] == len(items)
        assert "not source truth" in queue["note"].casefold()
        assert "not gold" in queue["note"].casefold()
        assert all("v1_value" not in item for item in items)
        assert all("v2_value" not in item for item in items)
        assert all(item["split"] == "DEV" for item in items)
        if not items:
            assert ITEMS_PATH.is_file()


def test_t10_items_are_blind_source_records() -> None:
    lines = [line for line in ITEMS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    holdout = set(json.loads(SPLIT_PATH.read_text(encoding="utf-8"))["holdout"])
    items = [SourceTruthItem.model_validate_json(line) for line in lines]
    assert len(items) == 64
    assert sum(1 for item in items if item.split == "DEV") == 40
    assert sum(1 for item in items if item.split == "HOLDOUT") == 24
    for item in items:
        dumped = item.model_dump(mode="json")
        assert "v1_value" not in dumped
        assert "v2_value" not in dumped
        assert item.split in {"DEV", "HOLDOUT"}
        if item.split == "DEV":
            assert item.issuer_id not in holdout
        else:
            assert item.issuer_id in holdout
        assert item.metric_code in SOURCE_TARGET_METRICS
        assert item.source_presence.value in {"REPORTED", "NOT_REPORTED", "AMBIGUOUS"}
        assert item.adjudication_status.value == "REVIEWER_1_COMPLETE"


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


def test_unseen_holdout_is_identity_only() -> None:
    path = ROOT / "tests" / "v2" / "source_truth" / "holdout_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["items"]
    assert 10 <= len(items) <= 15
    lock = load_gold_lock(root=ROOT)
    symbols = {item["symbol"] for item in items}
    assert not symbols & set(lock.scoring_symbols)
    for item in items:
        assert len(item["pdf_sha256"]) == 64
        assert "v1_value" not in item
        assert "v2_value" not in item
        assert "normalized_value" not in item
        assert not str(item["local_file"]).startswith("D:")
