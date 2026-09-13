FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --extra ocr

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["cse-etl"]
