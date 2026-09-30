# CSE V2 Extraction — Next Engineering Steps and Project Recovery Plan

**Repository:** `Thanuka9/CSE-Report`  
**Active branch:** `v2/extraction-investigation`  
**Latest audited head:** `99e658c8affa42864031c81f8e2f85c9fd096acb`  
**Production engine:** `v1`  
**Coverage floor:** `min_draft_publishable = 8924`  
**Current V2 status:** NOT production-ready and NOT engineering-complete

## 1. Current evidence

The Pre-T10 investigation architecture was improved correctly:
- Source extraction is separated from production entity selection.
- CandidateTrace uses the actual in-run candidates.
- Production selection is recorded separately.
- Full-pipeline A/B rereads PDFs independently.
- Source Metric Truth Contract was strengthened.
- A new 12-filing unseen holdout was created.
- OCR runtime packaging was demonstrated with Tesseract in Docker.
- Production remains pinned to V1.

But the first unseen T25 holdout failed:

```text
24 adjudicated items
20 REPORTED
16 entity-resolved reported facts

TP                         11
False negatives             3
Value/entity mismatches     2
G01 fail-closed withholds   4

Entity-resolved recall  68.75%
Critical wrong facts        2
```

Therefore the branch cannot be described as “engineering complete” or “blocked on OFFICIAL only.”

---

## 2. P0 — Correct project status documents

Update:
- `docs/v2/EXTRACTION_INVESTIGATION_STATUS.md`
- `docs/v2/EXTRACTION_CERTIFICATION_REPORT.md`
- `docs/v2/CUTOVER_CHECKLIST.md`
- `docs/v2/SOURCE_VALIDATED_BASELINE.md`
- `docs/v2/IMPLEMENTATION_STATUS.md`
- `docs/v2/DECISIONS.md`

Required changes:

```text
T24 = REOPENED — unseen holdout exposed new defect families
T25 = FAILED — recall 68.75%; 3 FN; 2 critical wrong facts
T28 = BLOCKED ON ENGINEERING
T29 = BLOCKED ON ENGINEERING + OFFICIAL REVIEW
```

Do not mark fail-closed universe runs as acceptance passes. Fail-closed is safe behavior, not successful validation.

---

## 3. P0 — Diagnose LITE missing facts

Blind source truth for `LITE.N0000` / Laxapana PLC identified:

```text
TOP_LINE          889,239,000
PAT                79,190,000
OPERATING_PROFIT  156,042,000
```

V2 missed all three.

Use exact CandidateTrace and determine the first failure stage for each:

```text
page routing
statement detection
table detection
table reconstruction
row reconstruction
concept matching
entity ownership
period ownership
duration ownership
comparison-role ownership
unit/scale
SourceFact admission
conflict handling
publication
production selection
```

For each failure record:
- source page
- source row label
- source value
- candidate ID
- first failure stage
- reason code
- root cause
- generalized fix
- permanent regression test path

Do not guess the root cause from counts.

---

## 4. P0 — Diagnose SFCL wrong entity/value ownership

Blind source truth for `SFCL.N0000` / Senkadagala Finance:

```text
GROUP TOP_LINE = 2,572,716,568
GROUP PAT      =   344,406,148
```

V2 sees relevant numbers but associates/chooses the wrong value/entity combinations.

Primary hypothesis to test: **header / column ownership**.

Inspect:
- header spans
- Group / Company ownership
- current / comparative ownership
- 3M / cumulative ownership
- merged header propagation
- date ownership
- duplicate identity groups
- conflict resolution
- production selector

The correct Group-quarter-current cell must retain correct:
`metric`, `entity_scope`, `period_end`, `duration_months`, `comparison_role`, `unit`.

Because the holdout reports 2 critical wrong facts, this is P0.

---

## 5. P0 — Promote failed holdout cases into DEV/regression

The first T25 holdout has now been inspected. It is no longer an unbiased final holdout.

At minimum create permanent real-PDF regressions for:

```text
LITE — TOP_LINE
LITE — PAT
LITE — OPERATING_PROFIT
SFCL — TOP_LINE
SFCL — PAT
```

Retain HNBF/NAMU as G01 fail-closed evidence.

Rule:

```text
Once a holdout case influences engineering decisions,
it becomes DEV/regression data.
```

