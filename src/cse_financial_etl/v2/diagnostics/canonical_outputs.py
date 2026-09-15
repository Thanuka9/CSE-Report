"""Write canonical investigation artefacts with a shared run identity."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import polars as pl

from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.diagnostics.serialization import (
    derived_fact_to_mapping,
    source_fact_to_mapping,
)


def stamp_identity(
    rows: Sequence[Mapping[str, Any]], identity: Mapping[str, str]
) -> list[dict[str, Any]]:
    return [{**identity, **dict(row)} for row in rows]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")


def write_parquet(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        for key, value in payload.items():
            if value is None:
                payload[key] = ""
            elif isinstance(value, (list, tuple, dict)):
                payload[key] = json.dumps(value, default=str)
        prepared.append(payload)
    frame = (
        pl.DataFrame(prepared, infer_schema_length=max(len(prepared), 1))
        if prepared
        else pl.DataFrame({"run_id": []})
    )
    frame.write_parquet(path)


def fact_rows(
    facts: Sequence[SourceFact | DerivedFact],
    identity: Mapping[str, str],
    *,
    selected: bool | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fact in facts:
        if isinstance(fact, SourceFact):
            payload = source_fact_to_mapping(fact)
            payload["fact_id"] = fact.fact_id
            payload["fact_kind"] = "source"
        else:
            payload = derived_fact_to_mapping(fact)
            payload["fact_id"] = fact.fact_id
        if selected is not None:
            payload["production_selected"] = selected
        rows.append(payload)
    return stamp_identity(rows, identity)


def concat_case_parquets(out_dir: Path, filename: str, destination: Path) -> None:
    frames = [
        pl.read_parquet(path)
        for path in sorted(out_dir.glob(f"*/{filename}"))
        if path.is_file()
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if frames:
        pl.concat(frames, how="diagonal_relaxed").write_parquet(destination)
    else:
        write_parquet(destination, [])


def concat_case_jsonl(out_dir: Path, filename: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for path in sorted(out_dir.glob(f"*/{filename}")):
            handle.write(path.read_text(encoding="utf-8"))


def write_run_level_canonical_outputs(out_dir: Path) -> None:
    concat_case_parquets(out_dir, "candidate_trace.parquet", out_dir / "candidate_trace.parquet")
    concat_case_parquets(out_dir, "source_facts.parquet", out_dir / "source_facts.parquet")
    concat_case_parquets(out_dir, "derived_facts.parquet", out_dir / "derived_facts.parquet")
    concat_case_parquets(
        out_dir, "production_selection.parquet", out_dir / "production_selection.parquet"
    )
    concat_case_parquets(out_dir, "issue_ledger.parquet", out_dir / "issue_ledger.parquet")
    concat_case_jsonl(out_dir, "source_facts.jsonl", out_dir / "source_facts.jsonl")
    concat_case_jsonl(out_dir, "derived_facts.jsonl", out_dir / "derived_facts.jsonl")
