from __future__ import annotations

import pytest

from cse_financial_etl.v2.diagnostics.universe import (
    default_v1_snapshot,
    load_universe_pin,
    overlapping_pdfs_from_snapshot,
    shadow_v1_csv_against_v2,
)


def test_universe_pin_is_not_september_10_frozen() -> None:
    pin = load_universe_pin()
    assert pin["not_frozen_september_10"] is True
    assert "2026-09-05" in str(pin["relative_path"])
    assert "september-10" in str(pin["note"]).casefold() or "September-10" in str(pin["note"])


def test_v1_snapshot_shadows_against_v2_on_overlapping_pdfs() -> None:
    snapshot = default_v1_snapshot()
    if snapshot is None:
        pytest.skip("V1 normalized_facts snapshot is not present")
    assert snapshot.name == "normalized_facts_2026-09-05.csv"
    pdfs = overlapping_pdfs_from_snapshot(snapshot, limit=3)
    if len(pdfs) < 2:
        pytest.skip("overlapping real PDFs are not present")
    report = shadow_v1_csv_against_v2(snapshot, pdfs, limit=3)
    counts = report["counts"]
    assert isinstance(counts, dict)
    assert sum(int(value) for value in counts.values()) >= 1
    assert "by_metric" in report
    assert "by_issuer" in report
