.PHONY: setup test lint typecheck check run smoke

setup:
	uv sync --all-extras

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

check: lint typecheck test

run:
	uv run cse-etl run --project-root .

smoke:
	uv run cse-etl run --issuer-limit 4 --project-root .
