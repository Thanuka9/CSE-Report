"""CLI wrapper for the production universe-acceptance contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cse_financial_etl.validation.universe_acceptance import evaluate_universe_acceptance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = evaluate_universe_acceptance(
        manifest_path=args.manifest,
        review_path=args.review,
        facts_path=args.facts,
        errors_path=args.errors,
        baseline_path=args.baseline,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["acceptance"] != "ENGINEERING_FAILURES_PRESENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
