# N17 AI Blind Adjudication — Execution Status

**Plan:** `docs/v2/N17_AI_BLIND_ADJUDICATION_AND_FINAL_EXECUTION_PLAN.md`  
**Branch:** `v2/extraction-investigation`  
**Reviewer 1:** `chatgpt-blind-source-review-2026-09-19`  
**Adjudication:** `AI_REVIEWER_1_COMPLETE`  
**Engine / floor:** `v1` / `8924` (unchanged)  
**As of:** 2026-09-19

## Isolation

Adjudication inputs only:

- 13 N16 holdout PDFs (+ text/OCR dumps under `outputs/n17_blind_pdf_text/`)
- `docs/v2/SOURCE_METRIC_TRUTH_CONTRACT.md`
- identity manifest + this plan

Not consulted: V1/V2 outputs, CandidateTrace, SourceFacts, workbooks, selectors.

## Gold status — LOCKED

| Artifact | Path | Status |
|---|---|---|
| Gold JSONL | `tests/v2/source_truth/n17_ai_blind_gold.jsonl` | **130/130 locked** |
| Manifest | `tests/v2/source_truth/n17_ai_blind_gold_manifest.json` | `AI_BLIND_GOLD_LOCKED` |
| `gold_locked` | **true** | immutable N17 gold for N18 |

Presence counts:

| Presence | Count |
|---|---:|
| REPORTED | 115 |
| NOT_REPORTED | 15 |
| AMBIGUOUS | 0 |

OCR re-adjudication of SDB / HUNA / AFSL cleared all prior AMBIGUOUS slots via `outputs/n17_blind_partial/zzz_ocr_cleared.jsonl` (assembler last-wins).

FLOW REPORTED rows use `duration_months=3` only (no year substituted for Q4).

## Lock identifiers

Recorded in the lock commit:

- **gold commit SHA:** `639454a2d211153062dc9d4e4cb6dbd7de9852fd`
- **gold file SHA256:** see manifest `gold_sha256`
- **contract SHA256:** see manifest `source_contract_sha256`
- **13 PDF SHA256s:** see manifest `pdf_sha256`

## Next (N18)

1. ~~Run N18 exactly once against this locked gold — do not tune V2 first~~ **DONE**
2. ~~Freeze/commit the untouched first N18 score immediately~~ see score commit
3. Only then inspect failures  

First N18 score artifact: `tests/v2/universe/n18_ai_blind_first_score.json`  
(TP 23 / FN 68 / critical_wrong 8 / source-reported recall 0.20 — frozen untouched; investigate after score commit.)

Hard stops remain: do not promote V2 / lower 8924; do not invent values; do not silently rewrite gold.
