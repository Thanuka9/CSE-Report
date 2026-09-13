"""Isolated V2 extraction and context-resolution core.

This package must not change V1 production behavior. Downstream V2 modules share
exactly one canonical document representation and require explicit source evidence.
"""

from __future__ import annotations

from typing import Final, Literal

SCHEMA_VERSION: Final[Literal["v2.0.0"]] = "v2.0.0"
PARSER_NAME_NATIVE = "v2.native_pymupdf"
PARSER_VERSION_NATIVE = "1.0.0"
PARSER_NAME_OCR = "v2.ocr.tesseract"
PARSER_VERSION_OCR = "1.0.0"

__all__ = [
    "PARSER_NAME_NATIVE",
    "PARSER_NAME_OCR",
    "PARSER_VERSION_NATIVE",
    "PARSER_VERSION_OCR",
    "SCHEMA_VERSION",
]
