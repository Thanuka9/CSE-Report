"""Document quality features used for routing. Diagnostic only; not publication truth."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalToken

NUMERIC_TOKEN_RE = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?%?$|^-$")


class DocumentQualityFeatures(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    page_count: int
    native_token_count: int
    numeric_token_count: int
    pages_with_text: int
    numeric_density: float
    empty_page_count: int
    mean_tokens_per_page: float


def is_numeric_token(token: CanonicalToken) -> bool:
    return NUMERIC_TOKEN_RE.fullmatch(token.text.replace(" ", "")) is not None


def measure_document_quality(document: CanonicalDocument) -> DocumentQualityFeatures:
    tokens = [token for page in document.pages for line in page.lines for token in line.tokens]
    numeric = sum(1 for token in tokens if is_numeric_token(token))
    pages_with_text = sum(1 for page in document.pages if any(page.lines))
    page_count = len(document.pages)
    token_count = len(tokens)
    return DocumentQualityFeatures(
        page_count=page_count,
        native_token_count=token_count,
        numeric_token_count=numeric,
        pages_with_text=pages_with_text,
        numeric_density=(numeric / token_count) if token_count else 0.0,
        empty_page_count=page_count - pages_with_text,
        mean_tokens_per_page=(token_count / page_count) if page_count else 0.0,
    )
