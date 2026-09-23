# AI / evidence QA dossier

This folder is the reviewer dossier for OFFICIAL human gold. It is **not** MANUAL_QA.

## Approval boundary

- **V2 DRAFT production:** APPROVED from the AI/evidence QA perspective. No software rollback to V1 is indicated.
- **OFFICIAL publication:** NOT YET HUMAN-CERTIFIED.
- `AI_QA_PRECHECK_PASS` means no structural/evidence red flag was found in the machine ledger.
- `AI_QA_PRECHECK_PASS` does **not** mean an independent visual transcription of the source PDF.
- Do **not** relabel `UNADJUDICATED` / `PIPELINE_SEEDED` as `MANUAL_QA`.

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
| Existing MANUAL_QA issuers | 4 |
| Independent human MANUAL_QA still required | 96 |

Source artifact: GitHub Actions `full-universe-2026-09-10`, run `34482772459`.

## Files

- `CSE_V2_AI_QA_100plus_Production_Gate.xlsx` — Executive Summary, 100 Issuer QA, 900 Row QA, 281 Issuer Universe, Priority Review Queue, Methodology
- `ai_qa_100_issuer_precheck.csv`
- `ai_qa_281_issuer_universe_precheck.csv`
- `ai_qa_priority_review_queue.csv` — targeted exceptions for human source review
- `manual_qa_adjudication_packet.json` / `manual_qa_adjudication_queue.csv` — original 100-issuer packet; statuses unchanged

## Human next step

Use the Priority Review Queue for targeted source-PDF review. Only after independent confirmation against the official filing may a row become `MANUAL_QA`.
