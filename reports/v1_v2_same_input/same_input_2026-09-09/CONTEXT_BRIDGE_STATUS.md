# Context bridge — measured result

## Diagnosis (pre-bridge)
298,541 V1 cells were `DISCOVERY_ONLY` with null entity/period/unit. The feature flag reached the resolver; admission failed on missing source context — not a dead flag.

## Implementation
- `context_bridge.py` — V1 `compile_header` → entity/period/duration/comparison/unit on cells
- Conservative union — only demote V2 false `duration=3` when headers mark cumulative (`duration=None`); fill missing context; **no** blanket V1 overwrite

## Gate proofs
1. **One fact:** ACL PLASTICS `TOP_LINE` `731203000` GROUP 3M — PDF-verified; V2-only withheld (`CONFLICTING_SOURCE`); assisted **draft-selected**. See `first_verified_recovery_trace.json`.
2. **40-filing sample:** selected 125→133 (+10 gained / −2 lost).
3. **829 SHA-pinned cohort** (0 errors):

| KPI | V2-only | Assisted | Δ |
|---|---:|---:|---:|
| TARGET ELIGIBLE SourceFacts | 9,838 | 9,562 | −276 |
| Newly recovered ELIGIBLE keys | — | 370 | — |
| ELIGIBLE keys lost vs V2 | — | 200 | — |
| **Draft-selected TARGET (prod selection)** | **2,816** | **2,840** | **+24** |
| Context-bridged candidates | 0 | 22,159 | — |
| Still DISCOVERY_ONLY / pending verify | — | 201,546 | — |

## Honest reading
- **Primary delivery KPI is positive (+24 draft-selected TARGET facts)** on the identical 829 PDFs — first non-zero publishable lift from the bridge.
- Magnitude is small vs the ≥25% verified-gap target; most unlabeled single-entity filings (e.g. ABANS) still cannot invent COMPANY.
- Eligible-row net is negative while draft-selected rises — selection/conflict accounting differs from raw ELIGIBLE; do not quote ELIGIBLE delta as publishable lift.
- Two sample losses remain to adjudicate; former N18 not re-run in this pass.

## Next
Attribute remaining loss families (entity-unlabeled, concept, selection). Expand duration-demotion / statement typing carefully. Re-measure after each change on the same 829 pin.
