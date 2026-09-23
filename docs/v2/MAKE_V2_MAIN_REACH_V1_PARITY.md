# CSE — Make V2 the Main Engine: Reach V1 Capability and Cut Over

**Single objective:** Make V2 replace V1 in production **without losing correct financial facts**. Recover V1-scale correct, usable output on the same CSE PDFs while retaining V2's source evidence, entity/period/duration/unit correctness, lineage, and publication controls. **Do not create V3. Do not lower the 8,924 governance floor to declare success.**

## Current position — do not mistake an intermediate count for parity

- Same-input cohort: **829 SHA-pinned PDFs**. Use this exact cohort for every before/after comparison; keep its period, issuer, filing-revision and configuration manifest fixed.
- Historical V2 E13 draft-publishable output: **3,854**. The more recent direct comparison reports **2,816 V2-only vs 2,840 V1-assisted draft-selected TARGET facts**. These are **different output definitions**; neither may be silently substituted for the other.
- V1-assisted discovery initially added 298,541 observations with **zero** eligible lift. The source-context bridge subsequently achieved **+24 net TARGET draft selections**, but had selection churn (**130 new / 106 lost**) and newly wrong selections. **+24 is not yet a verified correctness or production win.**
- Eligible SourceFact *rows* decreased while distinct hard keys increased; measure both, with exact key definitions and source/derived counts separately.
- V1-only differential keys have **not all been PDF-adjudicated**. V1 output is a comparator/candidate source, **not source truth**.
- Keep **V1 as production** until every cutover gate at the end of this file passes.

## What the coding agent must build

```text
THE SAME PDF + PINNED SHA
   ├── V1 proven document / statement / table / row / cell recovery
   └── V2 document / statement / table / row / cell recovery
                            ↓
          ONE DEDUPLICATED SOURCE-OBSERVATION SET
                            ↓
     SOURCE-EVIDENCED HEADER / COLUMN / UNIT CONTEXT
                            ↓
                 V2 FactCandidates
                            ↓
    V2 resolver → SourceFacts → validation → selection
                            ↓
          derived facts → publication → workbook
```

**Do not import V1's final published values**, issuer-specific patches or inferred entity/quarter/scale. Port or adapt the **physical extraction and header/column/unit evidence** that finds and correctly identifies source cells. A V1 cell without PDF-verifiable context remains reviewable, not publishable. V2 should keep its existing valid observation when the V1 bridge is silent; require stronger *conflicting source evidence* before replacing/demoting it.

## Execute in this order — do not return to issuer-by-issuer patching

### 1. Define the one comparable production KPI

Run V1, V2-only and V1-assisted V2 against the **same 829 PDF hashes**, target metric set, period/entity query, release mode and publication rules. Report a matched-key ledger through **source observation → SourceFact → validation → production selection → draft publication**. Reconcile the 3,854 E13 total and the 2,816/2,840 TARGET counts by enumerating source vs derived vs non-target/price rows and selection rules. The primary KPI is **additional PDF-correct, draft-publishable target facts**, not observations, ELIGIBLE rows or small-regression TP counts.

Required comparisons: correct recovered; correct lost; wrong newly selected; wrong removed; V1-only source-valid; V1-only invalid; both missing; genuinely not reported; source ambiguous; input/OCR failure. Never count every V1-only key as correct before source review.

### 2. Finish the real V1→V2 extraction integration

Use the existing `v2/challenger/` observation and context-bridge code as the starting point; do **not** build a parallel V2 or a new abstraction-only framework. Inspect and adapt the V1 statement/table/header/units/continuation code and V2 orchestration. Feed V1-recovered **statement, row, cell and column evidence** into V2's canonical source candidates *upstream of* `resolve_source_facts`, not just 200k+ raw numbers. Record source SHA, page, cell bbox/raw text, row label, statement ownership, entity, period, quarter-vs-YTD duration, comparison role, currency/unit and scale with evidence references.

Preserve safety: no COMPANY/BANK by issuer default; no Q4 = FY−9M; no PAT sourced from changes-in-equity; no share-count or note-row hijack as EPS/TOP_LINE; no monetary-thousands scale inherited by PER_SHARE; no guessing missing units or picking values simply because they equal V1/gold. Unknown or conflicting context must remain withheld with an explicit reason.

### 3. Repair the **whole selected-output path**, not merely candidate admission

