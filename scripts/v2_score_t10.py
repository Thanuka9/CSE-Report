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


def _write_score(root: Path, *, split: str, out_name: str) -> dict:
    freeze = collect_investigation_freeze(root)
    payload = score_t10_filings(root, split=split)
    payload["investigation_base_sha"] = freeze.investigation_base_sha
    payload["actual_code_sha"] = freeze.actual_code_sha
    compact = {key: value for key, value in payload.items() if key != "details"}
    compact["mismatch_examples"] = [
        row
        for row in payload["details"]
        if row["result"] in {"VALUE_OR_ENTITY_MISMATCH", "FN", "G01_WITHHELD"}
    ]
    out = root / "tests" / "v2" / "universe" / out_name
    out.write_text(json.dumps(compact, indent=2) + "\n", encoding="utf-8")
    return compact


def main() -> int:
    root = _root()
    t10 = _write_score(root, split="DEV", out_name="t10_score.json")
    t25 = _write_score(root, split="HOLDOUT", out_name="t25_holdout_score.json")
    print(json.dumps({"t10_dev": t10, "t25_holdout": t25}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
