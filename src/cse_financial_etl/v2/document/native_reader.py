"""Deterministic PyMuPDF → CanonicalDocument. No financial concept mapping."""

from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pymupdf as fitz

from cse_financial_etl.v2 import PARSER_NAME_NATIVE, PARSER_VERSION_NATIVE, SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import (
    CanonicalDocument,
    CanonicalLine,
    CanonicalPage,
    CanonicalToken,
    line_bbox_from_tokens,
)
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.canonicalize import canonicalize_document
from cse_financial_etl.v2.exceptions import NativeParseError

# Visual-baseline clustering reconstructs rows that PDF emitters split across blocks.
# This is geometry, not financial interpretation.
_BASELINE_WINDOW = 4
_MIN_TOLERANCE = 2.2
_MAX_TOKEN_HEIGHT = 12.0
_HEIGHT_TOLERANCE = 0.28


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cluster_tokens(tokens: list[CanonicalToken], *, page_number: int) -> tuple[CanonicalLine, ...]:
    if not tokens:
        return ()
    rows: list[list[CanonicalToken]] = []
    centres: list[float] = []
    for token in sorted(tokens, key=lambda item: (item.center_y, item.bbox[0], item.text)):
        best_index: int | None = None
        best_distance = float("inf")
        height = token.bbox[3] - token.bbox[1]
        tolerance = max(_MIN_TOLERANCE, min(height, _MAX_TOKEN_HEIGHT) * _HEIGHT_TOLERANCE)
        start = max(0, len(rows) - _BASELINE_WINDOW)
        for index in range(start, len(rows)):
            distance = abs(token.center_y - centres[index])
            if distance <= tolerance and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is None:
            rows.append([token])
            centres.append(token.center_y)
        else:
            rows[best_index].append(token)
            centres[best_index] = sum(item.center_y for item in rows[best_index]) / len(
                rows[best_index]
            )

    lines: list[CanonicalLine] = []
    for row_index, row_tokens in enumerate(rows):
        ordered = tuple(sorted(row_tokens, key=lambda item: (item.bbox[0], item.text)))
        lines.append(
            CanonicalLine(
                line_id=f"p{page_number}:l{row_index:04d}",
                tokens=ordered,
                bbox=line_bbox_from_tokens(ordered),
            )
        )
    lines.sort(key=lambda line: (round(line.bbox[1], 3), line.bbox[0], line.line_id))
    return tuple(lines)


def _page_tokens(page: Any, *, page_number: int) -> list[CanonicalToken]:
    words = page.get_text("words", sort=True)
    tokens: list[CanonicalToken] = []
    for item in words:
        if len(item) < 5:
            continue
        text = str(item[4]).strip()
        if not text:
            continue
        x0, y0, x1, y1 = (float(item[0]), float(item[1]), float(item[2]), float(item[3]))
        tokens.append(
            CanonicalToken(
                text=text,
                page_number=page_number,
                bbox=(x0, y0, x1, y1),
                confidence=None,
                source_parser=PARSER_NAME_NATIVE,
            )
        )
    return tokens


def read_native_pdf(pdf_path: Path, *, filing_version_id: str) -> CanonicalDocument:
    """Parse a native PDF into the single V2 CanonicalDocument representation."""

    if not pdf_path.is_file():
        raise NativeParseError(f"PDF does not exist: {pdf_path}")
    source_sha256 = sha256_file(pdf_path)
    pages: list[CanonicalPage] = []
    try:
        with fitz.open(pdf_path) as document:  # type: ignore[no-untyped-call]
            page_count = int(document.page_count)
            if page_count < 1:
                raise NativeParseError("PDF contains no pages")
            for index in range(1, page_count + 1):
                page = document.load_page(index - 1)
                rect = page.rect
                tokens = _page_tokens(page, page_number=index)
                pages.append(
                    CanonicalPage(
                        page_number=index,
                        width=float(rect.width),
                        height=float(rect.height),
                        lines=_cluster_tokens(tokens, page_number=index),
                        extraction_mode=ExtractionMode.NATIVE,
                    )
                )
    except NativeParseError:
        raise
    except Exception as exc:
        raise NativeParseError(f"PyMuPDF failed to parse {pdf_path}: {exc}") from exc

    return canonicalize_document(
        filing_version_id=filing_version_id,
        source_sha256=source_sha256,
        pages=tuple(pages),
        parser_manifest={
            "schema_version": SCHEMA_VERSION,
            "parser_name": PARSER_NAME_NATIVE,
            "parser_version": PARSER_VERSION_NATIVE,
            "pymupdf_version": version("PyMuPDF"),
            "extraction_mode": ExtractionMode.NATIVE.value,
        },
    )
