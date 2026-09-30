# Same-definition KPI: 3,854 vs 2,816 / 2,840

**Mandate:** `docs/v2/MAKE_V2_MAIN_REACH_V1_PARITY.md` §1  
**Do not substitute these figures for each other.**

## Definitions

| Label | Definition | Count (pre non-reg fix) |
|---|---|---:|
| E13 `draft_publishable_count` | Production statuses EXTRACTED + EXTRACTED_DERIVED after entity/period/duration selection; **source + derived** (incl. ROE, NPM, EPS_SELECTED, …) on clean SHA `d29b392` | **3,854** |
| Three-way `draft_selected_target` | `select_pipeline_facts` on **SOURCE** facts only; TARGET metric set; COMPANY→GROUP→BANK preference | V2 **2,816** / assisted **2,840** |
| ELIGIBLE TARGET rows | All entities/durations/comparisons; no production query | V2 **9,838** |

## E13 3,854 decomposition (`e13_summary.json` coverage_by_metric)

| Class | Metrics | Sum |
|---|---|---:|
| Source TARGET-like | TOP_LINE, OP, PBT, PAT, EPS_BASIC, EPS_DILUTED, NAVPS, TOTAL_ASSETS, TOTAL_EQUITY, TOTAL_LIABILITIES | **2,751** |
| Derived / publication | EPS_SELECTED, ROE, ROA, NPM, DEBT_TO_EQUITY | **1,103** |
| **Total** | | **3,854** |

So **2,816 TARGET draft-selected ≈ same order as E13’s 2,751 source slice**, not the 3,854 total. The ~65 gap is entity preference, filing errors (9), and selection-rule drift — not proof that assisted +24 closes the E13 gap.

## Rule for reporting

- Announce **TARGET draft-selected** and **source+derived** separately.
- Never publish “3,878” (= 3854+24) without a same-definition E13-style rerun.
- After each integration, remeasure both TARGET and source+derived on the pinned 829.

Post non-reg fix numbers: see updated `gap_summary.json` after the 829 remeasure.
