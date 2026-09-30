# N04 — Generalized root-cause classification (LITE + SFCL)

## Families

| ID | Family | Status | Evidence |
|---|---|---|---|
| F1 | Header graph / column ownership — entity subtitles dropped | **FIX LANDED** | `_is_entity_bearing_subtitle` |
| F2 | Header evidence propagation | **PARTIAL** | entity_evidence prefers banner texts |
| F3 | Duration ownership — `period ended` date cue → false 9M | **FIX LANDED** | skip `\bperiod\s+ended\b` as duration banner |
| F4 | Holdout truth authoring (SFCL) | **CORRECTED** | COMPANY values mislabeled GROUP |

## Score (inspected T25 — not final holdout)

After F1+F3+SFCL truth: DEV recall 1.0; inspected HOLDOUT TP16/FN0/critical0/recall 1.0.

## Remaining before certification

- N17/N18 new unseen holdout blind gold + score
- G02/G04–G08 KEEP/NARROW decisions (still UNTESTED)
- H1/H2 not built
- Sept-10 frozen replay; current-universe floors; OFFICIAL
