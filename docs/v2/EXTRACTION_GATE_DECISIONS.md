# Extraction Gate Decisions

Ablation outcomes for V2 fail-closed gates. No gate is KEEP/NARROW/REPLACE/REMOVE
until source-truth experiments run.

Source truth and publication policy stay separate. Do not disable a gate only to
raise counts.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.

| Gate | Current behaviour | Variants to test | Decision | Evidence |
|---|---|---|---|---|
| G01 Required entity semantics | Unresolved entity withholds. Expected issuer metadata is not source evidence. GROUP is never COMPANY. | A local explicit; B statement-level; C document-level; D singleton presentation; E issuer metadata only | UNTESTED | |
| G02 Partial-context cascade | Whole-monetary-table clearing when only some columns resolve | A current; B no cascade; C per-column; D HeaderGraph | UNTESTED | Diagnostic harness `g02_ablation` (`cascade` vs `per_column`). Production default remains cascade. |
| G03 Exact-quarter | FLOW publication requires `duration_months == 3`. 6M/9M/12M withheld. | Keep invariant; measure upstream duration errors vs gate | UNTESTED | |
| G04 OTHER-page exclusion | Notes/other pages skipped as statements | A blanket skip; B whole-PDF exact alias; C multi-label + context | UNTESTED | Diagnostic `discover_exact_aliases` finds exact aliases without publishing. |
| G05 Continuation | Explicit continued marker only | A current; B V1 evidenced; C V2 schema-evidence | UNTESTED | |
| G06 Source conflict | Conflicting current values withheld; no first/earliest win | Keep withholding; test header/entity/duration ownership | UNTESTED | |
| G07 Collapsed rows | Extra embedded numbers → `AMBIGUOUS_ROW_VALUES` | Reconstruct cells first, then gate | UNTESTED | |
| G08 Duplicate metric selection | Page-order / production selector | Evidence ranking | UNTESTED | |
| G09 EPS entity inference | Absence of Group is not Company | Source-truth audit before any such rule | UNTESTED | |

Header / unit / page-router bake-offs (H0–H2, U0–U2, P0–P2) are recorded with
those experiments. They are not decided here.
