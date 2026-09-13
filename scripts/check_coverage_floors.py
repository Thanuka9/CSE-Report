#!/usr/bin/env python3
"""Reject unauthorized reductions in configs/coverage_baseline.yml.

Does not modify the historical floor. Raising floors is allowed. Lowering
requires a complete ACKNOWLEDGED_REGRESSION governance record.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from cse_financial_etl.v2.exceptions import UnauthorizedCoverageFloorReduction
from cse_financial_etl.v2.governance.coverage_floors import (
    assert_coverage_floors_not_lowered,
    load_yaml_mapping,
)


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root (pyproject.toml)")


def _git_show(root: Path, git_ref: str, relpath: str) -> dict[str, object] | None:
    result = subprocess.run(
        ["git", "show", f"{git_ref}:{relpath}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    loaded = yaml.safe_load(result.stdout)
    return loaded if isinstance(loaded, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current",
        type=Path,
        default=None,
        help="Path to the current coverage_baseline.yml",
    )
    parser.add_argument(
        "--previous",
        type=Path,
        default=None,
        help="Path to a previous coverage_baseline.yml (PR/base snapshot)",
    )
    parser.add_argument(
        "--git-base",
        default=None,
        help="Git ref whose coverage_baseline.yml is the previous floor",
    )
    parser.add_argument(
        "--governance",
        type=Path,
        default=None,
        help="Optional ACKNOWLEDGED_REGRESSION record YAML",
    )
    args = parser.parse_args(argv)
    root = _project_root()
    current_path = args.current or (root / "configs" / "coverage_baseline.yml")
    current = load_yaml_mapping(current_path)
    previous = load_yaml_mapping(args.previous) if args.previous is not None else None
    if previous is None and args.git_base:
        previous = _git_show(root, args.git_base, "configs/coverage_baseline.yml")
    governance: object | None = None
    governance_path = args.governance or (root / "configs" / "coverage_floor_governance.yml")
    if governance_path.exists():
        governance = yaml.safe_load(governance_path.read_text(encoding="utf-8"))
    try:
        report = assert_coverage_floors_not_lowered(
            current=current,
            previous=previous,
            governance=governance,
        )
    except UnauthorizedCoverageFloorReduction as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if report.authorized:
        print(
            "authorized coverage-floor exceptions: "
            + ", ".join(item.path for item in report.authorized)
        )
    print("coverage floors: no unauthorized reductions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
