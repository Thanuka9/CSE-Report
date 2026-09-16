# CSE V2 Extraction — Verified Open Work and Final Engineering Path

**Repository:** `Thanuka9/CSE-Report`  
**Branch:** `v2/extraction-investigation`  
**Latest verified head (F3 checkpoint):** `a537f8fd83663b1d21a70b400428869256e882bf`  
**N11/N12 clean locked-33 SHA:** `2ff5d1ff1b04d0fbe559dc33d438e9072d030879` (freeze `ef4b200`)  
**Production engine:** `v1`  
**Coverage floor:** `min_draft_publishable = 8924`  
**Status:** NOT CERTIFIED / NOT READY FOR CUTOVER

## 1. Verified update since the previous audit

The branch advanced five commits beyond `99e658c8...`.

Completed or materially advanced:
- N02 LITE CandidateTrace investigation
- N03 SFCL CandidateTrace/source-truth cross-check
- N04 root-cause family record
- LITE real-PDF regression
- SFCL real-PDF regression
- F1 entity-subtitle ownership fix
- F3 duration-ownership refinement
- N08 gate diagnostic summary
- N09 header diagnostic summary
- failed T25 holdout evidence freeze
- corrected T25 truth/scoring
- N16 new unseen holdout identity manifest

Production must remain:

```yaml
extraction:
  engine: v1
```

## 2. First T25 holdout — repaired but permanently retired

The first unseen T25 holdout initially failed:

```text
entity-resolved recall 68.75%
3 false negatives
2 critical wrong facts
```

### LITE

The three missing facts were genuine V2 failures:

```text
TOP_LINE          889,239,000
PAT                79,190,000
OPERATING_PROFIT  156,042,000
```

CandidateTrace showed the first failure was `ENTITY_UNRESOLVED`: an explicit entity subtitle such as `Comprehensive Income - Group 31st December 2025` was dropped from the heading/context path.

A second latent defect was duration ownership: quarter-current cells could receive a 9M duration.

The branch now contains generalized F1/F3 fixes and real-PDF regressions.

### SFCL

The original two T25 critical wrong facts were caused by source-truth authoring, not an engine Company/Group swap.

The PDF's explicit `Company | Group` ordering matched V2's positional ownership. The T25 truth rows had labeled Company values as Group.

That truth error was corrected.

### Current inspected-set rescore

```text
entity-resolved reported facts  16
TP                              16
FN                               0
value/entity mismatches          0
critical wrong facts             0
entity-resolved recall         1.00
```

Important:

```text
THE FIRST T25 SET IS NOW INSPECTED DEV/REGRESSION DATA.
```

It must not be reused as the final unbiased holdout.

## 3. N16 — new unseen holdout is ready for N17

Locked manifest:

```text
tests/v2/source_truth/holdout_v2_identity_manifest.json
```

Status:

```text
SELECTED_PENDING_BLIND_ADJUDICATION
```

Count:

```text
13 filings
```

Diversity:

```text
BANK              3
FINANCE_COMPANY   3
INSURANCE         2
GENERAL           5
```

The set excludes the original locked 33, the failed first holdout, named regression issuers, known timeout issuers, and known regression PDFs.

Do not score this set before N17 blind truth exists.

# 4. OPEN — N17 Blind Adjudication

This is the next human/source-truth step.

Package prepared (blank; not gold):

```text
docs/v2/N17_BLIND_ADJUDICATION.md
tests/v2/source_truth/n17_blind_review_queue.json
```

Reviewer must not see:

```text
V1 values
V2 values
current extraction result
current selector result
```

Use only:
- source PDF
- Source Metric Truth Contract
- locked metric semantics

For each truth item record:

```text
filing_version_id
pdf_sha256
issuer_id
metric_code
source_presence
raw_source_label
raw_source_value
normalized_value
entity_scope
period_end
duration_months
comparison_role
currency
scale
unit_dimension
page
bbox
evidence_text
evidence_level
reviewer_1
reviewer_2 if required
adjudication_status
notes
split = HOLDOUT_V2
```

Source presence:

```text
REPORTED
NOT_REPORTED
AMBIGUOUS
```

Target source metrics:

```text
PAT
PBT
OPERATING_PROFIT
TOP_LINE
EPS_BASIC
EPS_DILUTED
NAVPS
TOTAL_EQUITY
TOTAL_ASSETS
TOTAL_LIABILITIES
```

Exclude derived/separate-domain metrics such as ROE, ROA, NPM, EPS_SELECTED, LIABILITIES_TO_EQUITY, and LAST_TRADED_PRICE.

