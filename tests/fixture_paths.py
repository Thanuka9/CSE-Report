"""Locate real-filing fixtures for regression tests (gap B8).

Resolution order:

1. ``tests/fixtures/pdf/<basename>`` — vendored copy committed to the repository.
2. ``data/raw/filings/<relative path>`` — the local filing lake (gitignored).

When neither exists the test is skipped with an explicit reason, unless the
environment variable ``CSE_REQUIRE_FIXTURES=1`` is set (CI), in which case the
missing fixture is a hard failure rather than a silent skip.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDORED_DIR = ROOT / "tests" / "fixtures" / "pdf"
LAKE_DIR = ROOT / "data" / "raw" / "filings"


def fixtures_required() -> bool:
    return os.environ.get("CSE_REQUIRE_FIXTURES", "").strip() in {"1", "true", "TRUE", "yes"}


def real_pdf(relative: str) -> Path:
    """Return the path of a real filing fixture, skipping (or failing in CI) when absent."""

    rel = Path(relative)
    candidates = [VENDORED_DIR / rel.name, VENDORED_DIR / rel, LAKE_DIR / rel]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    message = f"real filing fixture not present: {relative} (looked in {VENDORED_DIR} and {LAKE_DIR})"
    if fixtures_required():
        pytest.fail(message + "; CSE_REQUIRE_FIXTURES=1 forbids skipping")
    pytest.skip(message)
    raise AssertionError("unreachable")  # pragma: no cover