Trace representative PDF-confirmed V1-only facts *end to end*. A recovered cell counts only once it is source-validated, properly selected, and appears in the correct publication output. Preserve existing correct V2 selections. Test and repair the documented wrong selections (JAT TOP_LINE, HAYLEYS value, SIGIRIYA EPS/share count) and review the 129 disappeared eligible hard keys first. Distinguish valid duration re-keys from true lost facts. Avoid global V1 overrides or blanket V2 demotion. Maintain a first-loss reason for each missing *eligible target fact* at reader, context, admission, validation, selection and publication boundaries.

### 4. Recover **large, source-valid families** at full-universe scale

Rank work by **estimated additional correct published facts**, using the 829-filing ledger and PDF-verified representative samples. Only for target-matched observations, expand source-evidenced **unit → entity → period** recovery where the measured first-loss data supports it. Ignore the mass of non-target `CONCEPT_UNRESOLVED` numeric cells. Reuse winning V1 structural methods for untabled rows, continuations, header ownership, and unit scopes. Never claim success for a candidate-count increase without a correct-output increase. Keep prior regressions as safety tests, **not** the main optimization metric.

### 5. Run the same-input full-universe loop after each meaningful integration

For each candidate architectural change:

1. Run **V2-only vs V1-assisted V2** on the same pinned PDFs with identical definitions.
2. Measure source-correct selected/publishable **gains and losses**; PDF-adjudicate new or changed selections, stratified by issuer regime/layout; investigate **all new critical errors**.
3. Record hard-key new/lost/re-keyed separately from duplicate SourceFact rows; identify source vs derived and count each once.
4. Show one waterfall of remaining V1-only **source-valid** target facts by reader → context → admission → validation → selection → publication.
5. Keep a change only if it produces a **material increase in correct output** with no unexplained loss of existing correct facts or new critical wrong selections. Otherwise revert or revise it rather than stacking another patch.

Produce one comparable report for every run:

| Required KPI | V1 | V2-only | V1-assisted V2 |
|---|---:|---:|---:|
| Identical PDF SHAs / errors | measured | measured | measured |
| PDF-verified correct target source facts | measured | measured | measured |
| Correct selected / draft-publishable **source** facts | measured | measured | measured |
| Correct draft-publishable **derived** facts | measured | measured | measured |
| Correct total draft-publishable, **same definition** | measured | measured | measured |
| Newly correct / correct lost / newly wrong | — | — | measured |
| V1-only **source-valid** gap remaining | measured | measured | measured |
| Withheld target facts by first *real* failure | measured | measured | measured |
| Critical wrong selections / OCR exceptions | measured | measured | measured |

**If the full-universe correct-output total is flat after a substantial integration, stop local patches.** Re-examine which source-evidence stage or downstream selector still blocks V1-scale facts; do not add more raw observations or dilute the validator.

## Definition of V1 parity and V2 production readiness

**Parity is not “9,838 eligible rows” or a +24 TARGET count.** It is V2 recovering at least the V1-level **PDF-correct, draft-publishable target output on the same input and definitions**, or a governed, PDF-adjudicated accounting that explains V1's invalid/unreportable surplus. The **8,924 floor remains a separate release gate** until officially reconciled; do not assert that 8,924 equals same-input, source-correct V1 facts.

Only switch `engine: v1` to `engine: v2` after all of the following are true:

- Same-input V1/V2 reconciliation complete; comparable output totals and the 8,924 floor addressed **without lowering it to manufacture parity**.
- No unexplained loss of V1/V2 previously correct facts; zero known critical wrong selections; material, repeatable correct-output recovery across the full universe.
- Fresh **unseen** PDF-adjudicated holdout passes the existing correctness and recall gates. Former N18 and the 829 files used for engineering are **not unseen proof**.
- Clean committed SHA, reproducible input/config/PDF manifests, deterministic rerun, green relevant CI, OCR/quarantine disposition, complete per-fact lineage, validated derived values and workbook/source-output reconciliation.
- Required governance/official approval recorded; production flag changed deliberately; V1 retained as rollback with post-cutover monitoring.

## Final instruction to agent

> **Make V2 the main production engine by recovering V1-scale *correct published* financial facts, not by increasing candidates or iterating one issuer at a time.** Use the pinned 829 PDFs and a same-definition V1 comparator; complete the source-evidenced V1 statement/header/unit bridge inside V2; protect existing correct V2 selections; trace every target fact through admission, selection and publication; integrate the highest-volume recoverable source-valid capabilities; repeatedly measure net **PDF-correct full-universe publication**. Keep V1 live and do not claim completion until source-correct parity, the unchanged governed floor, fresh unseen validation, reproducibility, CI, lineage and official cutover gates pass. Report measured gains honestly; never replace missing output with a plan or an intermediate counter.
