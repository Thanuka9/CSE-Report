"""Build the post-hardening consolidated CSE review workbook."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from cse_financial_etl.reporting.final_workbook import build_final_workbook


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the final consolidated CSE workbook.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--as-of", required=True, help="Run observation date YYYY-MM-DD")
    args = parser.parse_args()

    path = build_final_workbook(args.project_root, date.fromisoformat(args.as_of))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
