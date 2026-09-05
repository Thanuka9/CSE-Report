# Metric methodology

## Periods

Flow metrics use explicitly reported standalone three-month values. Stock metrics use the balance at period end. Q4 prefers an explicit standalone three-month/`4Q` column; eligible non-EPS flows may be derived from compatible cumulative and preceding standalone quarters with lineage. Annual columns are never copied into Q4.

EPS output selects diluted EPS when the exact quarter reports it, otherwise basic EPS. Both remain in audit storage. Total liabilities use the explicit standalone balance or, when absent and both inputs are source-backed, a derived `Total Assets - Total Equity` fact with lineage.

## Ratios

- ROE: same-quarter PAT divided by that quarter's total equity.
- ROA: same-quarter PAT divided by that quarter's total assets.
- NPM: same-quarter PAT divided by that quarter's top line.

No ratio is emitted when required inputs are missing, incompatible or have an invalid denominator.

- Debt to equity: Total liabilities divided by total equity, expressed as a multiple (`x`).
