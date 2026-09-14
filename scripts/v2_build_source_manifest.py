"""Build source_manifest.parquet from the local filing lake.

V1 and V2 comparison runs must use this SHA set. The parquet itself is an
investigation artefact under outputs/ and is gitignored.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from cse_financial_etl.v2.contracts.investigation import SourceManifestRow

_PERIOD_PREFIX = re.compile(r"^(?P<period>\d{4}-\d{2}-\d{2})_")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _page_count(path: Path) -> int | None:
    try:
        import fitz
    except Exception:
        return None
    try:
        with fitz.open(path) as document:
            return int(document.page_count)
    except Exception:
        return None


def iter_filing_pdfs(lake: Path) -> list[Path]:
    return sorted(path for path in lake.rglob("*.pdf") if path.is_file())


def build_source_manifest(project_root: Path) -> list[SourceManifestRow]:
    lake = project_root / "data" / "raw" / "filings"
    rows: list[SourceManifestRow] = []
    for path in iter_filing_pdfs(lake):
        relative = path.relative_to(project_root).as_posix()
        period = None
        match = _PERIOD_PREFIX.match(path.name)
        if match is not None:
            period = date.fromisoformat(match.group("period"))
        issuer_folder = path.parent.name
        symbol = ""
        rows.append(
            SourceManifestRow(
                filing_version_id=f"{issuer_folder}/{path.name}",
                issuer_id=issuer_folder,
                symbol=symbol,
                period=period,
                local_file=relative,
                pdf_sha256=_sha256(path),
                file_size=path.stat().st_size,
                page_count=_page_count(path),
                source_acquisition_timestamp=datetime.fromtimestamp(
                    path.stat().st_mtime, tz=UTC
                ).isoformat(),
                revision_identifier=path.name,
            )
        )
    return rows


def write_source_manifest(project_root: Path, destination: Path | None = None) -> Path:
    rows = build_source_manifest(project_root)
    path = destination or (
        project_root / "outputs" / "v2_extraction_baseline" / "source_manifest.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [row.model_dump(mode="json") for row in rows]
    pl.DataFrame(payload).write_parquet(path)
    sha_list = path.with_name("source_manifest_sha256s.json")
    sha_list.write_text(
        json.dumps(
            [{"pdf_sha256": row.pdf_sha256, "local_file": row.local_file} for row in rows],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = write_source_manifest(root)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
