# V2 Extraction Investigation Report

Diagnostic report for the locked 33. Not certification. Not source gold.
Production engine remains V1. Coverage floor remains 8924.

Verified path: `docs/v2/VERIFIED_OPEN_WORK_AND_FINAL_ENGINEERING_PATH.md`.

- Run ID: locked-experiments-2ff5d1ff1b04d0fbe559dc33d438e9072d030879
- Investigation base SHA: 91a9c68bf940d3d9c2a86245f127de88ad4b4b6d
- Actual code SHA (N12 regen): 2ff5d1ff1b04d0fbe559dc33d438e9072d030879
- Freeze refresh commit: ef4b200
- Source snapshot ID: 7bab3c98cf6bdde906ad0a464885d32437a05f42925e80b49b4d4c8469c306dc
- Runtime: 3.12.0 / Windows-11-AMD64
- Cases: 33
- Lineage complete: 1497
- Context incomplete: 36
- SOURCE_VALUE_NOT_REPRODUCIBLE: 0
- G02 cascade suppressed: 0
- G03 FLOW duration missing: 36
- P1 OCR applied: False
- Prototypes built: H2=False U2=False P2=False
- Locked-33 A/B: deterministic (`baseline_run_summary.json`)

G01/G03/G09 KEEP. G02/G04–G08 remain UNTESTED.
First T25 holdout retired after F1/F3 + SFCL truth fix.
**Next:** N17 human blind adjudication — `docs/v2/N17_BLIND_ADJUDICATION.md` + `n17_blind_review_queue.json` (do not score N16 before truth).
N13 CI/PR and N14 universe challenger remain open. N20 Sept-10 artefacts missing.
