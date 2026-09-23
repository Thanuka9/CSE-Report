# CSE Financial Reports ETL — Final Agent Execution Plan
## Make V2 the production engine at defensible V1 parity

**Purpose:** One coordinated engineering execution, from the current flat full-universe recovery result through a production-ready V2 release. This is **not** a request for another investigative plan, another small N18 patch, or an intermediate status handoff. Engineering agents own the remaining implementation, repeated measurements, validation, CI, documentation, and production preparation. If all gates pass, the only remaining decision for the human owner should be **OFFICIAL approval and authorization for controlled cutover**.

**Repository:** `Thanuka9/CSE-Report` · active work branch: `v2/extraction-investigation` (use the actual checked-out branch/worktree, confirm head before changes).  
**Production today:** V1. Do not change the production default while engineering or certification fails.  
**Frozen comparison cohort:** 829 selected PDFs, same exact pinned SHA-256s and filing revisions, target periods `2025-12-31`, `2026-03-31`, `2026-06-30`.  
**Governance floor:** 8,924 historical draft-publishable; preserve this gate unless a separate governed, source-supported decision replaces it. **Do not pretend that it uses the same metric/output definition as TARGET draft-selected.**

> **Input truth:** The user's latest completed *local* measurements supersede older stored GitHub artifacts. At authoring, the connected GitHub branch still showed the earlier scaffold commit `c5bbe51`, so agents must inspect/preserve newer local code, tests, reports and stashes and commit them coherently. This document does not claim the local changes were independently pushed or validated here.

---

## 1. The single outcome agents are responsible for

**Make V2 recover at least V1-scale *correct, source-supported* target financial facts on comparable inputs, with V2's source-truth validation, lineage, and safe publication rules, then complete every engineering/certification gate required to make it the main engine.**

Success is **not** an increased candidate count; a smaller unresolved bucket; a +3/+18 improvement; a zero-critical-wrong number achieved by withholding most facts; a nice regression report; a document saying `DONE`; or a favorable count obtained by mixing source/derived/selection definitions.

At the end the agent must deliver one of two honest states:

- **READY FOR OFFICIAL DECISION:** Full quantitative/source-truth/CI/replay/lineage/rollback evidence supports cutover; V1 remains the active default until approval.
- **BLOCKED — WITH EVIDENCE:** The actual unresolved gate and source-backed facts are named; agents continue engineering rather than claiming that only OFFICIAL remains. Never promote despite a failed gate.

Do not set a fictitious number of code edits or say that the next single patch guarantees parity.

---

## 2. Baseline to freeze — do not rewrite history

Latest user-reported, full 829-PDF, zero-filing-error same-cohort TARGET comparison after note/share-count and table-unit corrections:

| Measurement | V2 only | V1-assisted V2 | Meaning |
|---|---:|---:|---|
| TARGET draft-selected | **2,816** | **2,819** | **+3**, essentially flat at universe scale |
| TARGET draft-selected in 80-file sample | **305** | **323** | +18 on sample; **not** universe proof |
| Earlier E13 total draft-publishable | **3,854** | Not yet reconciled in same definition | **Do not add +3 to 3,854** |
| Historical coverage gate | — | **8,924** | Separate universe/output-definition and governance check |

Prior work found 298,541 original discovery-only V1 observations with missing entity/period/unit; a context bridge made some admissible. Unsafe note-index/share-count false positives (JAT TOP_LINE=4; HAYLEYS=6000; SIGIRIYA EPS=share count) were corrected; the latest honest full-universe TARGET lift is +3. Legacy interim +24 and +171 cannot substitute for the latest result. V1-only engine keys (6,466 in an earlier diagnostic) **were not yet independently PDF-adjudicated as correct facts**. Do not use them as source truth.

