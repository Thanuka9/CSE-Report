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


def test_sept28_source_review_packet_is_not_imported_as_manual_qa() -> None:
    path = DOSSIER / "CSE_100_Issuer_Manual_QA_Final_2026-09-28.csv"
    receipt_path = DOSSIER / "manual_qa_final_receipt_2026-09-28.json"
    recovery = DOSSIER / "CSE_100_Issuer_QA_Recovery_2026-09-27.xlsx"
    assert path.is_file()
    assert receipt_path.is_file()
    assert recovery.is_file()

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 900
    assert len({row["symbol"] for row in rows}) == 100
    assert {row["manual_review_status"] for row in rows} == {"COMPLETED"}
    assert {row["reviewer_id"] for row in rows} == {"OPENAI_ASSISTANT_MANUAL_SOURCE_REVIEW"}
    verdicts = Counter(row["human_verdict"] for row in rows)
    assert verdicts["PASS"] == 676
    assert verdicts["FAIL"] == 224

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["approval_boundary"]["imported_as_manual_qa"] is False
    assert receipt["approval_boundary"]["committed_manual_qa_issuers"] == 4

    fixtures = json.loads(GOLDEN.read_text(encoding="utf-8"))
    by_status = Counter(str(row.get("verification_status") or "") for row in fixtures)
    assert by_status["MANUAL_QA"] == 4
    assert by_status["PIPELINE_SEEDED"] >= 90


def test_fail_backlog_signoff_is_residual_exceptions_not_manual_qa() -> None:
    summary = json.loads((DOSSIER / "manual_qa_fail_backlog_summary.json").read_text(encoding="utf-8"))
    workbook = DOSSIER / "CSE_100_Issuer_FAIL_Backlog_Signoff.xlsx"
    signoff_path = DOSSIER / "manual_qa_signoff_exceptions.csv"
    recovered_path = DOSSIER / "manual_qa_recovered_from_fail_queue.csv"
    residual_path = DOSSIER / "manual_qa_residual_fail_queue.csv"
    assert workbook.is_file()
    assert signoff_path.is_file()
    assert recovered_path.is_file()
    assert residual_path.is_file()

    assert summary["compared"] == 224
    assert summary["recovered"] == 56
    assert summary["residual"] == 168
    assert summary["signoff_exceptions"] == 10
    assert summary["ocr_required"] == 21
    assert summary["engineering_withheld"] == 137
    assert summary["recovered"] + summary["residual"] == 224

    with signoff_path.open(newline="", encoding="utf-8") as handle:
        signoff = list(csv.DictReader(handle))
    assert len(signoff) == 10
    assert {row["residual_class"] for row in signoff} <= {
        "VALUE_MISMATCH",
        "POLICY_DISAGREE_MACHINE_POPULATED",
    }

    with recovered_path.open(newline="", encoding="utf-8") as handle:
        recovered = list(csv.DictReader(handle))
    assert len(recovered) == 56
    assert {row["residual_class"] for row in recovered} == {"RECOVERED"}

    fixtures = json.loads(GOLDEN.read_text(encoding="utf-8"))
    by_status = Counter(str(row.get("verification_status") or "") for row in fixtures)
    assert by_status["MANUAL_QA"] == 4
    assert by_status["PIPELINE_SEEDED"] >= 90
