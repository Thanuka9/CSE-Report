"""Resolve a complete generation through one atomically replaced pointer."""
from __future__ import annotations

import json
from pathlib import Path

from cse_financial_etl.storage.stage_cache import atomic_write_text


def current_gold_dir(data_root: Path) -> Path:
    gold = data_root / "gold"
    pointer = gold / "CURRENT.json"
    if not pointer.exists():
        return gold  # pre-migration read compatibility
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    generation = str(payload["generation"])
    if Path(generation).name != generation or generation in {".", ".."}:
        raise ValueError("invalid gold generation")
    snapshot = gold / "snapshots" / generation
    if not snapshot.is_dir():
        raise FileNotFoundError(f"gold generation missing: {generation}")
    return snapshot


def activate_gold_snapshot(data_root: Path, generation: str) -> None:
    if Path(generation).name != generation or generation in {".", ".."}:
        raise ValueError("invalid gold generation")
    snapshot = data_root / "gold" / "snapshots" / generation
    required = ("current_financial_facts.parquet", "current_market_prices.parquet",
                "extraction_coverage.parquet", "accuracy_certainty.parquet")
    if not all((snapshot / name).is_file() for name in required):
        raise ValueError("incomplete gold generation")
    atomic_write_text(data_root / "gold" / "CURRENT.json", json.dumps({"generation": generation}))
