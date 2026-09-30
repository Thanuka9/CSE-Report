#!/usr/bin/env python3
"""Download the exact official CSE PDFs that back the 100-issuer gold QA set.

This is a review-support utility only. It does not change verification_status,
review decisions, release mode, or the production extraction engine.
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "reports" / "gold_gate" / "manual_qa_adjudication_queue.csv"
GOLD = ROOT / "tests" / "fixtures" / "golden_financial_facts.json"
OUT_DIR = ROOT / "reports" / "gold_gate" / "manual_qa_source_pdfs"
ZIP_PATH = ROOT / "reports" / "gold_gate" / "manual_qa_source_bundle.zip"
MANIFEST = OUT_DIR / "source_manifest.json"
CDN_ROOT = "https://cdn.cse.lk/cmt/upload_report_file/"
USER_AGENT = "CSE-Financial-Data-Platform/1.0 (+public regulatory research)"


def source_name(pdf_path: str) -> str:
    name = Path(pdf_path).name
    parts = name.split("_", 1)
    if len(parts) != 2 or len(parts[0]) != 10:
        raise ValueError(f"unexpected queued PDF name: {name}")
    return parts[1]


def download(url: str, destination: Path) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                content_type = response.headers.get("Content-Type", "")
            if not payload.startswith(b"%PDF") and "pdf" not in content_type.lower():
                raise ValueError(f"not a PDF: content-type={content_type!r}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            return len(payload), hashlib.sha256(payload).hexdigest()
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"download failed: {url}: {last_error}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with QUEUE.open("r", encoding="utf-8-sig", newline="") as handle:
        pending = list(csv.DictReader(handle))
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    existing_manual = [
        item for item in gold if item.get("verification_status") == "MANUAL_QA"
    ]

    entries: list[dict[str, str]] = []
    seen_symbols: set[str] = set()

    for row in pending:
        symbol = row["symbol"]
        seen_symbols.add(symbol)
        entries.append(
            {
                "symbol": symbol,
                "issuer_name": row["issuer_name"],
                "period_end": row["period_end"],
                "pdf": row["pdf"],
                "prior_status": row["current_verification_status"],
            }
        )
    for item in existing_manual:
        symbol = str(item["symbol"])
        if symbol in seen_symbols:
            continue
        entries.append(
            {
                "symbol": symbol,
                "issuer_name": str(item["issuer_name"]),
                "period_end": str(item["period_end"]),
                "pdf": str(item["pdf"]),
                "prior_status": "MANUAL_QA",
            }
        )
        seen_symbols.add(symbol)

    if len(entries) != 100:
        raise RuntimeError(f"expected 100 unique issuers, got {len(entries)}")

    manifest: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for index, entry in enumerate(entries, start=1):
        original = source_name(entry["pdf"])
        encoded = urllib.parse.quote(original, safe="._-()")
        url = CDN_ROOT + encoded
        safe_symbol = entry["symbol"].replace(".", "_")
        destination = OUT_DIR / f"{index:03d}_{safe_symbol}_{original}"
        try:
            size, digest = download(url, destination)
            manifest.append(
                {
                    **entry,
                    "review_index": index,
                    "source_url": url,
                    "downloaded_path": str(destination.relative_to(ROOT)),
                    "size_bytes": size,
                    "sha256": digest,
                    "download_status": "OK",
                }
            )
            print(f"{index:03d}/100 OK {entry['symbol']} {size:,} bytes")
        except Exception as exc:
            failures.append(
                {
                    **entry,
                    "review_index": str(index),
                    "source_url": url,
                    "error": str(exc),
                }
            )
            print(f"{index:03d}/100 FAIL {entry['symbol']}: {exc}")

    MANIFEST.write_text(
        json.dumps(
            {
                "issuer_count": len(entries),
                "downloaded_count": len(manifest),
                "failure_count": len(failures),
                "files": manifest,
                "failures": failures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if failures:
        (OUT_DIR / "download_failures.json").write_text(
            json.dumps(failures, indent=2), encoding="utf-8"
        )

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(ROOT / "reports" / "gold_gate"))

    print(f"bundle={ZIP_PATH}")
    print(f"downloaded={len(manifest)}/100 failures={len(failures)}")
    if len(manifest) < 95:
        raise RuntimeError("source bundle incomplete: fewer than 95 PDFs downloaded")


if __name__ == "__main__":
    main()
