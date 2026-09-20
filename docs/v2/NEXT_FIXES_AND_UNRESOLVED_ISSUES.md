# CSE V2 — Next Fixes and Unresolved Issues (Execution)

**Branch:** `v2/extraction-investigation`  
**Frozen N17 gold:** `639454a2` / `8f1e510` (rebased)  
**Frozen N18 first score:** immutable — do not overwrite  
**E02 diagnostic correction commit:** `07d3ca8`  
**Production engine / floor:** `v1` / `8924` (unchanged)

> Source MD from Downloads was not present on this machine; this file captures the
> agreed implementation order and verified progress from the 2026-09-20 handoff.

## Hard rules

- Do not mark an issue resolved merely because a fix was documented.
- Do not retune duration/period from holdout identity alone.
- Inspect source PDF + both candidate cells before generalized header fixes.
- N18 re-runs are **regression only** — not unseen holdout proof.
- Dirty working-tree challenger SHAs are not production-reproducible evidence.

## E02 diagnostic corrections (committed `07d3ca8`)

| Correction | Rule |
|---|---|
| Stock duration | NAVPS / TOTAL_* with null duration are **not** `DURATION_UNRESOLVED` |
| Missing candidates | No extracted candidate → `NO_TARGET_CANDIDATE`, not source-verified `ROW_NOT_FOUND` |

Unit tests: `tests/v2/unit/test_e02_target_taxonomy.py`.  
Full-universe E02 **rerun with corrected taxonomy still outstanding**.

## Verified P0 — UBC OPERATING_PROFIT (was last critical wrong)

### Diagnosis (source + candidates)

Gold `748,922` is **not** the YTD “Results from operating activities” cell (`1,840,423`).

It is Bank Q4 on the wrapped line:

```text
Profit before value added tax (VAT) & social security
contribution Levy (SSCL) on financial services
```

Failures stacked:

1. Pending label wrap dropped the first line → concept unresolved on the fragment.
2. Registry lacked bank pre-VAT/SSCL OP aliases (contract-accepted variant).
3. Extra title date banner rotated period pairs → CURRENT/COMPARATIVE flip.

Duration on the Q4 monetary columns was already `3`; the “WRONG_DURATION” N18 label was an artifact of scoring the wrong concept’s YTD cell.

### Fix landed (verify before claiming done)

| Change | File |
|---|---|
| Merge incomplete / lowercase-wrapped account labels | `table_reconstructor.py` |
| Bank OP-before-VAT/SSCL exact aliases | `taxonomy/registry.py` |
| In-field / leading date-banner alignment (no trailing slice rotate) | `column_context.py` |
| Unit tests | `test_wrapped_operating_profit_label.py` |

### Former N18 regression (not unseen)

| Metric | After entity fix | After UBC OP fix |
|---|---:|---:|
| TP | 29 | **33** |
| critical_wrong | 1 | **0** |
| period_mismatch | 8 | **6** |
| UBC OPERATING_PROFIT | MISMATCH | **TP** |
| numeric_correctness | 0.97 | **1.0** |

Artifact: `tests/v2/universe/n18_regression_after_ubc_op_fix.json`

## Remaining execution order

1. ~~UBC source/candidate diagnosis~~ **DONE**
2. ~~Generalized wrap + OP-before-VAT + period banner alignment~~ **DONE (tests green)**
3. ~~Zero critical wrong on former N18~~ **DONE**
4. **Recover 26 source-verified missing rows** (separate `NO_TARGET_CANDIDATE` vs true row miss)
5. Resolve remaining entity / period / unit mismatches (period_mismatch still elevated — triage next)
6. Clean-SHA full-universe E02 rerun (corrected taxonomy) + E13 challenger
7. V1 parity loop
8. Fresh unseen holdout (only after major P0/P1 families)
9. OCR quarantine recovery, CI, replay, certification, cutover

## Still unresolved (do not mark done)

- 68 FN / recall ~0.25 on former N18
- period_mismatch / unit_mismatch residual families
- E02 full-universe rerun under corrected taxonomy
- OCR / CI / Sept-10 replay / workbook lineage / OFFICIAL cutover
- New unseen holdout (blocked until parity zone)

Hard stops remain: no V2 promotion, no floor change, no issuer patches, no inventing gold.
