# Source-review adjudication sample (Phase A.4)

**Queue:** `source_review_queue.json` stratified V1-only (n=30 live re-probe with issuer_name/type).  
**Artifact:** `source_review_adjudication_sample.json`  
**Rule:** V1 is comparator, not truth.

## Classification

| Class | n | Meaning |
|---|---:|---|
| `V2_CELL_ENTITY_UNRESOLVED_LIKELY_V1_INVENT` | 15 | V2 has the cell+concept; entity missing because headers/legal-name fail-closed (`test_company_in_issuer_name_alone_does_not_bind_company`). V1 stamped BANK/COMPANY without column banner — **not portable** without weakening source truth. |
| `V2_NO_CONCEPT_OR_CELL` | 12 | Real recovery targets: alias gaps, EPS-note/NAVPS statement ownership, missing reconstruction. |
| `V2_CANDIDATE_OTHER_ADMISSION` | 2 | Candidate exists; other admission/context gap. |
| `V2_ELIGIBLE_SELECTION_OR_IDENTITY_GAP` | 1 | Already eligible — soft-key / selection identity issue. |

## Implication for parity

Like-for-like **source-valid** V1 parity must **exclude inventable entity surplus** (≈ half this bank/finance-heavy sample) via governed disposition. Remaining engineering must target concept aliases + physical/NAVPS/EPS-note ownership — not inventing entity from `* Bank PLC` / `* Company PLC` legal names.

## Alias / physical repairs applied

- PAT: `Profit for the year` / loss-for-the-year variants  
- EPS_BASIC: `Basic loss per share`, restated basic earning(s)  
- NAVPS: trailing `LKR` / `- LKR` aliases + allow `OTHER_FINANCIAL_STATEMENT`  
- Label normalize: strip trailing YoY `(184.4%)` and bare `12.3%`  
- Numeric cells: do **not** treat `%` tokens as monetary values (fixes AMBIGUOUS_ROW_VALUES on variance columns)  
- Physical: reconstruct OTHER pages that print investor/key-ratio per-share lines; stop before shareholder lists  

## Sample disposition notes

- Seylan / Merchant `EPS_DILUTED` when PDF only prints `Basic/Diluted` → V1 dual-map surplus; V2 correctly keeps `EPS_BASIC`.  
- Galadari `EPS_BASIC` after alias: concept OK, **entity still fail-closed** (no Company/Group banner).  
- Cable V1 NAVPS `5.75`: **not printed** on the PDF (investor ratios show 5.02 / 4.18 / 5.16 / 4.26). V1 soft key is not source-valid.  

## Status

Still **BLOCKED** for READY FOR OFFICIAL DECISION until full-829 TARGET draft-selected shows material source-verified lift and later gates pass. Production remains V1.
