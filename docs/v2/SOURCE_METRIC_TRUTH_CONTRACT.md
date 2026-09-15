# Source Metric Truth Contract

This contract locks **source meaning** for V2 extraction investigation. It is not
publication policy, not V1 output, and not the current 33-filing scoring overlay.

Separate:

- **SOURCE TRUTH** — what the filing establishes.
- **PUBLICATION POLICY** — which proven source facts a release may display.

A reviewer records source truth without seeing or applying the current V1/V2 gate
decision. Existing gold that says “no Company/Group/Bank label → drop all expected”
is publication policy and must not be copied into source truth.

Investigation base SHA: `91a9c68bf940d3d9c2a86245f127de88ad4b4b6d`.

Derived metrics and market prices are out of scope for source-extraction recall.

## Normalization (locked)

- Absolute monetary values normalize to **base source currency units** using the
  evidenced scale (`123` at `Rs '000` → `123000` LKR when currency is LKR).
- Per-share values stay per-share. They **must not** inherit statement `Rs/'000`
  monetary scale.
- `cents/share` is not `Rs/share`. Normalize cents to rupees per share with
  explicit scale `0.01`. Do not store cents as LKR with scale 1.
- Percentages stay percentages. Ratios stay unitless. Share counts stay counts.
- **No FX conversion** unless a separate governed FX policy exists. None exists.

## Hard source rules (not optional)

- Never invent entity, period, or unit.
- Never convert GROUP → COMPANY.
- `TOTAL_LIABILITIES` is explicit-source-only. Assets − equity is not source truth.
- Q4 flow must be **reported**. `FY − 9M` is not a source PAT/PBT/OP/TOP_LINE.
  That is source semantics for reported duration, not a reason to invent Q4.

## Publication policy (do not bake into gold)

These are gates to ablate later. They are **not** source presence:

- Exact-quarter (`duration_months == 3`) for FLOW publication.
- Current vs comparative publication.
- Unlabelled Company/Group/Bank columns withheld.
- OTHER-page exclusion.
- Production entity selector dropping GROUP when the query wants COMPANY.

A filing can **report** a 6-month PAT. Source presence is REPORTED. Publication
may still withhold it.

---

## PAT

| Field | Contract |
|---|---|
| Canonical metric | `PAT` |
| Source semantic | Profit or loss **for the period after tax**, total entity line |
| Allowed statements | Income statement. Not notes-only narrative. |
| Entity | Explicit Company / Bank / Group (or later G01-proven document evidence) |
| Period / duration | FLOW. Source records the reported duration. Publication requires 3 months. |
| Unit | Monetary, source currency |
| Accepted variants | Registry exact aliases: profit/(loss) for the period; after tax; continuing operations period profit |
| Explicit exclusions | EBITDA; PBT; OCI-only lines; profit **attributable to owners / equity holders** |
| Derivation | Forbidden |
| Sector/regime | Same semantic across GENERAL / BANK / FINANCE / INSURANCE |

**Locked:** `PAT` is the total-entity profit/(loss) for the period after tax.
"Profit attributable to owners of the parent" is not PAT. If both lines exist,
record PAT from the total period line only. If only an attributable line exists,
source presence for PAT is `NOT_REPORTED` (do not silently promote attributable).

---

## PBT

| Field | Contract |
|---|---|
| Canonical metric | `PBT` |
| Source semantic | Profit or loss **before tax** for the period |
| Allowed statements | Income statement |
| Entity / period / unit | Same as PAT |
| Accepted variants | Profit before tax / income tax / taxation; loss before tax |
| Explicit exclusions | PAT; operating profit; tax expense |
| Derivation | Forbidden |

---

## OPERATING_PROFIT

| Field | Contract |
|---|---|
| Canonical metric | `OPERATING_PROFIT` |
| Source semantic | Results from operating activities / profit from operations |
| Allowed statements | Income statement |
| Accepted variants | Operating profit; profit from operations; operating profit before tax on financial services |
| Explicit exclusions | **EBITDA**; operating profit **after** taxes on financial services |
| Derivation | Forbidden |

If the income statement has no operating-profit line, source presence is
`NOT_REPORTED`. Do not invent HDFC (or any issuer) operating profit.

---

## TOP_LINE

| Field | Contract |
|---|---|
| Canonical metric | `TOP_LINE` |
| Source semantic | Regime-specific gross income / revenue. Canonical code stays `TOP_LINE`. |
| Allowed statements | Income statement |
| Derivation | Forbidden |

Regime source concepts (registry):

