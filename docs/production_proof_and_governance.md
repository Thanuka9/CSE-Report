# Production proof and governance

This repository deliberately separates **engineering completion** from **empirical/institutional proof**. A green unit/regression suite is necessary but is not evidence that every CSE issuer is correct.

## Full-universe acceptance

Run **Full universe acceptance** from GitHub Actions and provide an `as_of` date. The workflow:

1. runs the complete CSE issuer universe with the native compiler and Tunnel B enabled,
2. writes the normal manifest/review/error artifacts,
3. creates a deterministic 100-issuer adjudication packet, and
4. separates engineering gates from proof gates such as an incomplete human benchmark.

A full-universe run is an engineering pass only when there are no pipeline errors and no production gates other than explicitly external proof gates. The generated artifact is still not an official release until the independent benchmark and reviewer requirements are satisfied.

## 100-issuer independent adjudication

`cse-etl prepare-adjudication --as-of YYYY-MM-DD --target-issuers 100` creates a stratified packet. Machine values are supplied only as context and never become truth automatically. Reviewers must populate the `human_*`, reviewer, timestamp and verdict fields from the source filing. `cse-etl validate-adjudication <packet>` checks whether 100 unique issuers have complete human context.

The production gold gate continues to require `min_gold_issuers: 100`. Importing completed adjudication into the permanent MANUAL_QA fixture remains a governed data-curation action; it must not be automated from machine output.

## Certainty calibration

Golden validation now computes reliability bins, Brier score and expected calibration error from MANUAL_QA observations that carry machine `overall_certainty`. Fewer than the configured minimum observations returns `INSUFFICIENT_MANUAL_SAMPLE`; certainty must be described as a heuristic ranking score until the status is `CALIBRATED`.

## OCR acceptance

The normal deterministic suite tests routing without requiring system OCR packages. The separate **OCR production acceptance** workflow installs Tesseract/Ghostscript and the locked OCR extra, then requires the scanned fixture to complete through an actual OCR extraction method. This prevents a weak native document from passing merely because it was marked `requires_ocr`.

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
