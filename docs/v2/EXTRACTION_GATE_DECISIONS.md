# Extraction Gate Decisions

Ablation outcomes for V2 fail-closed gates. No gate is KEEP/NARROW/REPLACE/REMOVE
until source-truth experiments run.

Source truth and publication policy stay separate. Do not disable a gate only to
raise counts.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.

| Gate | Current behaviour | Variants to test | Decision | Evidence |
|---|---|---|---|---|
| G01 Required entity semantics | Unresolved entity withholds. Expected issuer metadata is not source evidence. GROUP is never COMPANY. | A local explicit; B statement-level; C document-level; D singleton presentation; E issuer metadata only | UNTESTED | Locked-33: 256 unresolved entity columns; 65 of those have an unused document-heading entity cue. Document heading is not copied. Issuer metadata is not source. |
| G02 Partial-context cascade | Whole-monetary-table clearing when only some columns resolve | A current; B no cascade; C per-column; D HeaderGraph | UNTESTED | Locked-33 diagnostic after source/selection split: cascade 1420 vs per_column 1420, `facts_suppressed_by_cascade=0`. Not source-confirmed; production default remains cascade. |
| G03 Exact-quarter | FLOW publication requires `duration_months == 3`. 6M/9M/12M withheld. | Keep invariant; measure upstream duration errors vs gate | UNTESTED | Locked-33 FLOW: 725 quarter / 416 non-quarter / 36 duration-missing. Do not invent duration. |
| G04 OTHER-page exclusion | Notes/other pages skipped as statements | A blanket skip; B whole-PDF exact alias; C multi-label + context | UNTESTED | Diagnostic `discover_exact_aliases` on locked 33: 32 exact hits, 23 statement-page / 9 other-page. Does not publish. |
| G05 Continuation | Explicit continued marker only | A current; B V1 evidenced; C V2 schema-evidence | UNTESTED | Locked-33: 0 explicit continuation regions. Production stays explicit-marker. Schema-evidence continuation is not enabled. |
| G06 Source conflict | Conflicting current values withheld; no first/earliest win | Keep withholding; test header/entity/duration ownership | UNTESTED | Conflict groups by matched alias after cell-level SourceRef. |
| G07 Collapsed rows | Extra embedded numbers → `AMBIGUOUS_ROW_VALUES` | Reconstruct cells first, then gate | UNTESTED | Gate compares line-level numbers to reconstructed cell count. Cell `SourceRef.raw_text` is the numeric token. |
| G08 Duplicate metric selection | Page-order / production selector | Evidence ranking | UNTESTED | Locked-33: 660 eligible SourceFacts, 64 duplicate identity groups. Production selection is measured separately. |
| G09 EPS entity inference | Absence of Group is not Company | Source-truth audit before any such rule | UNTESTED | Current production infers COMPANY on EPS_NOTE when the blob has no Group. Not source-confirmed KEEP. |

Header / unit / page-router bake-offs (H0–H2, U0–U2, P0–P2) are recorded with
those experiments. They are not decided here.

P1 is opt-in (`read_document(..., page_routing="page")`). Production stays P0
document-level routing. Locked-33 census: 7 mixed filings, 9 empty native pages.
Tesseract was not available; empty pages were not OCR'd and no tokens were invented.

H2 HeaderGraph, U2 UnitEvidenceResolver, and P2 hybrid merge are **not built**.
U0 now parses USD as USD with no FX conversion. `cents/share` scale is locked at `0.01`.