Freeze copies/checksums of: the pinned cohort manifest, latest V2-only and assisted manifests, latest `gap_summary.json`, `KPI_DEFINITION_RECONCILE.md`, `PARITY_EXECUTION_STATUS.md`, `NON_REGRESSION_INVESTIGATION.md`, current full output/review ledger, original blind N17/N18 scores, E13 reference, and the 8,924 gate. Preserve unrelated stashes/WIP. Mark old 812-only and zero-cohort runs **superseded, not deleted**. Record actual code SHA, PDF SHA list, input/config/market snapshot hashes, parser/OCR versions, run IDs, dirty-state flag and output checksums. Resolve the earlier “clean” folder vs `working_tree_dirty: true` manifest contradiction before calling any run reproducible.

---

## 3. Guardrails that do not change

1. V1 stays production until governed approval; V2 is a feature-flagged challenger.
2. Never use V1 workbook values, issuer/security metadata, current query, or a gold answer to manufacture PDF source evidence.
3. Source metric/entity/period/duration/comparison/unit must be supported by the PDF (cell, row, header, statement, or explicit evidenced continuation). Unlabeled grids do **not** become COMPANY/BANK because of the issuer.
4. `CHANGES_IN_EQUITY` PAT lookalikes are not income-statement PAT. A note index/share count is not TOP_LINE/EPS. Q4 must be printed exact-quarter, not FY−9M. Per-share never inherits Rs '000. `TOTAL_LIABILITIES` must be sourced as defined by the source-truth contract, not silently manufactured from the accounting equation.
5. Never lower the 8,924 floor, change metric definitions, reuse a burned holdout, copy an issuer-specific patch, or count unreviewed V1-only keys as correct recovery just to show lift.
6. Correctness **and** recovery must improve. Keep all previously correct facts under non-regression checks; any change that adds a critical wrong fact blocks promotion.
7. Every recovered/withheld/lost fact must have stable lineage and an explicit reason. Do not allow duplicate row counts to masquerade as gains/losses of unique target facts.

---

## 4. Agent coordination and scope — one delivery, not repeated handoffs

**Coordinator/integration agent:** owns the end-to-end definition, common cohort, comparability, worktree/stash hygiene, merged run, release checklist and final report. It accepts no module as “complete” on unit tests alone. Freeze baseline before branching; serialize changes to shared resolver/selection files; merge through tests; do not overwrite independent WIP.

**Extraction/recovery agent:** implements V1 structural-to-V2 contextual recovery at target-fact scale, preserving physical cell/header/statement/unit evidence and fixing the actual dominant full-universe loss boundaries. This is not an instruction to multiply raw observations or add generalized issuer guesses.

**Fact-admission/selection agent:** owns SourceFact resolution, dedup/conflict semantics, correct non-regressive union, source-versus-derived view, expected-entity selection and draft publication bridge. Prevents candidate ID collisions from dropping amounts or selecting note/share-count values.

**Source-truth/QA agent:** independently PDF-adjudicates sampled new/lost/disagreeing facts; owns fresh unseen holdout and critical-wrong analysis, rather than using V1 as truth.

**Release/reproducibility agent:** owns pinned-input manifests, OCR/quarantine, full test suite and real GitHub CI, fixed-input replay, export/workbook lineage, release-mode gating and rollback demonstration.

Work may be parallel, but **one coordinator must integrate and rerun on identical inputs**, and each agent must deliver code + test + measured effect + retained artifacts, not another roadmap. Agents must not treat a locally completed report or clean stdout as a pushed/green-CI result.

---

## 5. Execution Phase A — establish the real target-fact deficit

**Objective:** determine how many *correct source target facts* V1 actually supplies on the same 829 PDFs, how many V2 also has, and exactly where V2 loses the rest.

