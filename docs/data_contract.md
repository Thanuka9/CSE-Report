# Data contract summary

- Financial grain: issuer, entity scope, period end, period type, metric, filing version.
- Market grain: security symbol and market-as-of date.
- Quarter-price grain: security symbol, financial period end and filing version.
- Monetary facts use decimal values with explicit currency and scale.
- Every accepted fact retains raw label, raw value, source page, source hash and unit evidence.
- Missing values use typed reason codes; a blank is not zero.
- Reporting selects only approved facts from the current approved filing version.
- Flow metrics use the standalone three-month quarter. Eligible Q4 flows may be derived from compatible cumulative and preceding standalone quarters with lineage; EPS is never derived this way.
- `EPS_SELECTED` uses diluted EPS when reported and otherwise basic EPS; both inputs are retained.
- Total liabilities may be explicitly extracted or derived as Assets minus Equity with lineage.
- Quarter-end price is specific to the exact voting/non-voting security symbol.
- ROE, ROA and NPM are same-quarter derived facts: PAT / equity, PAT / assets, and PAT / top line.
