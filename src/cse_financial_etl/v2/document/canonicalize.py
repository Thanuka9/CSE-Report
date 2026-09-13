"""Build CanonicalDocument from parser-neutral page/token inputs."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalPage
from cse_financial_etl.v2.exceptions import NativeParseError


def canonicalize_document(
    *,
    filing_version_id: str,
    source_sha256: str,
    pages: tuple[CanonicalPage, ...],
    parser_manifest: dict[str, str],
) -> CanonicalDocument:
    if not pages:
        raise NativeParseError("native parse produced no pages")
    return CanonicalDocument(
        filing_version_id=filing_version_id,
        source_sha256=source_sha256,
        pages=pages,
        parser_manifest=dict(sorted(parser_manifest.items())),
    )