1. Re-run **V1**, **V2-only** and the current **V1-assisted V2** with the **same 829 SHA-pinned PDFs** and same filing/metric/period/required entity/selection policy. Check identical 829 membership and report errors/quarantine separately. Do not compare with a different 1,641-attempt E02 cohort as if identical.
2. Reconcile **SourceFact rows → deduplicated source fact keys → correct eligible target keys → selected TARGET → derived facts → E13 total draft-publishable**. Recreate the 3,854 definition on the same input or explicitly say why not comparable. Keep stock `duration=null`, flow duration exact, current/comparative, company/group and scale in the identity. Prove why V2 can have 9,838 eligible *rows* but ~2,816 selected TARGET facts; do not assume the difference is all an extraction defect.
3. Produce **one same-input fact-level differential**, not a raw candidate census: V1-only, V2-only, both same, both conflicting, source-not-reported, ambiguous, invalid V1, and source-reported both missed. Preserve source page/row/cell and every gate decision.
4. Independently adjudicate a stratified set of **V1-only target keys, new assisted selections, lost selections, and disagreement keys** against the PDFs. Include banks, finance/insurance/general, 2/4/6/8-column layouts, Group/Company/Bank, Q4/YTD, per-share/unit and OCR. Negative/not-reported cases must be included. Distinguish sample-verified totals from unknown-universe totals.
5. Produce a **fact-loss waterfall** for source-verified V1-only reported targets: missing page/statement → missing row/cell → concept → entity → period → duration/comparison → unit/scale → SourceFact admission → conflict/validation → production selection → draft publication. Every fact belongs to one **first causal loss** plus optional secondary reasons.

**Deliverable:** `reports/v1_v2_same_input/<new_run_id>/SOURCE_VALID_GAP_AND_SELECTION_WATERFALL.md` and machine-readable keyed ledger, SHA manifest, source-review ledger and reconciled KPI definitions.

**Decision gate:** If most validated correct V1-only facts are lost after source admission/selection, fix that bridge before adding new extraction. If their pages/rows/cells were never recovered, repair the physical reader/context adapter. Choose work by **recoverable correct fact volume**, not by raw 201k pending cells or 13-file regressions.

---

## 6. Execution Phase B — recover capability, not another +3

Implement one integrated **source-backed structural recovery** path, with V1's proven physical/header/statement/unit/continuation capabilities adapted into V2 contracts. The current `v2/challenger/` bridge and `run_pdf_pipeline(..., v1_source_observations=True)` are the starting point, **not** a completed solution.

Work from PDF to final output:

```text
Same PDF bytes / SHA
 ├─ V2 statement/table/row/cell reader
 └─ V1 physical reader + source header/unit/continuation geometry
               ↓
   source-anchored structured observations (not orphan numerics)
               ↓
   evidence-owned concept/entity/period/duration/comparison/unit
               ↓
   non-regressive candidate union + explicit conflict/admission
               ↓
   one V2 SourceFact ledger + full CandidateTrace
               ↓
   V2 validation → source/derived separation
               ↓
   selection → release policy → draft TARGET and E13 outputs
```

**Specific engineering obligations:**

- Carry V1 table/statement/header structure and scoped unit declarations **with the cell**; resolve only from documented PDF evidence. A numeric cell with `entity=None`/`period=None`/`unit=None` remains discovery-only and does not count as recovered.
- Prioritize **target-matched** observations and source-verified high-volume failures. The 42-filing pending partition found 2,118 target-matched cells, with UNIT 668 → ENTITY 486 → PERIOD 346 among its still-discovery gates. Those are a **sample diagnostic**, not a universe prevalence estimate. Non-target CONCEPT_UNRESOLVED mass does not justify thousands of context operations.
- Complete a **non-regressive merge**: preserve a previously source-supported V2 candidate when V1 is silent; only demote it when superior conflicting PDF evidence demonstrates wrong ownership. Distinguish genuinely false V2 facts demoted from correct facts lost. Reconcile hard-key and row changes, duration re-keys, value swaps and slot churn.
- Reject note indices, note totals, share counts and wrong-statement rows before target selection; retain corrected JAT/HAYLEYS/SIGIRIYA negatives and ACL/InsureMe/JKH-Hotels positives as permanent real-PDF regressions.
- Fix the selected-output bridge when a valid target SourceFact exists but is not chosen/published. Do not bypass V2 source-truth rules to elevate it.
- Use V1 component capabilities already mapped in `docs/v2/V1_V2_EXTRACTION_COMPONENT_MATRIX.md`: `compiler/header_tree.py`, `compiler/units.py`, `compiler/statement_compiler.py`, `document/table_reconstructor.py`, `document/continuation.py` as appropriate. **Port algorithms and source evidence, not V1 issuer-specific or silent-fill debt.**
- Instrument exact reason-coded transitions: discovered, target matched, source reanchored, contextualized, SourceFact, eligible/withheld, selected/rejected, published/unpublished. A “recovered” fact must reach the correct requested output.

