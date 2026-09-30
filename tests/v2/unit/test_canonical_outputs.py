from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from cse_financial_etl.v2.diagnostics.canonical_outputs import (
    stamp_identity,
    write_jsonl,
    write_parquet,
    write_run_level_canonical_outputs,
)
from cse_financial_etl.v2.diagnostics.investigation_freeze import (
    InvestigationFreeze,
    freeze_run_identity,
)


def test_canonical_outputs_stamp_run_identity(tmp_path: Path) -> None:
    freeze = InvestigationFreeze(
        investigation_base_sha="91a9c68bf940d3d9c2a86245f127de88ad4b4b6d",
        actual_code_sha="abc:dirty:123",
        code_sha="abc",
        branch="v2/extraction-investigation",
        working_tree_dirty=True,
        source_snapshot_id="snap",
        python_version="3.12.0",
        platform="Windows-11-AMD64",
        extraction_engine="v1",
        min_draft_publishable=8924,
    )
    identity = freeze_run_identity(freeze, run_id="locked-baseline-abc:dirty:123")
    rows = stamp_identity([{"metric_code": "PAT", "value": "1"}], identity)
    parquet_path = tmp_path / "source_facts.parquet"
    jsonl_path = tmp_path / "source_facts.jsonl"
    write_parquet(parquet_path, rows)
    write_jsonl(jsonl_path, rows)
    frame = pl.read_parquet(parquet_path)
    assert frame["run_id"][0] == identity["run_id"]
    assert frame["actual_code_sha"][0] == "abc:dirty:123"
    assert frame["investigation_base_sha"][0] == freeze.investigation_base_sha
    assert frame["source_snapshot_id"][0] == "snap"
    line = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert line["python_version"] == "3.12.0"
    assert line["platform"] == "Windows-11-AMD64"
    assert line["metric_code"] == "PAT"


def test_run_level_canonical_outputs_concat_case_files(tmp_path: Path) -> None:
    identity = {
        "run_id": "run-1",
        "actual_code_sha": "abc",
        "investigation_base_sha": "base",
        "source_snapshot_id": "snap",
        "python_version": "3.12.0",
        "platform": "test",
    }
    case_a = tmp_path / "AAA"
    case_b = tmp_path / "BBB"
    write_parquet(case_a / "source_facts.parquet", stamp_identity([{"metric": "PAT"}], identity))
    write_parquet(case_b / "source_facts.parquet", stamp_identity([{"metric": "PBT"}], identity))
    write_jsonl(case_a / "source_facts.jsonl", stamp_identity([{"metric": "PAT"}], identity))
    write_jsonl(case_b / "source_facts.jsonl", stamp_identity([{"metric": "PBT"}], identity))
    write_parquet(case_a / "candidate_trace.parquet", stamp_identity([{"candidate_id": "c1"}], identity))
    write_parquet(case_b / "candidate_trace.parquet", stamp_identity([{"candidate_id": "c2"}], identity))
    write_parquet(case_a / "derived_facts.parquet", stamp_identity([{"metric": "ROE"}], identity))
    write_parquet(case_b / "derived_facts.parquet", stamp_identity([{"metric": "ROA"}], identity))
    write_jsonl(case_a / "derived_facts.jsonl", stamp_identity([{"metric": "ROE"}], identity))
    write_jsonl(case_b / "derived_facts.jsonl", stamp_identity([{"metric": "ROA"}], identity))
    write_parquet(
        case_a / "production_selection.parquet",
        stamp_identity([{"metric": "PAT", "production_selected": True}], identity),
    )
    write_parquet(case_b / "production_selection.parquet", [])
    write_parquet(case_a / "issue_ledger.parquet", stamp_identity([{"issue_id": "1"}], identity))
    write_parquet(case_b / "issue_ledger.parquet", stamp_identity([{"issue_id": "2"}], identity))
    write_run_level_canonical_outputs(tmp_path)
    source = pl.read_parquet(tmp_path / "source_facts.parquet")
    traces = pl.read_parquet(tmp_path / "candidate_trace.parquet")
    assert set(source["metric"].to_list()) == {"PAT", "PBT"}
    assert set(traces["candidate_id"].to_list()) == {"c1", "c2"}
    assert "actual_code_sha" in source.columns
    jsonl = (tmp_path / "source_facts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl) == 2
    assert (tmp_path / "issue_ledger.parquet").is_file()
    assert (tmp_path / "production_selection.parquet").is_file()
