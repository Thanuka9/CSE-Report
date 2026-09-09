$ErrorActionPreference = "Stop"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/"
}

uv python install 3.12
uv sync --locked --group dev
uv run pytest
uv run ruff check src
uv run mypy src

if (-not (Get-Command pdftotext -ErrorAction SilentlyContinue)) {
    Write-Warning "Poppler pdftotext was not found. The pypdf fallback works, but table-column accuracy may be lower."
}
