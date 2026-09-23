from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOSSIER = ROOT / "reports" / "gold_gate"
GOLDEN = ROOT / "tests" / "fixtures" / "golden_financial_facts.json"


def test_ai_qa_dossier_covers_100_and_281_without_relabeling_manual_qa() -> None:
    path_100 = DOSSIER / "ai_qa_100_issuer_precheck.csv"
    path_281 = DOSSIER / "ai_qa_281_issuer_universe_precheck.csv"
    queue = DOSSIER / "ai_qa_priority_review_queue.csv"
    workbook = DOSSIER / "CSE_V2_AI_QA_100plus_Production_Gate.xlsx"
    assert path_100.is_file()
    assert path_281.is_file()
    assert queue.is_file()
    assert workbook.is_file()

    with path_100.open(newline="", encoding="utf-8") as handle:
        rows_100 = list(csv.DictReader(handle))
    with path_281.open(newline="", encoding="utf-8") as handle:
        rows_281 = list(csv.DictReader(handle))
    with queue.open(newline="", encoding="utf-8") as handle:
        review_queue = list(csv.DictReader(handle))

    assert len(rows_100) == 100
    assert len({row["symbol"] for row in rows_100}) == 100
    verdicts_100 = Counter(row["precheck_verdict"] for row in rows_100)
    assert verdicts_100["AI_QA_PRECHECK_PASS"] == 95
    assert verdicts_100["AI_QA_REVIEW"] == 5

    assert len(rows_281) == 281
    assert len({row["symbol"] for row in rows_281}) == 281
    verdicts_281 = Counter(row["precheck_verdict"] for row in rows_281)
    assert verdicts_281["AI_QA_PRECHECK_PASS"] == 260
    assert verdicts_281["AI_QA_REVIEW"] == 21
    assert len(review_queue) >= 5

    fixtures = json.loads(GOLDEN.read_text(encoding="utf-8"))
    by_status = Counter(str(row.get("verification_status") or "") for row in fixtures)
    assert by_status["MANUAL_QA"] == 4
    assert by_status["PIPELINE_SEEDED"] >= 90
    assert "AI_QA_PRECHECK_PASS" not in by_status