# 5. OPEN — N18 Score the new holdout

Only after N17 truth is locked:

```text
run V2 on the same 13 PDFs
score SourceFacts against blind truth
```

Do not change extraction rules between truth lock and scoring.

Score:
- TP / FP / FN
- value mismatch
- entity mismatch
- period mismatch
- duration mismatch
- comparison mismatch
- unit/scale mismatch
- G01 withheld
- critical wrong facts
- source-reported recall
- numeric/entity/period/duration/unit accuracy

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

If N18 fails:
1. freeze the failure,
2. promote confirmed failures to DEV/regression,
3. fix generalized root causes,
4. lock another unseen holdout,
5. repeat.

Never retune on N16 and then call N16 the final passing holdout.

# 6. DONE — N11 Clean-SHA baseline

Completed on clean SHA `2ff5d1ff1b04d0fbe559dc33d438e9072d030879`:

- `working_tree_dirty=false`
- `all_deterministic=true`
- locked-33 baseline regenerated from disk

Canonical pointer: `tests/v2/universe/baseline_run_summary.json`.

# 7. DONE — N12 Canonical regeneration

Canonical summaries reconciled on the N11 SHA (freeze commit `ef4b200`):

```text
tests/v2/universe/investigation_freeze.json
tests/v2/universe/baseline_run_summary.json
tests/v2/universe/experiment_summary.json
tests/v2/universe/defect_family_ranking.json
docs/v2/EXTRACTION_REPORT.md
docs/v2/EXTRACTION_INVESTIGATION_STATUS.md
```

# 8. OPEN — N13 GitHub CI

There is still no GitHub Actions run and no PR for `v2/extraction-investigation`.

Open a PR or dispatch the workflow.

Require green:
- Ruff
- mypy
- `tests/v2`
- full pytest
- synthetic PDF gauntlets
- real-PDF regression suite
- production hardening
- coverage-floor governance
- workbook routing tests
- mandatory real-PDF acceptance tests

Local testing alone is not final branch validation.

# 9. OPEN — N14 Full-universe V2 challenger

The latest full-universe signal remains the older failed challenger:

```text
3,684 draft-publishable
vs
8,924 historical coverage alarm
```

That predates the latest F1/F3 work.

After N11-N13, run a fresh current-universe challenger with `--engine v2` while production default remains V1.

Report separately:

```text
PDFs attempted
PDFs extracted
PDFs quarantined
OCR-required failures
SourceFacts
DerivedFacts
production-selected facts
draft-publishable facts
concept unresolved
entity unresolved
period unresolved
duration unresolved
comparison unresolved
unit unresolved
conflict-withheld facts
duplicate-selection facts
```

Do not judge the universe only by one aggregate publishable count.

The 8924 number remains a governance alarm, not source truth.

# 10. STILL OPEN — material gate evidence

N08 is diagnostic only.

Decided from prior source truth:

```text
G01 KEEP
G03 KEEP
G09 KEEP
```

Still untested against source truth:

```text
G02 partial-context cascade
G04 OTHER-page exclusion
G05 continuation
G06 conflicting current values
G07 collapsed rows
G08 duplicate source selection
```

These do not block starting N17/N18, but they remain open before final certification if N18/N14 shows they are material.

Do not turn `cascade == per_column` into KEEP evidence without source-truth adjudication.

# 11. STILL OPEN — header bake-off

N09 measured only H0:

```text
H0 = MEASURED
H1 = UNTESTED / not harnessed
H2 = UNTESTED / not built
```

Do not claim an H0/H1/H2 winner.

Build/run H1/H2 only if N18 or N14 still shows material header/ownership defects after F1/F3.

# 12. OPEN — N20 exact September-10 replay

The exact September-10 frozen artifacts are still unavailable.

The September-05 diagnostic is not equivalent.

When the exact artifacts are available, freeze:
- same PDFs
- same PDF SHAs
- same filing versions
- same issuer universe
- same market snapshot
- same configuration inputs

Then run:

```text
V1 comparator
V2 A
V2 B
```

V1 is for disagreement discovery only, not source truth.

# 13. OPEN — certification

Certification remains blocked until:

```text
N17 blind truth complete
N18 new unseen holdout passes
N11 clean baseline complete
N12 canonical outputs reconciled
N13 CI green
N14 current-universe V2 challenger healthy
material unresolved gates addressed
N20 exact frozen replay completed when artifacts exist
```

