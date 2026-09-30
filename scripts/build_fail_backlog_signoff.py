"""Build the residual human sign-off pack from a fail-backlog rerun."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parents[1]
DOSSIER = ROOT / "reports" / "gold_gate"
ABSENCE_TOKENS = {
    "NOT_REPORTED",
    "NOT_REPORTED_3M",
    "SOURCE_CONFIRMED_NOT_REPORTED",
    "DASH",
    "NIL",
}


def _human_absence(value: str) -> bool:
    return str(value or "").strip().upper() in ABSENCE_TOKENS


def classify(row: dict) -> str:
    if row.get("match"):
        return "RECOVERED"
    if row.get("residual_class") == "OCR_REQUIRED":
        return "OCR_REQUIRED"
    if row.get("rerun_status") == "EXTRACT_ERROR":
        return "EXTRACT_ERROR"
    human = str(row.get("human_value") or "")
    rerun = row.get("rerun_value")
    if _human_absence(human) and rerun is None:
        return "AGREE_ABSENT"
    if _human_absence(human) and rerun is not None:
        return "POLICY_DISAGREE_MACHINE_POPULATED"
    if rerun is None:
        return "STILL_WITHHELD"
    return "VALUE_MISMATCH"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rerun",
        type=Path,
        default=DOSSIER / "fail_backlog_rerun_all.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DOSSIER,
    )
    args = parser.parse_args()
    payload = json.loads(args.rerun.read_text(encoding="utf-8"))
    rows = list(payload.get("rows") or [])
    for row in rows:
        row["residual_class"] = classify(row)

    recovered = [row for row in rows if row["residual_class"] == "RECOVERED"]
    agree_absent = [row for row in rows if row["residual_class"] == "AGREE_ABSENT"]
    residual = [
        row
        for row in rows
        if row["residual_class"]
        in {
            "OCR_REQUIRED",
            "STILL_WITHHELD",
            "VALUE_MISMATCH",
            "POLICY_DISAGREE_MACHINE_POPULATED",
            "EXTRACT_ERROR",
        }
    ]
    ocr = [row for row in residual if row["residual_class"] == "OCR_REQUIRED"]
    withheld = [
        row
        for row in residual
        if row["residual_class"] in {"STILL_WITHHELD", "EXTRACT_ERROR"}
    ]
    signoff = [
        row
        for row in residual
        if row["residual_class"]
        in {"VALUE_MISMATCH", "POLICY_DISAGREE_MACHINE_POPULATED"}
    ]

    fields = [
        "residual_class",
        "symbol",
        "issuer_name",
        "issuer_type",
        "period_end",
        "metric_code",
        "human_value",
        "human_page",
        "rerun_value",
        "rerun_status",
        "rerun_page",
        "packet_machine_status",
    ]

    residual_csv = args.out_dir / "manual_qa_residual_fail_queue.csv"
    signoff_csv = args.out_dir / "manual_qa_signoff_exceptions.csv"
    recovered_csv = args.out_dir / "manual_qa_recovered_from_fail_queue.csv"
    ocr_csv = args.out_dir / "manual_qa_ocr_required_queue.csv"
    withheld_csv = args.out_dir / "manual_qa_engineering_withheld.csv"
    for path, data in (
        (residual_csv, residual),
        (signoff_csv, signoff),
        (recovered_csv, recovered),
        (ocr_csv, ocr),
        (withheld_csv, withheld),
    ):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    summary = {
        "rerun_file": str(args.rerun),
        "compared": len(rows),
        "recovered": len(recovered),
        "agree_absent": len(agree_absent),
        "residual": len(residual),
        "signoff_exceptions": len(signoff),
        "ocr_required": len(ocr),
        "engineering_withheld": len(withheld),
        "by_class": dict(Counter(row["residual_class"] for row in rows)),
        "residual_issuers": sorted({row["symbol"] for row in residual}),
        "signoff_issuers": sorted({row["symbol"] for row in signoff}),
    }
    summary_path = args.out_dir / "manual_qa_fail_backlog_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    wb = Workbook()
    cover = wb.active
    cover.title = "README"
    cover["A1"] = "CSE 100-issuer FAIL backlog — residual human sign-off"
    cover["A1"].font = Font(bold=True, size=14)
    cover["A3"] = "This workbook is NOT MANUAL_QA. Independent human confirmation is still required."
    cover["A5"] = "Compared FAIL rows"
    cover["B5"] = summary["compared"]
    cover["A6"] = "Recovered by hybrid V2 rerun"
    cover["B6"] = summary["recovered"]
    cover["A7"] = "Still disagree after rerun"
    cover["B7"] = summary["residual"]
    cover["A8"] = "True ambiguities for human sign-off"
    cover["B8"] = summary["signoff_exceptions"]
    cover["A9"] = "OCR required (not a value decision)"
    cover["B9"] = summary["ocr_required"]
    cover["A10"] = "Engineering withheld (unlabeled entity / duration / admission)"
    cover["B10"] = summary["engineering_withheld"]
    cover["A12"] = (
        "Start with Signoff_Exceptions only. Do not inspect Recovered or "
        "Engineering_Withheld before development continues. OCR_Required needs "
        "Tesseract, not a transcribed number. This workbook is NOT MANUAL_QA."
    )

    def _write_sheet(name: str, data: list[dict]) -> None:
        ws = wb.create_sheet(name)
        ws.append(fields)
        for row in data:
            ws.append([row.get(key, "") for key in fields])

    _write_sheet("Signoff_Exceptions", signoff)
    _write_sheet("OCR_Required", ocr)
    _write_sheet("Engineering_Withheld", withheld)
    _write_sheet("Residual_All", residual)
    _write_sheet("Recovered", recovered)
    xlsx_path = args.out_dir / "CSE_100_Issuer_FAIL_Backlog_Signoff.xlsx"
    wb.save(xlsx_path)
    print(json.dumps({key: summary[key] for key in summary if key not in {"residual_issuers", "signoff_issuers"}}, indent=2))
    print(f"wrote {xlsx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
