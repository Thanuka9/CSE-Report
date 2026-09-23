# CSE V2 — N18 Failure Triage and Recovery Execution Plan

**Repository:** `Thanuka9/CSE-Report`  
**Branch:** `v2/extraction-investigation`  
**Frozen N17 gold commit:** `639454a2`  
**Frozen N18 first score commit:** `dc146572`  
**Gold composition:** `115 REPORTED / 15 NOT_REPORTED / 0 AMBIGUOUS`  
**First N18 signal:** `TP 23 / FN 68 / recall 0.20 / numeric correctness 0.74 / 8 critical wrong`  
**Purpose:** convert the first unseen holdout failure into generalized engineering fixes without turning the holdout into another patch cycle.

---

# 1. Freeze Rule

The first N18 score is historical evidence.

Do not overwrite it.

Do not regenerate it after code changes and pretend it is still the original unseen result.

Preserve:

```text
N17 frozen gold
+
N18 first score
+
code SHA
+
gold SHA
+
all failure details
```

Once engineering uses these failures for tuning:

```text
N18 set becomes regression / DEV evidence
```

It is no longer the final unseen proof set.

A new unseen holdout is required only after the major fixes are complete.

---

# 2. Correct Accounting of the N18 Result

Gold rows marked `REPORTED`:

```text
115
```

Exact true positives:

```text
23
```

Missing / false negatives:

```text
68
```

Therefore:

```text
115 - 23 - 68 = 24
```

There are approximately **24 produced-but-not-correct reported facts**.

Of these:

```text
8 = critical wrong
~16 = other value/context mismatches
```

So the failure is not simply:

```text
68 missing
```

The real picture is:

```text
23 correct
68 absent
24 produced but wrong
```

This means V2 currently has **both recall and correctness defects**.

---

# 3. Triage Priority

Do not start with the 68 missing facts.

Fix emitted wrong facts first.

Correct order:

```text
P0-A  8 critical wrong
P0-B  remaining produced-but-wrong facts
P0-C  any output for NOT_REPORTED gold
P1    68 missing facts
```

Reason:

```text
missing fact
= recall problem

wrong emitted fact
= recall + correctness + publication-risk problem
```

A system that emits a wrong value is more dangerous than one that abstains.

---

# 4. Required Root-Cause Taxonomy

Every failure must be assigned to one primary root-cause family.

## False positive

```text
FALSE_POSITIVE_NOT_REPORTED
```

Use when gold says source metric is not reported but V2 emits a fact.

---

## Wrong-context / wrong-value families

```text
WRONG_ENTITY
WRONG_PERIOD
WRONG_DURATION
WRONG_COMPARISON_ROLE
WRONG_UNIT
WRONG_SCALE
WRONG_VALUE_CELL
WRONG_CONCEPT
WRONG_SELECTION
```

Definitions:

### WRONG_ENTITY
Example:

```text
GROUP selected instead of COMPANY
GROUP selected instead of BANK
COMPANY/BANK ownership bound incorrectly
```

### WRONG_PERIOD
Example:

```text
prior year selected
wrong date column selected
```

### WRONG_DURATION
Example:

```text
9M selected instead of 3M
12M selected instead of Q4
```

### WRONG_COMPARISON_ROLE
Example:

```text
comparative selected as current
```

### WRONG_UNIT
Example:

```text
per-share treated as monetary
currency missing/wrong
```

### WRONG_SCALE
Example:

```text
Rs '000 interpreted as Rs
per-share inherited statement thousands
```

### WRONG_VALUE_CELL
Metric/context are otherwise correct but the adjacent numeric cell is wrong.

### WRONG_CONCEPT
Wrong row semantic matched.

### WRONG_SELECTION
Correct candidate exists, but selector chooses another candidate.

---

## Missing-structure families

```text
PAGE_NOT_FOUND
STATEMENT_NOT_FOUND
TABLE_NOT_FOUND
ROW_NOT_FOUND
CELL_NOT_FOUND
```

Use the **first missing structural stage**.

---

## Missing-resolution families

```text
ENTITY_UNRESOLVED
PERIOD_UNRESOLVED
DURATION_UNRESOLVED
COMPARISON_UNRESOLVED
UNIT_UNRESOLVED
CONCEPT_UNRESOLVED
```

---

## Downstream withholding families

```text
SOURCEFACT_WITHHELD
VALIDATION_WITHHELD
SELECTION_WITHHELD
PUBLICATION_WITHHELD
```

Use only when upstream structure/context is valid and the fact is later dropped.

---

# 5. Required Triage Record

Create one row per N18 failure.

Required fields:

```text
filing_version_id
issuer_id
issuer_type
metric_code

gold_source_presence
gold_raw_label
gold_raw_value
gold_normalized_value
gold_entity_scope
gold_period_end
gold_duration_months
gold_comparison_role
gold_currency
gold_scale
gold_page
gold_evidence_text

v2_fact_present
v2_raw_value
v2_normalized_value
v2_entity_scope
v2_period_end
v2_duration_months
v2_comparison_role
v2_currency
v2_scale
v2_source_page

n18_result
severity
first_failure_stage
root_cause_family

source_verified
generalized_fix_candidate
notes
```

Recommended output:

```text
tests/v2/universe/n18_failure_triage.csv
tests/v2/universe/n18_failure_triage.json
```

---

# 6. Triage Procedure

For each failed row:

## Step 1 — Open the frozen gold row

Use:

```text
n17_ai_blind_gold.jsonl
```

Do not modify it.

---

## Step 2 — Open V2 result used in the original N18 run

Use only the frozen engine output from that score.

Do not rerun new code yet.

---

## Step 3 — Compare exact dimensions

Check:

```text
metric
value
entity
period
duration
comparison role
currency
scale
page
```

---

## Step 4 — Inspect the source PDF if required

Use source evidence to determine the real first failure.

Do not infer the root cause from the score label alone.

Example:

```text
gold PAT exists
V2 missing
candidate row exists
entity unresolved
```

Root cause:

```text
ENTITY_UNRESOLVED
```

Not:

```text
SOURCEFACT_WITHHELD
```

---

## Step 5 — Assign exactly one primary root cause

Secondary issues may be listed in notes.

Do not assign multiple primary causes to one row.

This prevents double-counting.

---

# 7. P0-A — Critical Wrong Cases

Inspect all 8 first.

Required output table:

| Filing | Metric | Gold | V2 | Root Cause | Generalized Fix |
|---|---|---|---|---|---|

For every critical wrong case answer:

```text
Did the correct candidate exist?
Was the wrong candidate structurally closer?
Was entity ownership wrong?
Was period/duration ownership wrong?
Was scale/unit wrong?
Was concept wrong?
Did selection choose the wrong valid candidate?
```

No code change until all 8 are clustered.

---

# 8. P0-B — Remaining Produced-but-Wrong Cases

Expected count:

```text
~16
```

These matter because V2 emitted something.

Group by:

```text
root cause
metric
issuer type
statement type
layout family
```

Look for repeated patterns.

Examples:

```text
WRONG_ENTITY x 7
WRONG_DURATION x 5
WRONG_SCALE x 3
WRONG_SELECTION x 1
```

A repeated family is a candidate for generalized repair.

---

# 9. P0-C — NOT_REPORTED False Positives

Gold:

```text
15 NOT_REPORTED
```

Check whether V2 emits any facts for those slots.

Every such case becomes:

```text
FALSE_POSITIVE_NOT_REPORTED
```

This category is high severity.

Examples:

```text
attributable profit promoted to PAT
owners' equity promoted to TOTAL_EQUITY
basic EPS copied to diluted EPS
assets-equity treated as TOTAL_LIABILITIES
interest income incorrectly treated as bank Gross income
```

These must be eliminated before production.

---

# 10. P1 — Missing Facts

Only after wrong-produced cases are understood, triage the 68 missing rows.

For each missing fact identify the first failure:

```text
page
statement
table
row
cell
concept
entity
period
duration
comparison
unit
SourceFact
validation
selection
publication
```

Then aggregate.

Example result:

```text
ENTITY_UNRESOLVED       21
DURATION_UNRESOLVED     15
ROW_NOT_FOUND           11
STATEMENT_NOT_FOUND      9
SELECTION_WITHHELD       7
CONCEPT_UNRESOLVED       5
```

The real counts must come from the frozen triage, not assumptions.

---

# 11. Aggregate Outputs Required

Generate:

```text
n18_failure_by_root_cause.csv
n18_failure_by_metric.csv
n18_failure_by_issuer_type.csv
n18_failure_by_statement_type.csv
n18_failure_by_severity.csv
```

Also create:

```text
n18_failure_summary.json
```

with:

```text
total_gold_reported
TP
missing
produced_wrong
critical_wrong
false_positive_not_reported

root_cause_counts
metric_counts
issuer_type_counts
```

---

# 12. Engineering Prioritization Formula

Rank generalized fixes using:

```text
priority =
severity
×
number_of_real_target_facts_affected
×
generalizability
```

Prefer:

```text
one fix → many filings / metrics
```

Reject:

```text
one fix → one issuer only
```

---

# 13. E02 Must Run in Parallel

Do not stop the full-universe CandidateTrace work.

Run:

```text
N18 failure triage
+
E02 full-universe CandidateTrace
```

Use the same root-cause vocabulary.

N18 tells us:

```text
which failures are definitely real
```

E02 tells us:

```text
how widespread each family is
```

The intersection determines priority.

Example:

```text
N18:
WRONG_ENTITY is P0

Universe:
ENTITY_UNRESOLVED affects hundreds of target facts

→ entity ownership becomes top generalized engineering target
```

---

# 14. Fix Rule

Do not patch individual holdout cases.

Every proposed fix must answer:

```text
1. What generalized root cause does it fix?
2. Which N18 failures belong to that family?
3. How many universe target facts show the same family?
4. What source evidence supports the rule?
5. What negative cases protect against overreach?
```

---

# 15. Fix Development Sequence

For each root-cause family:

```text
inspect all N18 examples
↓
inspect universe examples
↓
identify generalized rule
↓
implement
↓
add positive tests
↓
add negative tests
↓
run DEV/regression
↓
run former N18 set as regression
↓
measure no new critical wrong
↓
promote only if winner
```

---

# 16. Important Holdout Rule

After using N18 failures for engineering:

```text
N16/N17/N18 set = regression evidence
```

It must not later be called unseen.

Do not repeatedly rerun it and claim final holdout success.

Use it for:

```text
regression
root-cause verification
guardrails
```

---

# 17. New Final Holdout

Create the next unseen proof set **only after major fixes are complete**.

Do not create it now.

Reason:

```text
creating too early
→ inspecting it
→ burning another holdout
```

The next holdout should be selected after:

```text
major P0 fixes
+
major recall fixes
+
universe parity
```

Then:

```text
new identity-only selection
→ blind source gold
→ freeze
→ one final score
```

---

# 18. What to Do After Triage

Expected sequence:

```text
T1  complete N18 triage
T2  rank root causes
T3  compare with E02 universe counts
T4  choose top generalized P0 fix
T5  implement + regressions
T6  verify former N18 failures
T7  promote only if safe
T8  run full-universe challenger
T9  repeat for next major family
T10 reach V1 parity zone
T11 select new unseen holdout
T12 blind adjudication
T13 final score
T14 CI + replay + lineage + workbook
T15 certification
T16 OFFICIAL
T17 cutover
```

---

# 19. Hard Stops

Do not accept a fix if:

```text
it requires issuer identity
it requires exact page number
it fixes only one holdout filing
critical wrong count increases
NOT_REPORTED false positives increase
source-truth correctness decreases
previous valid facts disappear unexplained
```

---

# 20. Immediate Next Action

Start now with:

```text
8 critical wrong
↓
remaining produced-but-wrong
↓
15 NOT_REPORTED false-positive check
↓
68 missing
↓
aggregate root causes
```

Do not implement fixes before the clusters are complete.

---

# 21. Definition of Triage Complete

N18 triage is complete only when:

```text
every failed reported slot has one primary root cause
every NOT_REPORTED slot has false-positive status checked
all 8 critical wrong are source-reviewed
produced-wrong count reconciles
68 missing are assigned first-failure stages
root-cause aggregates exist
top 2–4 generalized engineering targets are ranked
```

---

# 22. Final Direction

The first unseen holdout has done its job.

It proved:

```text
coverage is poor
AND
wrong-context/value output is real
```

The next phase is therefore:

```text
freeze evidence
→ triage exact failures
→ identify generalized causes
→ fix P0 correctness first
→ fix major recall families
→ verify at universe scale
→ reach parity
→ use a fresh unseen holdout for final proof
```

Do not return to issuer-by-issuer patching.
Do not restart the architecture.
Do not continue certification while P0 wrong-output defects remain.
