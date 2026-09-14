from __future__ import annotations

from pathlib import Path

GATES = {
    "G01": "Required entity semantics",
    "G02": "Partial-context cascade",
    "G03": "Exact-quarter",
    "G04": "OTHER-page exclusion",
    "G05": "Continuation",
    "G06": "Source conflict withholding",
    "G07": "Collapsed rows",
    "G08": "Duplicate metric selection",
    "G09": "EPS entity inference",
}


def test_gate_decision_log_exists_and_is_untested() -> None:
    path = Path(__file__).resolve().parents[3] / "docs" / "v2" / "EXTRACTION_GATE_DECISIONS.md"
    text = path.read_text(encoding="utf-8")
    for gate_id, title in GATES.items():
        assert gate_id in text
        assert title.split()[0] in text or gate_id in text
    assert "UNTESTED" in text
    assert "KEEP" in text
    assert "Do not disable a gate only to" in text or "raise counts" in text
