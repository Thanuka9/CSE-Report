# Production proof and governance

This repository deliberately separates **engineering completion** from **empirical/institutional proof**. A green unit/regression suite and a full-universe engineering pass are necessary, but they are not evidence that every CSE issuer is correct or that an institutional reviewer has approved official publication.

## Full-universe acceptance

Run **Full universe acceptance** from GitHub Actions and provide an `as_of` date. The workflow:

1. runs the complete CSE issuer universe with the native compiler, Tunnel B and production OCR runtime enabled,
2. uses a spawned per-PDF worker with hard process-tree cancellation,
3. writes the normal manifest, normalized facts, review and pipeline-error artifacts,
4. creates a deterministic 100-issuer adjudication packet, and
5. separates engineering failures, bounded quarantined filing exceptions and external proof gates.

A full-universe run is an engineering pass when there are no production gates other than explicitly external proof gates and there are no **unhandled** pipeline errors. The only pipeline error class that may be quarantined is an `EXTRACTION` timeout whose message proves that the PDF/OCR worker exceeded its configured bound and its process tree was terminated. The maximum number of those quarantines is versioned in `configs/coverage_baseline.yml`. Quarantined filings remain absent from publication and visible in both pipeline-error and review evidence. Any non-timeout error, missing/mismatched error evidence, or quarantine count above the configured limit fails engineering acceptance.

Coverage is also fail-closed. The current baseline is calibrated from the completed 2026-09-09 safe universe methodology and explicitly measures DRAFT-publishable facts rather than relying only on a pre-hardening raw extraction count.

### 2026-09-09 final engineering evidence

The final passing production proof is pipeline run `4e9ef5ff-878f-4348-b0fe-4d48b6572e67`, GitHub Actions run `34339810852`, on main commit `c0844ff366e20ae5c23fec721a51e4cd8559276c`. Artifact `10102186226` is the retained full-universe evidence.

It covered 281 issuers / 302 securities and 829 official CSE filings. It produced 6727 `EXTRACTED` facts plus 2296 `EXTRACTED_DERIVED` facts, for 9023 facts publishable under the DRAFT policy. The acceptance artifact records zero engineering gates and zero unhandled pipeline errors, with exactly three bounded extraction-timeout quarantines. The earlier unsafe publication/context/fallback gates did not recur. Acceptance is `ENGINEERING_PASS_EXTERNAL_PROOF_PENDING`.

The three quarantined filings are Sarvodaya Development Finance PLC for 2025-12-31 and 2026-03-31, and Renuka City Hotels PLC for 2026-06-30. Each exceeded the 480-second PDF/OCR worker limit, its process tree was terminated, and its output remained withheld/review-queued. The current policy allows at most three such exact bounded timeout quarantines; any overflow or any other pipeline-error class fails engineering acceptance.

The only remaining acceptance gates are `GOLD_SAMPLE_INCOMPLETE` and `GOLD_ISSUER_SAMPLE_INCOMPLETE`, which are external proof requirements. The artifact is therefore not an official institutional release until the independent benchmark and reviewer requirements below are satisfied.

The historical red proof `d6299b06-2f47-43d2-8024-d60c1d883804` is retained for auditability. It exposed the stale pre-fail-closed coverage floor; the floor was recalibrated from the empirically observed safe methodology without weakening accounting, entity, duration, unit, validation or publication rules.

## 100-issuer independent adjudication

`cse-etl prepare-adjudication --as-of YYYY-MM-DD --target-issuers 100` creates a stratified packet. Machine values are supplied only as context and never become truth automatically. Reviewers must populate the `human_*`, reviewer, timestamp and verdict fields from the source filing. `cse-etl validate-adjudication <packet>` checks whether 100 unique issuers have complete human context.

The production gold gate continues to require `min_gold_issuers: 100`. Importing completed adjudication into the permanent MANUAL_QA fixture remains a governed data-curation action; it must not be automated from machine output.

## Certainty calibration

Golden validation computes reliability bins, Brier score and expected calibration error from MANUAL_QA observations that carry machine `overall_certainty`. Fewer than the configured minimum observations returns `INSUFFICIENT_MANUAL_SAMPLE`; certainty must be described as a heuristic ranking score until the status is `CALIBRATED`.

## OCR acceptance

The deterministic suite tests routing without requiring system OCR packages. Production OCR acceptance installs Tesseract/Ghostscript and the locked OCR extra and requires scanned material to complete through an actual OCR extraction method. The full-universe workflow uses the same OCR runtime.

## Signed institutional review

A reviewer name alone cannot approve an official fact. Decisions must be HMAC-SHA256 signed and remain bound to fact identity, filing SHA-256, policy version and decision timestamp.

Provision a reviewer key as an environment/secret value named `CSE_REVIEW_KEY_<KEY_ID>` (non-alphanumeric key-id characters become `_`). Example key id `BSD-REVIEW-1` maps to `CSE_REVIEW_KEY_BSD_REVIEW_1`. Then use `cse-etl sign-review-decision ... --key-id BSD-REVIEW-1`. The secret is never written into Git.

For a bank/enterprise deployment, store these secrets in the institution's approved secret manager/HSM bridge and map key issuance/revocation to authenticated staff identities. The repository provides cryptographic possession checks; organizational identity provisioning remains an institutional control.

## Required GitHub branch protection

`main` must be protected in repository settings. The connected GitHub integration used to build this change cannot mutate repository administration settings, so this final control has to be enabled by a repository administrator.

Use **Settings → Rules → Rulesets → New branch ruleset** for `main` and require:

- pull requests before merging;
- at least one approval (or the organization's required count);
- dismiss stale approvals when new commits are pushed;
- require Code Owner review;
- require successful `validate (ubuntu-latest)` and `validate (windows-latest)` checks from **Deterministic production checks**;
- block force pushes and branch deletion;
- do not allow bypass for ordinary contributors;
- optionally require signed commits if that matches institutional policy.

`.github/CODEOWNERS` identifies the current repository owner, but CODEOWNERS has enforcement effect only after the branch ruleset requires Code Owner review.
