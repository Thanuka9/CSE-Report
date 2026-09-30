# AI / evidence QA dossier

This folder is the reviewer dossier for OFFICIAL human gold. It is **not** MANUAL_QA.

## Approval boundary

- **V2 DRAFT production:** APPROVED from the AI/evidence QA perspective. No software rollback to V1 is indicated.
- **OFFICIAL publication:** NOT YET HUMAN-CERTIFIED.
- `AI_QA_PRECHECK_PASS` means no structural/evidence red flag was found in the machine ledger.
- `AI_QA_PRECHECK_PASS` does **not** mean an independent visual transcription of the source PDF.
- Do **not** relabel `UNADJUDICATED` / `PIPELINE_SEEDED` as `MANUAL_QA`.
- The 2026-09-28 `CSE_100_Issuer_Manual_QA_Final` CSV is a completed 900-row source review by `OPENAI_ASSISTANT_MANUAL_SOURCE_REVIEW`. It is **not** independent `MANUAL_QA` and was **not** written into `tests/fixtures/golden_financial_facts.json`.

## Audit coverage

| Measure | Result |
|---|---|
| Required gold benchmark issuers | 100 |
| Benchmark issuers audited | 100 |
| Benchmark rows audited | 900 |
| 100-issuer evidence precheck PASS | 95 |
| 100-issuer evidence precheck REVIEW | 5 |
| Full-universe issuers audited | 281 |
| 281-issuer precheck PASS | 260 |
| 281-issuer precheck REVIEW | 21 |
| Sept-27 recovery: exact PDFs hashed | 100 / 100 |
| Sept-27 completed human adjudication for this packet | 0 / 100 |
| Sept-28 source-review rows COMPLETED | 900 / 900 |
| Sept-28 human_verdict PASS / FAIL | 676 / 224 |
| Sept-28 reviewer_id | OPENAI_ASSISTANT_MANUAL_SOURCE_REVIEW |
| FAIL backlog hybrid V2 rerun recovered | 56 / 224 |
| Remaining true ambiguities for human sign-off | 10 |
| Remaining OCR_REQUIRED | 21 |
| Remaining engineering withheld | 137 |
| Committed MANUAL_QA issuers | 4 |
| Independent human MANUAL_QA still required | 96 |

Source artifact: GitHub Actions `full-universe-2026-09-10`, run `34482772459`.

The Sept-10 100-issuer packet is **not** the same set as the committed golden fixture (60 symbol overlap). The prior 4 `MANUAL_QA` issuers belong to different fixture periods and do not count as 4/100 of this packet.

## Files

- `CSE_V2_AI_QA_100plus_Production_Gate.xlsx` — Executive Summary, 100 Issuer QA, 900 Row QA, 281 Issuer Universe, Priority Review Queue, Methodology
- `ai_qa_100_issuer_precheck.csv`
- `ai_qa_281_issuer_universe_precheck.csv`
- `ai_qa_priority_review_queue.csv` — targeted exceptions for human source review
- `CSE_100_Issuer_QA_Recovery_2026-09-27.xlsx` — exact-PDF recovery / audit status
- `CSE_100_Issuer_Manual_QA_Final_2026-09-28.csv` — 900-row source review (assistant reviewer)
- `manual_qa_final_receipt_2026-09-28.json`
- `manual_qa_final_issuer_status.csv`
- `manual_qa_final_fail_queue.csv` — original 224 machine/source disagreements
- `fail_backlog_rerun_merged.json` — hybrid V2 rerun vs Sept-28 human_value
- `manual_qa_recovered_from_fail_queue.csv` — 56 extractor-recovered rows
- `manual_qa_signoff_exceptions.csv` — 10 true ambiguities
- `manual_qa_ocr_required_queue.csv` — 21 OCR_REQUIRED rows (SDB, ACAP, GRAN, LLUB)
- `manual_qa_engineering_withheld.csv` — 137 unlabeled-entity / admission withholds
- `CSE_100_Issuer_FAIL_Backlog_Signoff.xlsx` — residual human sign-off workbook
- `manual_qa_adjudication_packet.json` / `manual_qa_adjudication_queue.csv` — original 100-issuer packet; statuses unchanged

## Human next step

Do **not** inspect all 900 rows, and do not re-inspect the 224 FAIL queue, before development continues. Independent confirmation against the official filing is still required before any row becomes `MANUAL_QA`.

1. Open `CSE_100_Issuer_FAIL_Backlog_Signoff.xlsx` sheet `Signoff_Exceptions` (10 rows).
2. Leave `OCR_Required` until Tesseract is available; do not guess values.
3. Leave `Engineering_Withheld` as fail-closed unlabeled/admission gaps (ABAN, CABO, LGIL, UAL, AFSL, …). Do not invent COMPANY from the issuer name.
