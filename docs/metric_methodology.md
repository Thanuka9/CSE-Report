# Metric methodology

## Periods

Flow metrics use only explicitly reported standalone three-month/current-quarter values. Stock metrics use the standalone balance at period end. Q4 requires an explicitly reported standalone three-month/`4Q` value. Annual, 6M, 9M and YTD columns are never copied or differenced into a quarter. Cumulative-only values remain review evidence.

EPS output selects diluted EPS when the exact current quarter reports it, otherwise basic EPS. Both remain in audit storage. Total liabilities must be explicitly extracted from the standalone statement; `Total Assets - Total Equity` is used only as a reconciliation check.

## Ratios

- ROE: same-quarter PAT divided by that quarter's total equity.
- ROA: same-quarter PAT divided by that quarter's total assets.
- NPM: same-quarter PAT divided by that quarter's top line.
- Debt to equity: total liabilities divided by total equity, expressed as a multiple (`x`).

No ratio is emitted when required inputs are missing, incompatible or have an invalid denominator. There is no TTM logic.
