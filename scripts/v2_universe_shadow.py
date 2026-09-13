#!/usr/bin/env python3
"""Shadow V1 snapshot CSV facts against V2 on overlapping local PDFs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.universe import (
    default_v1_snapshot,
    load_universe_pin,
    overlapping_pdfs_from_snapshot,
    shadow_v1_csv_against_v2,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-csv", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    snapshot = args.reference_csv or default_v1_snapshot()
    if snapshot is None or not snapshot.is_file():
        raise SystemExit("V1 snapshot CSV not found")
    pdfs = overlapping_pdfs_from_snapshot(snapshot, limit=args.limit)
    report = shadow_v1_csv_against_v2(snapshot, pdfs, limit=args.limit)
    pin = load_universe_pin()
    payload = {
        "reference_csv": str(snapshot),
        "snapshot_id": pin.get("snapshot_id"),
        "pdf_count": len(pdfs),
        "pdfs": {name: str(path) for name, path in pdfs.items()},
        "report": report,
        "note": pin.get("note"),
        "not_frozen_september_10": pin.get("not_frozen_september_10"),
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
