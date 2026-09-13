#!/usr/bin/env python3
"""Show remaining locked-set misses with nearby statement labels. Not §37."""

from __future__ import annotations

import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.golden import _match_key, published_source_facts
from cse_financial_etl.v2.diagnostics.real_filings import load_real_filing_cases
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.statements.table_reconstructor import reconstruct_statements
from cse_financial_etl.v2.taxonomy.registry import normalize_label

KEYWORDS = (
    "profit",
    "operating",
    "earnings",
    "eps",
    "per share",
    "nav",
    "net asset",
    "net book",
    "before tax",
    "after tax",
    "pbt",
    "pat",
)


def main() -> int:
    rows = []
    for case in load_real_filing_cases(limit=40, locked=True):
        statements, facts, _derived, _metrics = run_pdf_pipeline(
            case.pdf_path,
            issuer_id=case.issuer_id,
            filing_version_id=case.case_id,
            expected_entity_scope=case.entity_scope,
            target_period_end=case.period_end,
        )
        predicted = published_source_facts(facts)
        exp_map = {
            _match_key(item.metric_code, item.entity_scope, item.period_end): item
            for item in case.expected
        }
        pred_groups: dict = {}
        for item in predicted:
            pred_groups.setdefault(
                _match_key(item.metric_code, item.entity_scope, item.period_end), []
            ).append(item)
        misses = []
        for key, gold in exp_map.items():
            preds = pred_groups.get(key) or []
            if any(item.normalized_value == gold.normalized_value for item in preds):
                continue
            misses.append(gold.metric_code)
        if not misses:
            continue
        document = read_document(case.pdf_path, filing_version_id=case.case_id)
        regions = detect_statement_regions(document)
        reconstructed = reconstruct_statements(document, regions)
        labels = []
        for statement in reconstructed:
            bound = bind_column_context(document, statement)
            durations = [
                column.duration_months
                for column in bound.columns
                if column.unit_dimension is not None and column.unit_dimension.value == "MONETARY"
            ]
            entities = [
                None if column.entity_scope is None else column.entity_scope.value
                for column in bound.columns
                if column.unit_dimension is not None and column.unit_dimension.value == "MONETARY"
            ]
            interesting = [
                row.raw_label
                for row in statement.rows
                if any(word in normalize_label(row.raw_label) for word in KEYWORDS)
            ]
            labels.append(
                {
                    "type": statement.statement_type.value,
                    "page": statement.pages[0],
                    "entities": entities,
                    "durations": durations,
                    "labels": interesting[:20],
                }
            )
        rows.append(
            {
                "symbol": case.issuer_id,
                "misses": misses,
                "published": sorted({item.metric_code for item in predicted}),
                "statements": labels,
            }
        )
    Path("data/cache/v2_remaining_labels.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    print(json.dumps({row["symbol"]: row["misses"] for row in rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
