#!/usr/bin/env sh
set -eu
command -v uv >/dev/null 2>&1 || {
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
}
uv python install 3.12
uv sync
uv run pytest
uv run ruff check src tests
command -v pdftotext >/dev/null 2>&1 || \
  echo "Warning: Poppler pdftotext is missing; pypdf fallback accuracy may be lower." >&2