Then produce:
- final `SOURCE_VALIDATED_BASELINE`
- final `EXTRACTION_CERTIFICATION_REPORT`
- final gate-decision record
- final universe acceptance report

# 14. OPEN — OFFICIAL review

OFFICIAL is the final human/governance gate, not the only current blocker.

OFFICIAL should happen only after engineering acceptance, new-holdout pass, healthy universe, clean reproducible baseline, CI pass, and governed frozen-replay disposition.

OFFICIAL then decides:

```text
promote V2
or
hold V1
```

# 15. Documentation adjustment required now

`docs/v2/EXTRACTION_INVESTIGATION_STATUS.md` is current.

But these still describe the first T25 holdout as actively failed:

```text
docs/v2/EXTRACTION_CERTIFICATION_REPORT.md
docs/v2/CUTOVER_CHECKLIST.md
```

Update them to:

```text
First T25 holdout:
FAILED initially
→ investigated
→ LITE extraction defects fixed
→ SFCL truth-label error corrected
→ rescored 1.0 on entity-resolved inspected facts
→ permanently retired from final holdout use

Final holdout path:
N16 identity locked
→ N17 blind truth pending
→ N18 scoring pending
```

Do not present the repaired first holdout as final certification evidence.

# 16. Recommended execution order from current head

```text
A00 Update stale certification/cutover wording.
A01 Freeze head a537f8fd... as current engineering checkpoint.
A02 N17 blind adjudication on holdout_v2_identity_manifest.json.
A03 Lock N17 truth.
A04 N18 score without changing extraction rules.
A05 If N18 fails, promote failures to DEV/regression and repeat engineering loop.
A06 If N18 passes, complete N11 clean-SHA locked-33 baseline.
A07 N12 regenerate all canonical investigation artifacts.
A08 N13 open PR / run GitHub Actions to green.
A09 N14 run full current-universe V2 challenger.
A10 Analyze universe failure clusters and resolve material remaining defects.
A11 Complete source-truth gate experiments only where universe/holdout evidence requires them.
A12 Build H1/H2 only if material header defects remain after F1/F3.
A13 N20 run exact Sept-10 replay when artifacts become available.
A14 Establish final SOURCE_VALIDATED_BASELINE.
A15 Produce final Extraction Certification Report.
A16 Conduct OFFICIAL human review.
A17 Only after approval consider `engine: v2` production cutover.
```

# 17. Hard stops

Do not:
- inspect N16 PDFs for tuning before N17 truth is locked,
- score N16 before blind truth exists,
- retune on N16 and call the same set final holdout,
- promote V2,
- lower 8924,
- delete V1,
- call H2 completed,
- call G02/G04-G08 decided,
- treat the first T25 set as final holdout,
- treat Sept-05 replay as Sept-10 acceptance,
- claim OFFICIAL is the only blocker.

# 18. Current verified state

```text
F3 checkpoint                     a537f8fd83663b1d21a70b400428869256e882bf
N11/N12 clean SHA                 2ff5d1ff1b04d0fbe559dc33d438e9072d030879
Freeze refresh                    ef4b200

LITE root cause                   diagnosed
LITE F1/F3 fixes                  landed
LITE regression                   added

SFCL engine ownership             matched PDF
SFCL truth-label error            corrected
SFCL regression/evidence          added

First T25 holdout                 retired to DEV/regression
First T25 inspected rescore       100% entity-resolved recall / 0 critical wrong

N08 gate diagnostics              done, several gates still UNTESTED
N09 header diagnostic             H0 only
H1/H2                             not built

N16 new holdout                   selected, 13 filings
N17 blind adjudication            PACKAGE READY (human fill pending)
N18 score                         BLOCKED ON N17

N11 clean baseline                DONE
N12 canonical regeneration        DONE
N13 CI                            OPEN (branch pushed; PR needs gh/token)
N14 full-universe challenger      OPEN

N20 Sept-10 exact replay          OPEN / artifacts missing
Certification                     BLOCKED
OFFICIAL                          BLOCKED
Production cutover                BLOCKED

Production engine                 V1
Coverage floor                    8924
```

# 19. Definition of ready for OFFICIAL

Move to OFFICIAL only when:

```text
new unseen holdout passes
critical wrong facts = 0
source-reported recall >= 97%
clean full-pipeline A/B deterministic
CI green
current-universe challenger healthy
source lineage complete
material failure clusters understood
coverage governance preserved
exact Sept-10 replay completed or formally governed if artifacts remain unavailable
```

Until then, V2 remains challenger-only and V1 remains production.