**Engineering loop:** pick the biggest *source-verified* full-universe loss family → implement generalized change → test positives AND negatives → re-run identical cohort → measure correct new, correct lost, wrong new, wrong removed and net correct selected output → keep, revise or roll back. Do not stack patches after a flat result.

**Hard stop / change of approach:** If **two consecutive meaningful full-829 experiments** fail to recover a material share of verified V1-only facts, suspend local context/alias fixes and revisit the **physical reader integration or selection architecture** revealed by the waterfall. A +3 full-universe result is not sufficient. Do not fabricate a forecast of how many further edits will be needed.

---

## 7. Execution Phase C — hard parity and correctness gates

Run at the same clean committed SHA, identical pinned cohort, with a clean tree:

1. **Quantitative like-for-like parity:** report V1 vs V2 source-valid target keys and V1 vs V2 correct selected TARGET output; V2 must meet or exceed V1 **for the same definition and input PDFs**, or document the **independently source-verified invalid V1 facts** excluded and obtain governed disposition. No silent redefinition. Reconcile the historical **8,924 E13 draft-publishable floor** on its own matching scope and require the governed acceptance gate to pass.
2. **No critical wrong selected facts** on the institutional gold and reviewed changes; verify value, metric, entity, period, duration, comparison, currency/scale/unit and correct reported/not-reported semantics. Positive lift without correctness does not pass.
3. **No unexplained regression:** account for all lost previously correct hard keys and selected facts; any demotion must cite stronger source evidence or be restored.
4. **Output reconciliation:** separate source facts, derived facts, selected TARGET, E13 draft-publishable and market-data outputs. No double counts, mis-keyed observations, or implicit substitutions.
5. **Exceptions:** zero **unhandled** filing errors on the acceptance cohort; disposition of damaged/OCR/timed-out PDFs and quarantine must be recorded rather than silently excluded. If an exception is governed as quarantined, identify it and demonstrate the correct fail-closed path.

**Do not start the final unseen holdout while these gates fail.** Former N18 is a regression, not an unseen test.

---

## 8. Execution Phase D — certification, replay, CI and release readiness

Agents must complete these, not leave them for a later “final engineering” project:

- **Fresh unseen holdout:** select and freeze uninspected filings distinct from N17 and burned N18; blind adjudication independent of engine output; diverse issuer sectors, entity structures, durations, units, native/OCR. Apply the current approved source-truth/recall/accuracy gates, including **zero critical wrong facts**. If it fails, promote failures to DEV, repair generalized causes, and select a **new** unseen holdout after repairs.
- **Reproducibility:** clean committed SHA, clean worktree, pinned PDF+input/config/market/OCR hashes, deterministic A/B output and full run manifests. Resolve the previous `clean_d29b392` versus `working_tree_dirty: true` contradiction. Replay the exact historical Sept-10 frozen inputs when genuinely available; otherwise document unavailable artifacts and obtain approval for a governed equivalent — **never call a different snapshot an exact replay**.
- **CI:** real remote GitHub Actions on the integrated commit/PR; Ruff/type checks, full pytest, V2 tests, source-truth negatives, extraction regressions, all applicable hardening/governance/workbook checks. Record run URLs and failures fixed. Local “green” is not remote CI.
- **Lineage:** selected SourceFact and DerivedFact must connect to PDF SHA/page/bbox/row/cell, parser/evidence context, decision reason and (for derived facts) exact input-fact IDs; replay trace must explain every rejected or quarantined output.
- **OCR/robustness:** handle scanned/mixed PDFs; verify runtime packaging, quarantines and retry policy without making missing source evidence eligible by default.
- **Production readiness:** draft-to-OFFICIAL release-mode controls, output workbook/schema compatibility, operator runbook, controlled feature/default switch and tested V1 rollback with consistent data/manifest semantics. No automatic production flip by a coding agent before human authorization.
- **Governance documentation:** refresh status, cutoff/checklist, source-validated baseline, certification report and KPI reconcile based on **measured** results. Do not mark stages finished because they were described in a Markdown file.

