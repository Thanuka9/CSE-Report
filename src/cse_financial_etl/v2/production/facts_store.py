"""Persist native V2 facts for production workbook publication."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact


def v2_publication_paths(project_root: Path, as_of_date: date) -> tuple[Path, Path]:
    root = project_root.resolve()
    outputs = root / "outputs"
    return (
        outputs / f"v2_source_facts_{as_of_date.isoformat()}.jsonl",
        outputs / f"v2_derived_facts_{as_of_date.isoformat()}.jsonl",
    )


def write_v2_publication_facts(
    project_root: Path,
    as_of_date: date,
    *,
    source_facts: Sequence[SourceFact],
    derived_facts: Sequence[DerivedFact],
) -> tuple[Path, Path]:
    source_path, derived_path = v2_publication_paths(project_root, as_of_date)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "\n".join(fact.model_dump_json() for fact in source_facts) + ("\n" if source_facts else ""),
        encoding="utf-8",
    )
    derived_path.write_text(
        "\n".join(fact.model_dump_json() for fact in derived_facts)
        + ("\n" if derived_facts else ""),
        encoding="utf-8",
    )
    return source_path, derived_path


def load_v2_publication_facts(
    project_root: Path, as_of_date: date
) -> tuple[tuple[SourceFact, ...], tuple[DerivedFact, ...]]:
    source_path, derived_path = v2_publication_paths(project_root, as_of_date)
    source = _load_jsonl(source_path, SourceFact)
    derived = _load_jsonl(derived_path, DerivedFact)
    return source, derived


def _load_jsonl[T](path: Path, model: type[T]) -> tuple[T, ...]:
    if not path.exists():
        return ()
    rows: list[T] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(model.model_validate(json.loads(stripped)))  # type: ignore[attr-defined]
    return tuple(rows)