- GENERAL: Revenue, Total revenue, Net sales, Turnover, Revenue from contracts with customers
- BANK canonical TOP_LINE: **Gross income**
- BANK distinct source lines, not substitutes for Gross income: Interest income; Total operating income
- FINANCE_COMPANY: Total income, Net operating income, Income (exact), Gross income, Interest income, Total operating income
- SLFRS17: Insurance revenue
- SLFRS4: Gross written premium, Net earned premium

Generic issuer class `INSURANCE` is **not** proof of SLFRS 4 or 17. Record
`source_concept` / `matched_alias`. Leave `accounting_regime` unresolved unless
that reporting regime is explicitly requested or evidenced.

**Locked:** BANK TOP_LINE is Gross income. Interest income and Total operating
income remain distinct source concepts. When Gross income is present, that line
is TOP_LINE. When only Interest income or Total operating income is present,
record the actual `matched_alias`; do not relabel it as Gross income. Reviewers
must not pick a workbook default among the three.

---

## EPS_BASIC

| Field | Contract |
|---|---|
| Canonical metric | `EPS_BASIC` |
| Source semantic | Basic earnings/(loss) per ordinary share for the reported flow period |
| Allowed statements | Income statement; EPS note / share-information page |
| Unit | Per-share. Do not apply `Rs '000` scale. |
| Accepted variants | Basic EPS; “Earnings per share” when no separate diluted line exists |
| Explicit exclusions | Diluted-only lines; NAVPS |
| Derivation | Forbidden as source. `EPS_SELECTED` is derived. |

Absence of the word Group is **not** Company evidence (G09).

---

## EPS_DILUTED

| Field | Contract |
|---|---|
| Canonical metric | `EPS_DILUTED` |
| Source semantic | Diluted earnings/(loss) per share, only when a diluted line exists |
| Allowed statements | Income statement; EPS note |
| Unit | Per-share, no monetary statement scale |
| Derivation | Forbidden as source |

If the heading has no diluted line, source presence is `NOT_REPORTED`. Do not
copy basic EPS into diluted.

---

## NAVPS

| Field | Contract |
|---|---|
| Canonical metric | `NAVPS` |
| Source semantic | Net assets / net asset value per share at period end |
| Allowed statements | Balance sheet; EPS/share-information note |
| Period behaviour | Point-in-time |
| Unit | Per-share |
| Derivation | Forbidden as source (do not compute from equity / shares unless that is later a governed derived metric, which it is not today) |

---

## TOTAL_EQUITY

| Field | Contract |
|---|---|
| Canonical metric | `TOTAL_EQUITY` |
| Source semantic | Total equity / shareholders’ funds of the stated entity |
| Allowed statements | Balance sheet |
| Period behaviour | STOCK |
| Derivation | Forbidden |
| Current aliases | Total equity; Shareholders funds; Total shareholders funds |
| Explicit exclusions | Equity attributable to owners / equity holders of the parent |

**Locked:** `TOTAL_EQUITY` is total equity of the stated entity, including NCI
when a total line exists. "Equity attributable to owners of the parent" is not
TOTAL_EQUITY. If both lines exist, use the inclusive total. If only attributable
equity is printed, source presence for TOTAL_EQUITY is `NOT_REPORTED`.

---

## TOTAL_ASSETS

| Field | Contract |
|---|---|
| Canonical metric | `TOTAL_ASSETS` |
| Source semantic | Total assets of the stated entity |
| Allowed statements | Balance sheet |
| Period behaviour | STOCK |
| Accepted variants | Total assets |
| Derivation | Forbidden |

---

## TOTAL_LIABILITIES

| Field | Contract |
|---|---|
| Canonical metric | `TOTAL_LIABILITIES` |
| Source semantic | Explicit total liabilities line |
| Allowed statements | Balance sheet |
| Period behaviour | STOCK |
| Accepted variants | Total liabilities; Total liability |
| Derivation | **Forbidden.** Assets − equity is not source TOTAL_LIABILITIES. |

---

## Out of source-extraction truth

| Code | Domain |
|---|---|
| `EPS_SELECTED` | Derived |
| `LIABILITIES_TO_EQUITY` | Derived |
| `ROE` / `ROA` / `NPM` | Derived (a missing ROE after a missing PAT is not a second extraction miss) |
| `LAST_TRADED_PRICE` | Market-price domain, not PDF extraction |

---

## Evidence levels for truth items

Use `CELL_EXPLICIT`, `COLUMN_HEADER_EXPLICIT`, `TABLE_EXPLICIT`,
`STATEMENT_EXPLICIT`, `DOCUMENT_EXPLICIT`, `STRUCTURALLY_INFERRED`, or
`AMBIGUOUS`.

Document-level or structural entity evidence may be recorded. It must not be
pre-judged as publishable. That is gate G01.
