"""T05-T19 diagnostic experiments on the locked 33. Does not change production."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.experiments import run_locked_experiments
from cse_financial_etl.v2.diagnostics.investigation_freeze import collect_investigation_freeze


def _root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    root = _root()
    out = args.out or (root / "outputs" / "v2_extraction_experiments")
    result = run_locked_experiments(
        root=root,
        out_dir=out,
        ledger_dir=root / "outputs" / "v2_extraction_baseline",
        split_path=root / "tests" / "v2" / "source_truth" / "split.json",
        limit=args.limit,
        freeze=collect_investigation_freeze(root),
    )
    summary = result["summary"]
    (root / "tests" / "v2" / "universe" / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    t10_path = root / "tests" / "v2" / "source_truth" / "t10_review_queue.json"
    t10_path.write_text(json.dumps(result["t10"], indent=2) + "\n", encoding="utf-8")
    report = out / "extraction_report.md"
    committed_report = root / "docs" / "v2" / "EXTRACTION_REPORT.md"
    committed_report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
