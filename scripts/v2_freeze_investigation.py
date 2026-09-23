"""Write the investigation runtime freeze JSON."""

from __future__ import annotations

from pathlib import Path

from cse_financial_etl.v2.diagnostics.investigation_freeze import write_investigation_freeze


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = write_investigation_freeze(root)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