---

## 9. One mandatory full-universe report — every major integration run

Publish one table with same-input, same-definition columns for **V1 / V2-only / V1-assisted V2**:

- exact PDF SHA cohort and errors/quarantines;
- V1-only source-verified correct target keys and remaining valid gap;
- source-observed, context-complete, eligible **rows**, eligible **hard keys**;
- selected TARGET source facts, separately selected derived facts;
- correct/incorrect gained and correct/incorrect lost selections;
- current E13 *total* draft-publishable under a matched definition, separately from TARGET;
- per-sector, metric, entity, period, OCR/native breakdown;
- first-loss waterfall and unresolved source review queue;
- zero-critical-wrong check and known exceptions;
- clean SHA, PDF/input hashes, reproducibility and CI state.

**Acceptance cannot be stated using only `+N`, a candidate count or a single `3,854`/`8,924` comparison.**

---

## 10. Final agent handoff / definition of done

The coordinator may write **`READY FOR OFFICIAL DECISION`** only when all of the following are evidenced and linked:

- [ ] identical 829-PDF comparison (and any required production cohort), reconciled KPI definitions and frozen manifests;
- [ ] material, source-verified V1-capability recovery and **like-for-like correct V1 parity** in selected target facts;
- [ ] historical 8,924 E13 governance gate correctly reconciled and passed (or separately governed replacement, never quiet lowering);
- [ ] zero critical wrong on reviewed delta and a new unseen holdout passing approved recall/accuracy gates;
- [ ] all lost previously correct selections explained; no unresolved wrong new selections;
- [ ] clean reproducible full runs, exception/OCR disposition and relevant replay evidence;
- [ ] real remote CI green on integrated code, full tests and lineage/export reconciliation;
- [ ] release/cutover documentation updated, V1 rollback proven, and code/reports committed and pushed;
- [ ] V1 still production pending OFFICIAL authorization.

**The human owner's final step:** read the compact decision pack, grant/withhold OFFICIAL approval, authorize the controlled V2-default cutover, observe the smoke checks and maintain V1 rollback. Agents may prepare and test the switch but must not represent approval as automatic.

If a gate fails, the agent must keep working on the actual blocker and issue a **BLOCKED WITH EVIDENCE** report. Do **not** hand back another isolated issue as “the only remaining final step”; do not invent a success result or guarantee that this entire undertaking requires one code change.

### Copy/paste top-level command to the agent team

> Execute this entire plan as one integrated recovery-to-release assignment. Preserve current local changes and production V1. First quantify the same-PDF, source-verified V1→V2 deficit and loss waterfall, then implement the generalized V1-capability/context/selection changes that recover **correct selected facts at full-universe scale**, measuring each against the 829 pinned PDFs. Do not stop after +3, more candidates, or a passing small regression. Continue through like-for-like parity, E13 governance, fresh unseen source-truth holdout, clean replay, OCR/quarantine, full remote CI, lineage, workbook and rollback tests. Commit/push code, tests and measured artifacts. Report READY FOR OFFICIAL DECISION **only** when every gate is supported. Otherwise report the precise failed gate and continue engineering; do not promote V2 or weaken source truth to force parity.
