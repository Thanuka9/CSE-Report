#!/usr/bin/env python3
"""Fixed-input replay/diff skeleton (V2 Phase 0).

Pins runtime metadata and diffs fact populations by identity. This does not
run the V1 pipeline and does not gate V2 implementation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.diagnostics.replay import collect_runtime_pin, replay_fact_diff


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root (pyproject.toml)")


def _load_facts(path: Path | None) -> tuple[dict[str, Any], ...]:
    if path is None or not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return tuple(item for item in payload if isinstance(item, dict))
    if isinstance(payload, dict) and isinstance(payload.get("facts"), list):
        return tuple(item for item in payload["facts"] if isinstance(item, dict))
    raise SystemExit(f"{path} must be a JSON list of facts or an object with a facts array")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-facts", type=Path, default=None)
    parser.add_argument("--current-facts", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    root = _project_root()
    pin = collect_runtime_pin(root)
    diff = replay_fact_diff(_load_facts(args.reference_facts), _load_facts(args.current_facts))
    report = {
        "runtime_pin": pin.model_dump(),
        "fact_diff": diff,
        "note": "Replay A/B determinism and historical-vs-current attribution are later Phase 28 steps.",
    }
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