Do not reuse this same 12-file set as the final holdout.

---

## 6. P0 — Fix generalized root causes only

Required loop:

```text
source-confirmed defect
→ root-cause family
→ generalized fix
→ permanent regression
→ DEV rerun
```

Do not add:
- issuer-specific constants
- file-specific page offsets
- hard-coded expected values
- V1-derived truth
- issuer-name entity shortcuts

Possible generalized families:
- header graph / column ownership
- statement boundary detection
- row reconstruction
- merged span propagation
- date/current/comparative ownership
- duration ownership
- duplicate source ranking
- finance-company layouts
- multi-line concept labels

---

## 7. P1 — Reopen the header-engine investigation

SFCL makes header/column context a high-priority risk again.

Run:

```text
H0 — current V2
H1 — useful V1 hierarchical geometry techniques
H2 — new V2 HeaderGraph / ColumnHeaderPath
```

Score:
- entity
- period
- duration
- comparison
- unit ownership
- wrong-cell rate
- critical wrong fact rate

Cover real layouts:
- 2-col current/comparative
- 4-col Group/Company
- 4-col current/comparative
- 6-col quarter/YTD
- 8-col Group/Company quarter/YTD
- Bank/Group
- Company/Group
- Consolidated/Company
- split/multi-row date headers
- merged entity spans
- note/% columns

H2 replaces H0 only if source-truth evidence supports it.

---

## 8. P1 — Complete material gate experiments

Still unresolved:
- G02 partial-context cascade
- G04 OTHER-page exclusion
- G05 continuation
- G06 conflicting current values
- G07 collapsed rows
- G08 duplicate source selection

For each gate, test applicable variants:

```text
CURRENT
DISABLED
NARROWED
REPLACEMENT
```

Measure:
- TP
- FP
- FN
- precision
- recall
- critical wrong facts
- correct facts recovered
- incorrect facts admitted

Decision must become:
`KEEP`, `NARROW`, `REPLACE`, or `REMOVE`.

---

## 9. P1 — Keep G01 fail-closed while testing better evidence

Do not weaken G01 simply to improve recall.

Test evidence levels independently:
- cell-local
- column header
- statement title
- table title
- document heading
- single-entity structural proof
- issuer metadata

Issuer metadata remains selection context, not automatic source truth.

Goal: determine whether stronger document/structural evidence can safely resolve entity without creating false Company/Group assignments.

---

## 10. P1 — Keep stages separate

Required architecture:

```text
PDF
↓
Source Candidates
↓
SourceFacts
↓
Validation
↓
DerivedFacts
↓
Production Selection
↓
Publication / Workbook
```

Do not collapse:
- extraction misses
- fail-closed context withholds
- production selection
- publication rejection
into one count.

---

## 11. P1 — Generate a clean committed canonical baseline

Current evidence contains `:dirty:` run identities.

After fixes:
1. commit all code,
2. ensure clean working tree,
3. regenerate baseline.

Required outputs:
- `run_manifest.json`
- `source_manifest.json`
- `candidate_trace.parquet`
- `source_facts.parquet`
- `derived_facts.parquet`
- `production_selection.parquet`
- `issue_ledger.parquet`
- `issue_summary.csv`
- `experiment_summary.json`
- `defect_family_ranking.json`
- `extraction_report.md`

Every artifact must reference one clean `actual_code_sha`.

---

## 12. P1 — Run GitHub Actions

The investigation branch still needs CI validation.

Open a PR or dispatch the workflow and require green:
- Ruff
- mypy
- `tests/v2`
- full pytest
- synthetic PDF gauntlets
- real-PDF regressions
- production hardening
- coverage-floor governance
- workbook routing tests

Local testing alone is not final branch validation.

---

## 13. P1 — Rerun the full current universe

Historical V2 challenger result:

```text
3,684 draft-publishable
vs
8,924 historical coverage alarm
```

remains a failure signal.

After generalized fixes, rerun the current full universe with `--engine v2` while `configs/app.yml` stays `engine: v1`.

Report separately:
- SourceFacts
- DerivedFacts
- production-selected facts
- draft-publishable facts
- quarantined filings
- OCR failures
- concept unresolved
- entity unresolved
- period unresolved
- duration unresolved
- comparison unresolved
- unit unresolved

