"""Versioned native geometry cache. Accounting decisions are always recomputed."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

from cse_financial_etl.document.document_ir import (
    BBox,
    CanonicalDocumentIR,
    DocumentQuality,
    LineIR,
    PageIR,
    TokenIR,
    sha256_file,
)
from cse_financial_etl.storage.stage_cache import StageCache, cache_key


def _decode(payload: dict[str, Any], source: Path, digest: str) -> CanonicalDocumentIR:
    if payload["source_sha256"] != digest:
        raise ValueError("cache source mismatch")
    def token(raw: dict[str, Any]) -> TokenIR:
        return TokenIR(**{**raw, "bbox": BBox(**raw["bbox"])})
    pages = []
    for raw in payload["pages"]:
        if raw.get("tables"):
            raise ValueError("native cache cannot contain accounting tables")
        lines = tuple(LineIR(**{**line, "bbox": BBox(**line["bbox"]),
            "tokens": tuple(token(t) for t in line["tokens"])}) for line in raw["lines"])
        pages.append(PageIR(raw["page_number"], raw["width"], raw["height"],
            tuple(token(t) for t in raw["tokens"]), lines))
    quality = dict(payload["quality"])
    quality["reconstruction_gaps"] = tuple(quality.get("reconstruction_gaps", ()))
    return CanonicalDocumentIR(tuple(pages), DocumentQuality(**quality), digest, str(source))


def cached_native_document(pdf_path: Path) -> CanonicalDocumentIR:
    from cse_financial_etl.document import document_ir as canonical
    from cse_financial_etl.documents import document_ir as legacy
    from cse_financial_etl.ingestion import native_pdf
    from cse_financial_etl.ingestion.native_pdf import extract_native_document

    digest = sha256_file(pdf_path)
    implementation = hashlib.sha256(b"".join(Path(str(module.__file__)).read_bytes()
        for module in (legacy, canonical, native_pdf))).hexdigest()
    key = cache_key(source_sha256=digest, stage="native_geometry_v1", versions={
        "implementation": implementation, "pymupdf": version("PyMuPDF"),
        "pdfplumber": version("pdfplumber")})
    cache = StageCache(pdf_path.parent / ".stage_cache")
    payload = cache.get_json(key)
    if payload is not None:
        try:
            return _decode(payload, pdf_path, digest)
        except (KeyError, TypeError, ValueError):
            pass  # Corrupt/stale cache is recomputed from the PDF.
    document = extract_native_document(pdf_path)
    cache.put_json(key, asdict(document))
    return document
