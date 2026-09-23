from __future__ import annotations

from pathlib import Path

from cse_financial_etl.v2.contracts.investigation import SOURCE_TARGET_METRICS
from cse_financial_etl.v2.taxonomy.registry import load_registry


def test_truth_contract_covers_registry_source_targets() -> None:
    root = Path(__file__).resolve().parents[3]
    text = (root / "docs" / "v2" / "SOURCE_METRIC_TRUTH_CONTRACT.md").read_text(encoding="utf-8")
    registry = load_registry()
    for code in SOURCE_TARGET_METRICS:
        assert code in text
        concept = registry.get(code)
        assert concept.source_only is True
        assert concept.derivation_allowed is False
    assert "PUBLICATION POLICY" in text
    assert "SOURCE TRUTH" in text
    assert "Never convert GROUP → COMPANY" in text or "Never convert GROUP" in text
    assert "TOTAL_LIABILITIES" in text
    assert "EBITDA" in text
    assert "No FX conversion" in text
    assert "cents/share" in text
    assert "0.01" in text
    assert "attributable to owners" in text.casefold()
    assert "Gross income" in text
    assert "Interest income" in text
    assert "OPEN before adjudication" not in text
    assert "**OPEN:**" not in text
