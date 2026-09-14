"""T05-T19 extraction investigation runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.baseline import (
    build_locked_source_manifest,
    run_locked_baseline,
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
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default outputs/v2_extraction_baseline)",
    )
    args = parser.parse_args(argv)
    root = _root()
    out = args.out or (root / "outputs" / "v2_extraction_baseline")
    manifest = build_locked_source_manifest(root)
    (out).mkdir(parents=True, exist_ok=True)
    (out / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    summary = run_locked_baseline(
        root=root,
        out_dir=out,
        include_v1=not args.skip_v1,
        limit=args.limit,
    )
    committed = root / "tests" / "v2" / "universe" / "locked_source_manifest.json"
    committed.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    compact = {key: value for key, value in summary.items() if key not in {"filings", "regime_audit"}}
    compact["mixed_native_ocr_case_ids"] = [
        item["case_id"] for item in summary.get("filings", []) if item.get("mixed_native_ocr")
    ]
    (root / "tests" / "v2" / "universe" / "baseline_run_summary.json").write_text(
        json.dumps(compact, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(compact, indent=2))
    return 0 if summary.get("all_deterministic") else 2


if __name__ == "__main__":
    raise SystemExit(main())
