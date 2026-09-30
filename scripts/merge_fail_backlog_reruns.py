"""Merge fail-backlog rerun JSON files, preferring later matches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOSSIER = ROOT / "reports" / "gold_gate"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=DOSSIER / "fail_backlog_rerun_merged.json",
    )
    args = parser.parse_args()
    by_key: dict[tuple[str, str], dict] = {}
    for path in args.inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("rows") or []:
            key = (str(row["symbol"]), str(row["metric_code"]))
            previous = by_key.get(key)
            if previous and previous.get("match") and not row.get("match"):
                continue
            by_key[key] = row
    rows = list(by_key.values())
    matched = sum(1 for row in rows if row.get("match"))
    summary = {
        "compared": len(rows),
        "matched": matched,
        "still_fail": len(rows) - matched,
        "issuers": len({row["symbol"] for row in rows}),
        "rows": rows,
        "sources": [str(path) for path in args.inputs],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "compared": summary["compared"],
                "matched": summary["matched"],
                "still_fail": summary["still_fail"],
                "out": str(args.out),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