Do not judge the run only by one aggregate count.

---

## 14. P1 — Select a new unseen holdout

After LITE/SFCL and any additional confirmed defect families are fixed, lock a **new** 10–15 filing holdout.

Must be:
- not in original 33
- not in failed first holdout
- not manually inspected
- not used in regression
- not used for rule/alias tuning

Include diversity across:
GENERAL, BANK, FINANCE_COMPANY, INSURANCE, Group/Company, Bank/Group, Consolidated/Company, native, scanned, mixed OCR, 2/4/6/8-column layouts, varied units, notes/share-info, non-calendar quarters.

Blind adjudication must happen without seeing V1/V2 values.

Acceptance:

```text
critical wrong source facts = 0
source-reported target-fact recall >= 97%
numeric accuracy >= 99.5%
entity accuracy >= 99.8%
period accuracy >= 99.8%
duration accuracy >= 99.8%
unit/scale accuracy >= 99.8%
```

Any critical wrong fact reopens engineering.

---

## 15. T26 exact frozen-universe replay remains open

Current T26 evidence is based on a September-05 snapshot, not the exact September-10 frozen universe.

Do not mark exact fixed-input replay accepted.

When exact artifacts are available, use:
- same September-10 PDFs
- same PDF SHAs
- same market snapshot
- same issuer universe
- same filing revisions

Run:

```text
V1 comparator
V2 A
V2 B
```

V1 is disagreement evidence only, not truth.

---

## 16. Source-validated baseline remains provisional

Current source truth from T10 + failed T25 is useful evidence but not institutional certification.

Do not lower `min_draft_publishable = 8924` from this sample.

A future replacement baseline requires:
- institutional gold
- a new passing holdout
- full-universe evidence
- governed approval

---

## 17. Updated execution order

```text
N00 Correct overstated status documents.
N01 Freeze current failed-holdout evidence.
N02 Diagnose LITE with CandidateTrace.
N03 Diagnose SFCL with CandidateTrace/header evidence.
N04 Classify generalized root causes.
N05 Add permanent real-PDF regressions.
N06 Implement generalized fixes.
N07 Rerun DEV/source-truth scoring.
N08 Execute affected gate experiments.
N09 Run H0/H1/H2 header bake-off.
N10 Run unit/page/continuation experiments if implicated.
N11 Commit everything on a clean SHA.
N12 Regenerate canonical clean-head baseline.
N13 Run GitHub Actions.
N14 Run current-universe V2 challenger.
N15 Review remaining root-cause clusters.
N16 Select a NEW unseen holdout.
N17 Blindly adjudicate the new holdout.
N18 Score against acceptance gates.
N19 If failed: promote failures to DEV and repeat.
N20 If passed: perform exact frozen-universe replay when artifacts exist.
N21 Establish final source-validated baseline.
N22 Produce final Extraction Certification Report.
N23 Conduct OFFICIAL human review.
N24 Only after approval, consider V2 production cutover.
```

---

## 18. Hard stops

Do not:
- promote V2,
- lower the 8924 floor,
- delete V1,
- reuse the failed T25 set as final holdout,
- patch LITE/SFCL with issuer-specific constants,
- use V1 as source truth,
- infer Company from silence,
- infer Q4 as FY−9M,
- treat fail-closed as a passing acceptance test,
- claim OFFICIAL review is the only remaining blocker.

---

## 19. Definition of extraction completion

V2 extraction is complete only when:
- nearly all source-reported target facts are recovered,
- value/metric/entity/period/duration/comparison/unit are correct,
- critical wrong source facts = 0,
- every rejection is reason-coded,
- major gates are experimentally resolved,
- a fresh unseen holdout passes,
- full-pipeline A/B is deterministic,
- current-universe run is healthy,
- source lineage is complete.

Only then resume final V2 production cutover.

---

## 20. Current project verdict

```text
Architecture direction          GOOD
Investigation framework         MUCH IMPROVED
Source/selection separation     FIXED
DEV diagnostic                  USEFUL
First unseen holdout            FAILED
Critical wrong facts            PRESENT
Engineering complete            NO
Certification ready             NO
OFFICIAL-only stage             NO
Production cutover ready        NO
```

The failed holdout is now engineering evidence and must drive the next root-cause repair cycle.
