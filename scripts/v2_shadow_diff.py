#!/usr/bin/env python3
"""Fact-identity shadow diff for V1 vs V2 frozen-universe JSON payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.diagnostics.shadow import shadow_diff


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root (pyproject.toml)")


def _load_facts(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return tuple(item for item in payload if isinstance(item, dict))
    if isinstance(payload, dict) and isinstance(payload.get("facts"), list):
        return tuple(item for item in payload["facts"] if isinstance(item, dict))
    raise SystemExit(f"{path} must be a JSON list of facts or an object with a facts array")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-facts", type=Path, required=True)
    parser.add_argument("--current-facts", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    _project_root()
    report = shadow_diff(_load_facts(args.reference_facts), _load_facts(args.current_facts))
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
