"""Classify remaining N18 FN into discovery vs withhold vs wrong-statement families."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v2_score_n18_ai_blind import _load_items, collect_n17_v2_facts, score_n18  # noqa: E402
from cse_financial_etl.v2.document.router import read_document  # noqa: E402
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline  # noqa: E402
from cse_financial_etl.v2.contracts.enums import StatementType  # noqa: E402


def main() -> int:
    items = _load_items(ROOT / "tests/v2/source_truth/n17_ai_blind_gold.jsonl")
    identity = json.loads(
        (ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    facts = collect_n17_v2_facts(
        ROOT, ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json"
    )
    score = score_n18(items, facts)
    fns = [d for d in score["details"] if d.get("result") == "FN"]
    gold_by_key = {
        (i.issuer_id, i.metric_code): i
        for i in items
        if i.source_presence.value == "REPORTED"
    }

    out_rows = []
    pipe_cache: dict[str, object] = {}
    page_text: dict[str, str] = {}

    for d in fns:
        issuer = d["issuer_id"]
        metric = d["metric_code"]
        gold = gold_by_key.get((issuer, metric))
        idrow = next(r for r in identity["items"] if r["issuer_id"] == issuer)
        if issuer not in pipe_cache:
            doc = read_document(
                ROOT / idrow["local_file"],
                filing_version_id=str(idrow["filing_version_id"]),
            )
            page_text[issuer] = "\n".join(
                ln.text or "" for p in doc.pages for ln in (p.lines or ())
            )
            pipe_cache[issuer] = (
                doc,
                run_filing_pipeline(
                    doc,
                    issuer_id=issuer,
                    issuer_name=str(idrow.get("legal_name") or ""),
                    issuer_type=str(idrow.get("issuer_type") or ""),
                ),
            )
        doc, result = pipe_cache[issuer]
        label = (gold.raw_source_label if gold else "") or ""
        frag = label.lower()[:24]
        text_hit = bool(frag and frag in page_text[issuer].lower())
        if not text_hit and label:
            tokens = [t for t in label.lower().replace("/", " ").split() if len(t) >= 4][:3]
            text_hit = bool(tokens) and any(
                all(t in line.lower() for t in tokens)
                for line in page_text[issuer].splitlines()
            )

        resolved = [tr for tr in result.traces if tr.resolved_metric == metric]
        label_rows = [
            tr
            for tr in result.traces
            if frag and frag in (tr.row_label or "").lower()
        ]
        # wrong statement: label matched only outside income/BS/EPS note
        wrong_stmt = False
        for tr in label_rows:
            st = getattr(tr, "statement_type", None)
            if st is None:
                continue
            allowed = {
                StatementType.INCOME_STATEMENT,
                StatementType.BALANCE_SHEET,
                StatementType.EPS_NOTE,
            }
            # PAT/PBT/OP/TOP only valid on IS
            if metric in {"PAT", "PBT", "OPERATING_PROFIT", "TOP_LINE", "EPS_BASIC", "EPS_DILUTED"}:
                if st is not StatementType.INCOME_STATEMENT and st is not StatementType.EPS_NOTE:
                    wrong_stmt = True
            elif metric in {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES", "NAVPS"}:
                if st is not StatementType.BALANCE_SHEET and st is not StatementType.EPS_NOTE:
                    wrong_stmt = True

        stages = [
            tr.first_failure_stage.value
            for tr in resolved
            if tr.first_failure_stage is not None
        ]
        stage = Counter(stages).most_common(1)[0][0] if stages else None

        if resolved and stage == "ENTITY_UNRESOLVED":
            bucket = "DOWNSTREAM_ENTITY_UNRESOLVED"
        elif resolved and stage in {"PERIOD_UNRESOLVED", "UNIT_UNRESOLVED", "UNIT_DIMENSION_MISMATCH"}:
            bucket = "DOWNSTREAM_CONTEXT_UNRESOLVED"
        elif resolved and stage in {"VALIDATION", "PUBLICATION", "SOURCEFACT_WITHHELD", "VALIDATION_WITHHELD"}:
            bucket = "DOWNSTREAM_WITHHELD"
        elif resolved:
            bucket = "DOWNSTREAM_OTHER"
        elif wrong_stmt and label_rows:
            bucket = "WRONG_STATEMENT_CLASSIFICATION"
        elif label_rows:
            bucket = "UNTABLED_OR_CONCEPT_GAP"  # present as row but concept failed
        elif text_hit:
            bucket = "SOURCE_TEXT_PRESENT_NOT_TABLED"
        else:
            bucket = "GENUINELY_UNREPORTED_OR_OCR_MISS"

        out_rows.append(
            {
                "issuer_id": issuer,
                "metric_code": metric,
                "gold_label": label,
                "gold_value": None if gold is None else str(gold.normalized_value),
                "bucket": bucket,
                "resolved_count": len(resolved),
                "label_row_count": len(label_rows),
                "text_hit": text_hit,
                "wrong_statement": wrong_stmt,
                "dominant_stage": stage,
                "label_row_statements": sorted(
                    {
                        str(getattr(tr, "statement_type", None))
                        for tr in label_rows
                    }
                ),
            }
        )

    summary = {
        "fn_count": len(out_rows),
        "bucket_counts": dict(Counter(r["bucket"] for r in out_rows)),
        "by_issuer_bucket": {
            issuer: dict(Counter(r["bucket"] for r in out_rows if r["issuer_id"] == issuer))
            for issuer in sorted({r["issuer_id"] for r in out_rows})
        },
    }
    out = ROOT / "tests/v2/universe/n18_fn66_bucket_classification.json"
    out.write_text(json.dumps({"summary": summary, "rows": out_rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
