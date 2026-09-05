import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import typer

from cse_financial_etl.domain.enums import MetricType, UnitScope
from cse_financial_etl.extraction.unit_detector import detect_candidates, resolve_unit
from cse_financial_etl.orchestration.pipeline import Pipeline
from cse_financial_etl.sources.cse import fetch_market_capitalization
from cse_financial_etl.transformation.normalizer import normalize_value
from cse_financial_etl.validation.golden import validate_golden

app = typer.Typer(no_args_is_help=True, help="CSE financial-data ETL operator CLI")


def _rolling_periods(as_of: date) -> tuple[date, ...]:
    quarter_ends = [
        date(year, month, 31 if month in {3, 12} else 30)
        for year in range(as_of.year - 2, as_of.year + 1)
        for month in (3, 6, 9, 12)
    ]
    completed = [period for period in quarter_ends if period <= as_of]
    return tuple(completed[-3:])


def _parse_periods(value: str) -> tuple[date, ...]:
    try:
        periods = tuple(
            date.fromisoformat(item.strip()) for item in value.split(",") if item.strip()
        )
    except ValueError as exc:
        raise typer.BadParameter("Periods must be comma-separated ISO dates (YYYY-MM-DD).") from exc
    if not periods:
        raise typer.BadParameter("At least one reporting period is required.")
    return periods


@app.command("discover-securities")
def discover_securities() -> None:
    """Print the current official CSE security and issuer counts."""

    securities = fetch_market_capitalization()
    typer.echo(
        json.dumps(
            {
                "security_count": len(securities),
                "issuer_count": len({security.company_name for security in securities}),
            },
            indent=2,
        )
    )


@app.command("run")
def run_pipeline(
    as_of: str = typer.Option(date.today().isoformat(), help="Market snapshot date (YYYY-MM-DD)"),
    periods: str | None = typer.Option(
        None,
        help="Optional comma-separated period ends; defaults to the latest three completed quarters",
    ),
    project_root: Path = typer.Option(Path.cwd(), help="Repository root"),
    issuer_limit: int | None = typer.Option(None, min=1, help="Testing only: process N issuers"),
    skip_excel: bool = typer.Option(False, help="Do not generate the XLSX output"),
    offline: bool = typer.Option(
        False, help="Use the cached market snapshot and already downloaded filings"
    ),
) -> None:
    """Run discovery, download, extraction, validation, storage, and reporting."""

    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError as exc:
        raise typer.BadParameter("As-of date must use YYYY-MM-DD.") from exc
    period_dates = _parse_periods(periods) if periods else _rolling_periods(as_of_date)
    pipeline = Pipeline(project_root.resolve(), progress=typer.echo)
    try:
        result = pipeline.run(
            as_of_date,
            period_dates,
            issuer_limit=issuer_limit,
            offline=offline,
            skip_excel=skip_excel,
        )
    finally:
        pipeline.close()
    typer.echo(json.dumps(result, indent=2))


@app.command("detect-unit")
def detect_unit(
    text: str,
    value: str | None = typer.Option(None, help="Optional raw value to normalize"),
    metric_type: MetricType = typer.Option(MetricType.MONETARY_ABSOLUTE),
    scope: UnitScope = typer.Option(UnitScope.STATEMENT),
) -> None:
    """Inspect unit text and optionally normalize a value."""

    candidates = detect_candidates(text, scope=scope)
    unit = resolve_unit(candidates)
    typer.echo(
        f"currency={unit.currency} scale_factor={unit.scale_factor} source={unit.source_text!r}"
    )
    if value is not None:
        try:
            decimal_value = Decimal(value)
        except Exception as exc:
            raise typer.BadParameter("Value must be a valid decimal number.") from exc
        result = normalize_value(decimal_value, metric_type, candidates)
        typer.echo(f"normalized_value={result.normalized_value} status={result.status}")


@app.command("validate-golden")
def validate_golden_command(
    project_root: Path = typer.Option(Path.cwd(), help="Repository root"),
    as_of: str = typer.Option(date.today().isoformat(), help="Output label date"),
) -> None:
    """Validate extracted values against manually checked filing fixtures."""

    result = validate_golden(project_root.resolve(), date.fromisoformat(as_of))
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
