"""Select unseen HOLDOUT filings from filesystem identity only.

Do not parse PDF text, run V1/V2, or inspect statement content.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.diagnostics.real_filings import load_gold_lock, project_root

_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
HOLDOUT_COUNT = 12
HOLDOUT_PATH = Path("tests/v2/source_truth/holdout_manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _norm_name(value: str) -> str:
    return " ".join(value.replace("_", " ").replace(".", " ").split()).casefold()


def _issuer_lookup(root: Path) -> dict[str, dict[str, str]]:
    master = json.loads(
        (root / "data" / "master" / "issuer_security_master.json").read_text(encoding="utf-8")
    )
    lookup: dict[str, dict[str, str]] = {}
    for row in master.get("issuers") or ():
        if not isinstance(row, dict):
            continue
        symbols = [str(item) for item in row.get("symbols") or () if item]
        if not symbols:
            continue
        payload = {
            "symbol": symbols[0],
            "legal_name": str(row.get("legal_name") or ""),
            "issuer_type": str(row.get("issuer_type") or ""),
        }
        lookup[_norm_name(payload["legal_name"])] = payload
        lookup[_norm_name(symbols[0])] = payload
    return lookup


def select_unseen_holdout(
    *,
    root: Path | None = None,
    count: int = HOLDOUT_COUNT,
) -> list[dict[str, Any]]:
    root = root or project_root()
    lock = load_gold_lock(root=root)
    excluded = set(lock.scoring_symbols) | set(lock.regression_symbols) | set(
        lock.known_timeout_symbols
    )
    lookup = _issuer_lookup(root)
    filings = root / "data" / "raw" / "filings"
    candidates: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for pdf in sorted(filings.rglob("*.pdf")):
        issuer_dir = pdf.parent.name
        info = lookup.get(_norm_name(issuer_dir))
        if info is None:
            continue
        symbol = info["symbol"]
        if symbol in excluded or symbol in seen_symbols:
            continue
        match = _DATE_RE.search(pdf.name)
        try:
            local_file = pdf.relative_to(root).as_posix()
        except ValueError:
            local_file = pdf.as_posix()
        candidates.append(
            {
                "filing_version_id": f"{symbol}-{match.group(1) if match else pdf.stem}",
                "issuer_id": symbol,
                "symbol": symbol,
                "legal_name": info["legal_name"],
                "issuer_type": info["issuer_type"],
                "period": match.group(1) if match else None,
                "local_file": local_file,
                "pdf_sha256": _sha256(pdf),
                "file_size": pdf.stat().st_size,
            }
        )
        seen_symbols.add(symbol)
    ranked = sorted(
        candidates,
        key=lambda row: hashlib.sha256(
            f"{row['symbol']}|{row['local_file']}".encode()
        ).hexdigest(),
    )
    return ranked[:count]


def write_holdout_manifest(root: Path, path: Path | None = None) -> Path:
    rows = select_unseen_holdout(root=root)
    destination = path or (root / HOLDOUT_PATH)
    payload = {
        "note": (
            "Unseen HOLDOUT identity list. Existing locked 33 is DEV/regression. "
            "Do not inspect these PDFs or run extraction while developing rules."
        ),
        "investigation_base_sha": "91a9c68bf940d3d9c2a86245f127de88ad4b4b6d",
        "count": len(rows),
        "items": rows,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def write_source_truth_split(root: Path, path: Path | None = None) -> Path:
    lock = load_gold_lock(root=root)
    holdout = select_unseen_holdout(root=root)
    destination = path or (root / "tests" / "v2" / "source_truth" / "split.json")
    payload = {
        "note": (
            "Existing locked 33 is DEV/regression. HOLDOUT is a new unseen identity "
            "list. Do not inspect holdout PDFs or copy V1/V2 values. "
            "Adjudication_status is NOT_STARTED until blind review."
        ),
        "investigation_base_sha": "91a9c68bf940d3d9c2a86245f127de88ad4b4b6d",
        "dev": list(lock.scoring_symbols),
        "holdout": [row["symbol"] for row in holdout],
    }
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination
