# CSE V2 — AI Blind N17 Adjudication + Final Execution Plan

**Repository:** `Thanuka9/CSE-Report`  
**Branch:** `v2/extraction-investigation`  
**Production engine:** `v1`  
**Coverage floor:** `8924`  
**Goal:** remove N17 as a manual extraction bottleneck, finish the remaining evidence-driven V2 recovery work, then move directly through N18 → parity → CI → certification → controlled cutover.

---

# 1. Decision: N17 Will Be Performed as Blind AI Source Adjudication

The original N17 package says “human review”.

The actual reason for that rule is independence:

```text
truth must come from the source PDF
not from V1
not from V2
not from CandidateTrace
not from SourceFacts
not from selector output
```

ChatGPT can perform the document-reading task independently.

Therefore use:

```text
Reviewer 1:
chatgpt-blind-source-review-2026-09-19
```

This reviewer may use only:

```text
13 locked N16 source PDFs
docs/v2/SOURCE_METRIC_TRUTH_CONTRACT.md
tests/v2/source_truth/n17_blind_review_queue.json
locked metric semantics
```

Forbidden during adjudication:

```text
V1 values
V2 values
CandidateTrace
SourceFacts
workbook output
selector output
prior extraction results for the 13 holdout PDFs
```

This preserves the blind holdout.

## Governance wording

Do **not** falsely label the work as human-reviewed.

Use:

```text
AI_REVIEWER_1_COMPLETE
```

or:

```text
BLIND_SOURCE_REVIEW_COMPLETE
```

If institutional governance later requires an actual human signature, the human does **verification/sign-off**, not 130-value extraction from scratch.

That final review can be:

```text
source PDF
+
AI-produced gold
+
evidence page/text
```

with V1/V2 still hidden.

---

# 2. Locked N17 Selection Semantics

For every filing, adjudicate the requested target metric from the source PDF.

## FLOW metrics

```text
PAT
PBT
OPERATING_PROFIT
TOP_LINE
EPS_BASIC
EPS_DILUTED
```

Required target source context:

```text
period_end = 2025-12-31
duration_months = 3
comparison_role = CURRENT
required standalone entity:
  BANK → BANK
  FINANCE_COMPANY → COMPANY
  INSURANCE → COMPANY
  GENERAL → COMPANY
```

Q4 must be explicitly printed.

Forbidden:

```text
FY - 9M
12M substituted for Q4
9M substituted for Q4
6M substituted for Q4
GROUP substituted for COMPANY
GROUP substituted for BANK
```

If no explicit current 3M standalone source fact exists:

```text
source_presence = NOT_REPORTED
```

unless source evidence itself is genuinely ambiguous.

## STOCK metrics

```text
NAVPS
TOTAL_EQUITY
TOTAL_ASSETS
TOTAL_LIABILITIES
```

Required source context:

```text
period_end = 2025-12-31
comparison_role = CURRENT
duration_months = null
required standalone entity:
  BANK → BANK
  all others → COMPANY
```

---

# 3. Metric Truth Rules

## PAT

Use total profit/loss after tax for the period.

Do not use:

```text
profit attributable to owners
profit attributable to equity holders
OCI
PBT
```

## PBT

Use explicit profit/loss before tax.

No derivation.

## OPERATING_PROFIT

Use:

```text
operating profit
profit from operations
results from operating activities
operating profit before tax on financial services
```

Do not use EBITDA.

Do not use operating profit after financial-services taxes.

## TOP_LINE

Use regime-specific source semantics.

### BANK

Canonical source line:

```text
Gross income
```

Interest income or total operating income is not silently relabelled as Gross income.

### FINANCE_COMPANY

Allowed source concepts include:

```text
Total income
Net operating income
Income
Gross income
Interest income
Total operating income
```

Record the actual source label.

### INSURANCE

Use source-regime line:

```text
Insurance revenue
Gross written premium
Gross written contribution
Net earned premium
```

Do not infer SLFRS regime solely from issuer type.

### GENERAL

Use:

```text
Revenue
Total revenue
Net sales
Turnover
Revenue from contracts with customers
```

## EPS_BASIC

Explicit basic EPS / earnings per share.

Per-share unit.

Never apply statement `Rs '000`.

## EPS_DILUTED

Only reported when a diluted line exists.

Do not copy basic EPS.

## NAVPS

Explicit net asset value/assets per share only.

Do not derive from equity/shares.

## TOTAL_EQUITY

Explicit total equity.

Do not substitute:

```text
equity attributable to owners of parent
```

when a total line is absent.

## TOTAL_ASSETS

Explicit total assets.

## TOTAL_LIABILITIES

Explicit total liabilities only.

Never derive:

```text
assets - equity
```

---

# 4. Normalization Rules

Absolute monetary source:

```text
123 at LKR '000
→ 123000 LKR
```

Per-share:

```text
Rs/share → scale 1
cents/share → scale 0.01 to LKR/share
```

No FX conversion.

If unit/currency/scale is not evidenced:

```text
do not invent it
```

---

# 5. N17 Output Fields

For each of the 130 slots complete:

```text
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
adjudication_status
notes
split
```

Recommended reviewer/status:

```text
reviewer_1 = chatgpt-blind-source-review-2026-09-19
adjudication_status = AI_REVIEWER_1_COMPLETE
split = HOLDOUT
```

Where coordinates are not available from the review surface:

```text
bbox = null
notes = "Page/text source verified; bbox unavailable in adjudication surface."
```

Page + evidence text remain mandatory.

---

# 6. Evidence Levels

Use one of:

```text
CELL_EXPLICIT
COLUMN_HEADER_EXPLICIT
TABLE_EXPLICIT
STATEMENT_EXPLICIT
DOCUMENT_EXPLICIT
STRUCTURALLY_INFERRED
AMBIGUOUS
```

Preferred for values:

```text
CELL_EXPLICIT
```

Context may use explicit column/table/statement evidence.

---

# 7. Exact N17 Filing Set

```text
PABC.N0000   PAN ASIA BANKING CORPORATION PLC
UBC.N0000    UNION BANK OF COLOMBO PLC
SDB.N0000    SANASA DEVELOPMENT BANK PLC

COCR.N0000   COMMERCIAL CREDIT AND FINANCE PLC
AMCL.N0000   AMW CAPITAL LEASING AND FINANCE PLC
AFSL.N0000   ABANS FINANCE PLC

LGIL.N0000   LOLC GENERAL INSURANCE PLC
ATLL.N0000   AMANA TAKAFUL LIFE PLC

HUNA.N0000   HUNAS HOLDINGS PLC
CINS.N0000   CEYLINCO HOLDINGS PLC
JFP.N0000    JF PACKAGING PLC
NHL.N0000    NAWALOKA HOSPITALS PLC
SCAP.N0000   SOFTLOGIC CAPITAL PLC
```

Ten metrics per filing = **130 adjudication slots**.

---

# 8. Preferred Execution Surface: ChatGPT Work

Use ChatGPT **Work mode** if available because the repository states all 13 exact PDFs exist in the local workspace.

Work should access the exact files directly rather than relying on public mirrors.

## Work-mode instruction

Use this exact instruction:

```text
Open repository Thanuka9/CSE-Report on branch v2/extraction-investigation.

Complete N17 blind adjudication.

STRICT INPUT ISOLATION:
You may read ONLY:
1. tests/v2/source_truth/n17_blind_review_queue.json
2. tests/v2/source_truth/holdout_v2_identity_manifest.json
3. docs/v2/SOURCE_METRIC_TRUTH_CONTRACT.md
4. the 13 exact PDFs listed by local_file in the N16 manifest.

DO NOT OPEN:
- V1 outputs
- V2 outputs
- CandidateTrace
- SourceFacts
- score JSONs
- workbook output
- selector output
- prior gold involving these 13 filings

For each of the 130 metric slots:
- visually inspect the source PDF;
- use the current standalone 3-month source fact for FLOW metrics at 31 Dec 2025;
- use the current standalone point-in-time source fact for STOCK metrics;
- follow SOURCE_METRIC_TRUTH_CONTRACT.md exactly;
- do not derive Q4;
- do not derive TOTAL_LIABILITIES;
- do not substitute GROUP for COMPANY/BANK;
- record NOT_REPORTED when the required source fact is not explicitly reported;
- populate page and evidence_text;
- retain bbox when available;
- set reviewer_1 = "chatgpt-blind-source-review-2026-09-19";
- set adjudication_status = "AI_REVIEWER_1_COMPLETE".

Create:
tests/v2/source_truth/n17_ai_blind_gold.jsonl

Then validate:
- exactly 130 rows;
- no duplicate filing_version_id + metric_code;
- every row has source_presence;
- every REPORTED row has raw label/value, normalized value, entity, period, comparison, unit, page, evidence;
- flow REPORTED rows have duration_months=3;
- stock rows have duration_months=null;
- no V1/V2 output was opened.

After validation, create:
tests/v2/source_truth/n17_ai_blind_gold_manifest.json

The manifest must include:
- reviewer
- source contract SHA
- 13 PDF SHA256 values
- row count
- REPORTED / NOT_REPORTED / AMBIGUOUS counts
- validation checks
- explicit statement that V1/V2 outputs were not consulted.

Do NOT run N18 until the gold file and manifest are committed and frozen.
```

---

# 9. N17 Lock Step

After all 130 slots are complete:

```text
validate schema
↓
validate count = 130
↓
validate all exact PDF SHA256 values
↓
freeze gold file
↓
commit
↓
record gold commit SHA
```

Then change status to:

```text
N17 = AI BLIND GOLD LOCKED
```

Do not modify that gold after N18 begins.

If a source-review error is later discovered, preserve the original gold + score and issue a versioned correction rather than silently rewriting history.

---

# 10. Human Verification — If Governance Requires It

The project does not need a human to manually extract all 130 values again.

If a human signature is mandatory:

1. Randomly review a substantial sample plus every AI `AMBIGUOUS` row.
2. Review every `NOT_REPORTED` row.
3. Review high-risk rows:
   - entity ownership;
   - Q4 duration;
   - per-share scaling;
   - TOTAL_EQUITY;
   - TOTAL_LIABILITIES;
   - insurance TOP_LINE.
4. Resolve disagreements from the source PDF.
5. Record:

```text
reviewer_2
verification_status
review date
changed/not changed
reason
```

If no policy explicitly demands a biological-human reviewer, AI blind source review can be treated as the independent adjudication mechanism, provided that this governance decision is documented.

---

# 11. N18 Immediately After N17

Once gold is frozen:

```text
run V2 against n17_ai_blind_gold
```

Measure:

```text
source-reported recall
numeric correctness
entity correctness
period correctness
duration correctness
comparison correctness
unit correctness
critical wrong facts
```

Target direction:

```text
critical wrong = 0
source-reported recall >= 97%
numeric correctness >= 99.5%
context correctness near-total
```

Do **not** tune V2 before recording the first N18 score.

If N18 fails:

```text
freeze score
inspect failure
generalize fix
move failed holdout into regression evidence
use new independent proof set if another final holdout is required
```

---

# 12. Engineering Work That Continues in Parallel

N17 must no longer hold engineering.

Run simultaneously:

## E02
Full-universe CandidateTrace.

## E03-full
Universe target-fact-only first-failure census.

## E04-full
Universe V1↔V2 target-fact structural differential.

## OCR
Recover the 34 filings currently quarantined because Tesseract is missing.

Keep the 9 genuinely source-unusable cases explicitly quarantined.

## CI
Activate real GitHub Actions / PR checks.

---

# 13. Full-Universe Failure Census Required

The seed result says target first-failure is currently led by:

```text
ENTITY_UNRESOLVED = 707
```

But the seed is not enough.

Run the full universe and classify:

```text
PAGE_NOT_DISCOVERED
STATEMENT_NOT_DETECTED
TABLE_NOT_RECONSTRUCTED
TARGET_ROW_NOT_RECOVERED
NUMERIC_CELL_NOT_RECOVERED
CONCEPT_UNRESOLVED
ENTITY_UNRESOLVED
PERIOD_UNRESOLVED
DURATION_UNRESOLVED
COMPARISON_UNRESOLVED
UNIT_UNRESOLVED
SOURCEFACT_WITHHELD
VALIDATION_FAILED
SELECTION_WITHHELD
PUBLICATION_WITHHELD
PUBLISHED
```

Rank only **real target facts**, not all numeric cells.

---

# 14. E08 Is Conditional

Do not automatically port the rest of V1 header geometry.

The 44/44 DEV+LITE/SFCL target differential is:

```text
44/44 BOTH_RECOVER
```

Therefore denser V1 raw table/cell reconstruction is not itself proof of missing target facts.

Do E08 only if the full-universe target-fact census demonstrates a material header/entity/duration failure that V1 generalizable geometry can recover.

---

# 15. H1 / U1 Status

Current:

```text
H1
LITE: 40 SourceFacts
H0:   72 SourceFacts
→ H1 not promoted

U1
no SourceFact lift
→ U1 not promoted
```

Keep:

```text
H0 default
U0 default
```

Re-test only after a material structural improvement.

---

# 16. When to Run the Next Full-Universe Challenger

Do not run E13 merely because code changed.

Run E13 when at least one of these occurs:

```text
a generalized extraction component is promoted
a material source-truth failure is fixed
full-universe target census proves a recoverable family and the fix lands
```

Then measure:

```text
SourceFacts
draft-publishable
new valid facts
lost valid facts
critical wrong
target recall
entity/period/duration/unit resolution
OCR/pipeline errors
```

---

# 17. Parity Loop

Current V2:

```text
draft-publishable = 3748
floor = 8924
```

Guide:

```text
<6000        major recall problem
6000–8000    significant recovery, still below parity
8500–9200    V1 parity zone
9000–9700+   plausible mature V2 if source-valid
```

Do not lower the floor to manufacture success.

---

# 18. CI

Current issue:

```text
no real Actions evidence
```

This is not a reason to stop extraction work.

Before certification:

```text
open/activate PR
run ruff
run mypy
run pytest
run tests/v2
run real-PDF regressions
run source-truth score
run deterministic replay
run coverage governance
run workbook reconciliation
```

CI must be genuinely green.

---

# 19. Frozen Replay

Sept-10 exact replay remains desirable.

If exact artifacts are unavailable:

```text
document what is missing
↓
approve a governed replacement frozen snapshot
↓
run V1 and V2 on identical inputs
```

Do not falsely label a substitute as Sept-10.

Do not permanently block the project if an explicit governance replacement is approved.

---

# 20. Final Certification Inputs

Certification should require:

```text
V1-parity or better correct coverage
N18 passing blind score
critical wrong = 0
clean committed SHA
CI green
OCR recovered/quarantined
lineage complete
workbook reconciliation
fixed-input replay
OFFICIAL approval
V1 rollback
```

---

# 21. Cutover

Final operation:

```text
V1 production
+
V2 shadow
↓
same-input comparison
↓
source review of material disagreement clusters
↓
certification
↓
OFFICIAL
↓
V2 becomes default
↓
V1 remains rollback
```

Retire V1 only after stable V2 production observation.

---

# 22. Immediate Next Actions

Run these now in parallel:

```text
1. N17 AI blind adjudication in Work mode on exact local PDFs.
2. E02 full-universe CandidateTrace.
3. E03-full target-only failure census.
4. E04-full target structural differential.
5. Restore Tesseract and rerun 34 OCR-quarantined filings.
6. Activate real GitHub CI.
```

Then:

```text
N17 gold locked
→ N18

E02/E03/E04
→ identify top real recoverable failure
→ generalized fix
→ promote only winner
→ E13 full-universe challenger
→ repeat to parity
```

---

# 23. No More Artificial Blockers

The following should **not** hold V2:

```text
H2 not built
unused experimental gates
optional bake-offs
documentation polish
manual re-extraction of all N17 values by a person
unpromoted H1/U1
exact historical replay while a governed replacement is being approved
```

The real critical path is:

```text
source correctness
+
unseen blind validation
+
universe recall/parity
+
reproducibility
+
publication integrity
+
approval
```

---

# 24. Definition of Done

V2 is finished when:

```text
1. unseen holdout passes;
2. critical wrong facts = 0;
3. V2 reaches defensible V1 parity or better;
4. full-universe output is reproducible;
5. important OCR failures are recovered or explicitly quarantined;
6. every published fact traces to source PDF evidence;
7. workbook reconciliation passes;
8. CI is green;
9. replay requirement is satisfied or governed replacement approved;
10. OFFICIAL approves;
11. V1 rollback remains available.
```

This is the shortest path to finish V2 without recreating V1's patch ceiling.
