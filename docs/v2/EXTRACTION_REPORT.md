# V2 Extraction Investigation Report

Diagnostic report for the locked 33. Not certification. Not source gold.
Production engine remains V1. Coverage floor remains 8924.

- Run ID: locked-experiments-e92689dabc400e3609e64a9d50512e99d9374dec:dirty:0e06ef8bd0b3
- Investigation base SHA: 91a9c68bf940d3d9c2a86245f127de88ad4b4b6d
- Actual code SHA: e92689dabc400e3609e64a9d50512e99d9374dec:dirty:0e06ef8bd0b3
- Source snapshot ID: 7bab3c98cf6bdde906ad0a464885d32437a05f42925e80b49b4d4c8469c306dc
- Runtime: 3.12.0 / Windows-11-AMD64
- Cases: 33
- Lineage complete: 1606
- Context incomplete: 36
- SOURCE_VALUE_NOT_REPRODUCIBLE: 0
- G02 cascade suppressed: 0
- G03 FLOW duration missing: 36
- P1 OCR applied: False
- T10 queue items: 40
- Prototypes built: H2=False U2=False P2=False

T10: 40 DEV items in `tests/v2/source_truth/items.jsonl` (Reviewer 1 PDF-page
review). G01/G03/G09 KEEP. G02/G04–G08 remain UNTESTED.
T10 vs V2 SourceFacts: 30 TP, 1 value mismatch (ATL TOP_LINE), 8 G01-withheld
unlabeled REPORTED rows, 0 duration inventions. Not certification.
T25–T29 (holdout, frozen universe, certification, cutover) are blocked.
