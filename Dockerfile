FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir uv && uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["cse-etl"]
