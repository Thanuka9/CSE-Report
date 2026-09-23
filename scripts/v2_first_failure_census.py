"""Seed / expand first-failure census artefacts for recovery strategy R2.

Default: summarize locked-33 CandidateTrace parquet into JSON (+ optional CSVs).
Full-universe census requires a challenger run that emits CandidateTrace; this
script does not invent stages and does not retune extraction.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import polars as pl


def _counts(df: pl.DataFrame, col: str) -> dict[str, int]:
    if col not in df.columns:
        return {}
    return {
        str(row[col]): int(row["len"])
        for row in df.group_by(col).len().sort("len", descending=True).to_dicts()
    }


def summarize(df: pl.DataFrame, *, scope: str, note: str) -> dict:
    payload: dict = {
        "scope": scope,
        "note": note,
        "candidate_rows": df.height,
        "filings": int(df["filing_version_id"].n_unique())
        if "filing_version_id" in df.columns
        else None,
        "first_failure_stage_counts": _counts(df, "first_failure_stage"),
    }
    if "source_fact_created" in df.columns and df.schema.get("source_fact_created") == pl.Boolean:
        payload["source_fact_created_true"] = int(df.filter(pl.col("source_fact_created")).height)
    for col in (
        "entity_status",
        "period_status",
        "duration_status",
        "comparison_status",
        "unit_status",
        "concept_status",
    ):
        payload[f"{col}_counts"] = _counts(df, col)
    focus = [
        "ENTITY_UNRESOLVED",
        "UNIT_UNRESOLVED",
        "PERIOD_UNRESOLVED",
        "DURATION_UNRESOLVED",
        "CONCEPT_UNRESOLVED",
        "NUMERIC_UNPARSED",
        "UNIT_DIMENSION_MISMATCH",
    ]
    top: dict[str, list[dict]] = {}
    for stage in focus:
        if "first_failure_stage" not in df.columns or "resolved_metric" not in df.columns:
            top[stage] = []
            continue
        sub = df.filter(pl.col("first_failure_stage") == stage)
        if sub.height == 0:
            top[stage] = []
            continue
        grouped = (
            sub.group_by("resolved_metric").len().sort("len", descending=True).head(12).to_dicts()
        )
        top[stage] = [
            {"metric": row["resolved_metric"], "count": int(row["len"])} for row in grouped
        ]
    payload["top_metrics_by_focus_stage"] = top
    return payload


def write_csvs(df: pl.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if "first_failure_stage" in df.columns:
        (
            df.group_by("first_failure_stage")
            .len()
            .sort("len", descending=True)
            .rename({"len": "count"})
            .write_csv(out_dir / "universe_first_failure_summary.csv")
        )
    if {"resolved_metric", "first_failure_stage"}.issubset(df.columns):
        (
            df.group_by(["resolved_metric", "first_failure_stage"])
            .len()
            .sort("len", descending=True)
            .rename({"len": "count"})
            .write_csv(out_dir / "universe_first_failure_by_metric.csv")
        )
    if {"sector", "first_failure_stage"}.issubset(df.columns):
        (
            df.group_by(["sector", "first_failure_stage"])
            .len()
            .sort("len", descending=True)
            .rename({"len": "count"})
            .write_csv(out_dir / "universe_first_failure_by_sector.csv")
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("outputs/v2_extraction_baseline/candidate_trace.parquet"),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("tests/v2/universe/r2_seed_first_failure_locked33.json"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tests/v2/universe/r2_seed_census"),
    )
    parser.add_argument("--scope", default="locked-33-baseline-candidate-trace")
    args = parser.parse_args()
    if not args.trace.is_file():
        raise SystemExit(f"missing CandidateTrace parquet: {args.trace}")
    df = pl.read_parquet(args.trace)
    payload = summarize(
        df,
        scope=args.scope,
        note=(
            "SEED census from CandidateTrace. Full-universe R2 still required when "
            "universe-scale traces exist. Do not treat concept-unresolved raw counts "
            "as proof to expand aliases before header/unit ports."
        ),
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_csvs(df, args.out_dir)
    waterfall = {
        "ordered_stages": list(payload["first_failure_stage_counts"].items()),
        "resolution_unresolved": {
            key: payload.get(f"{key}_status_counts", {}).get("UNRESOLVED", 0)
            for key in ("entity", "period", "duration", "comparison", "unit", "concept")
        },
    }
    (args.out_dir / "universe_failure_waterfall.json").write_text(
        json.dumps(waterfall, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"wrote": str(args.out_json), "stages": payload["first_failure_stage_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
