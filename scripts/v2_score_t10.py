"""Score V2 SourceFacts against committed T10 items. Does not author truth."""

from __future__ import annotations

import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.investigation_freeze import collect_investigation_freeze
from cse_financial_etl.v2.diagnostics.t10_score import score_t10_filings


def _root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root")


def main() -> int:
    root = _root()
    freeze = collect_investigation_freeze(root)
    payload = score_t10_filings(root)
    payload["investigation_base_sha"] = freeze.investigation_base_sha
    payload["actual_code_sha"] = freeze.actual_code_sha
    out = root / "tests" / "v2" / "universe" / "t10_score.json"
    compact = {key: value for key, value in payload.items() if key != "details"}
    compact["mismatch_examples"] = [
        row
        for row in payload["details"]
        if row["result"] in {"VALUE_OR_ENTITY_MISMATCH", "FN", "G01_WITHHELD"}
    ]
    out.write_text(json.dumps(compact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
