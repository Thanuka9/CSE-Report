"""Regenerate freeze, locked baseline, experiments, and ranking from one freeze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.baseline import (
    build_locked_source_manifest,
    run_locked_baseline,
)
from cse_financial_etl.v2.diagnostics.canonical_outputs import write_json
from cse_financial_etl.v2.diagnostics.experiments import (
    build_defect_ranking,
    run_locked_experiments,
)
from cse_financial_etl.v2.diagnostics.investigation_freeze import (
    collect_investigation_freeze,
    freeze_run_identity,
    write_investigation_freeze,
)


def _root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-v1", action="store_true")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    root = _root()
    baseline_out = root / "outputs" / "v2_extraction_baseline"
    experiment_out = root / "outputs" / "v2_extraction_experiments"
    manifest = build_locked_source_manifest(root)
    (root / "tests" / "v2" / "universe" / "locked_source_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    freeze = collect_investigation_freeze(root)
    write_investigation_freeze(root, freeze=freeze)
    identity = freeze_run_identity(freeze, run_id=f"locked-baseline-{freeze.actual_code_sha}")
    baseline_out.mkdir(parents=True, exist_ok=True)
    write_json(baseline_out / "source_manifest.json", {"identity": identity, "items": manifest})
    summary = run_locked_baseline(
        root=root,
        out_dir=baseline_out,
        include_v1=not args.skip_v1,
        limit=args.limit,
        freeze=freeze,
    )
    compact = {
        key: value for key, value in summary.items() if key not in {"filings", "regime_audit"}
    }
    compact["mixed_native_ocr_case_ids"] = [
        item["case_id"] for item in summary.get("filings", []) if item.get("mixed_native_ocr")
    ]
    write_json(root / "tests" / "v2" / "universe" / "baseline_run_summary.json", compact)
    result = run_locked_experiments(
        root=root,
        out_dir=experiment_out,
        ledger_dir=baseline_out,
        split_path=root / "tests" / "v2" / "source_truth" / "split.json",
        limit=args.limit,
        freeze=freeze,
    )
    write_json(root / "tests" / "v2" / "universe" / "experiment_summary.json", result["summary"])
    write_json(root / "tests" / "v2" / "source_truth" / "t10_review_queue.json", result["t10"])
    report = (experiment_out / "extraction_report.md").read_text(encoding="utf-8")
    (root / "docs" / "v2" / "EXTRACTION_REPORT.md").write_text(report, encoding="utf-8")
    ranking = build_defect_ranking(compact, freeze=freeze)
    write_json(root / "tests" / "v2" / "universe" / "defect_family_ranking.json", ranking)
    print(json.dumps({"actual_code_sha": freeze.actual_code_sha, "baseline": compact}, indent=2))
    return 0 if summary.get("all_deterministic") else 2


if __name__ == "__main__":
    raise SystemExit(main())
