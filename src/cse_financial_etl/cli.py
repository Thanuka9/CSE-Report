import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

# Keep CLI help deterministic in tests/CI. Typer forces Rich terminal styling under
# GITHUB_ACTIONS unless this is set before Typer imports its rich utilities.
os.environ.setdefault("_TYPER_FORCE_DISABLE_TERMINAL", "1")
os.environ.setdefault("NO_COLOR", "1")

import typer

from cse_financial_etl.contracts.release import (
    DEFAULT_DECISIONS_RELATIVE_PATH,
    append_decision,
    make_decision,
)
from cse_financial_etl.domain.enums import MetricType, UnitScope
from cse_financial_etl.extraction.unit_detector import detect_candidates, resolve_unit
from cse_financial_etl.orchestration.pipeline import Pipeline
from cse_financial_etl.sources.cse import fetch_market_capitalization
from cse_financial_etl.transformation.normalizer import normalize_value
from cse_financial_etl.validation.adjudication import (
    prepare_adjudication_packet,
    validate_adjudication_packet,
)
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
    no_compile: bool = typer.Option(
        False,
        "--no-compile",
        help=(
            "Disable the native statement compiler. Rows then route layout_assist_only "
            "with explicit_fallback=COMPILER_DISABLED; diagnostics only."
        ),
    ),
    tunnel_b_always: bool = typer.Option(
        False, help="Always run the independent Tunnel B reader (not only for risky/sampled filings)"
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
            compile_statements=not no_compile,
            run_tunnel_b_always=tunnel_b_always,
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


@app.command("prepare-adjudication")
def prepare_adjudication_command(
    project_root: Path = typer.Option(Path.cwd(), help="Repository root"),
    as_of: str = typer.Option(..., help="Universe-run as-of date (YYYY-MM-DD)"),
    target_issuers: int = typer.Option(100, min=1, help="Unique issuers to independently adjudicate"),
    output: Path | None = typer.Option(None, help="Optional output CSV path"),
) -> None:
    """Create a deterministic 100-issuer human adjudication packet from a universe run."""

    result = prepare_adjudication_packet(
        project_root.resolve(),
        date.fromisoformat(as_of),
        target_issuers=target_issuers,
        output_path=output,
    )
    typer.echo(json.dumps(result, indent=2))


@app.command("validate-adjudication")
def validate_adjudication_command(
    packet: Path = typer.Argument(..., exists=True, dir_okay=False),
    target_issuers: int = typer.Option(100, min=1),
) -> None:
    """Check whether an adjudication packet has enough explicit independent human truth."""

    typer.echo(json.dumps(validate_adjudication_packet(packet, target_issuers=target_issuers), indent=2))


@app.command("sign-review-decision")
def sign_review_decision_command(
    issuer_name: str = typer.Option(...),
    symbol: str = typer.Option(...),
    period_end: str = typer.Option(...),
    metric_code: str = typer.Option(...),
    filing_sha256: str = typer.Option(...),
    reviewer_id: str = typer.Option(...),
    decision: str = typer.Option(..., help="APPROVED or REJECTED"),
    key_id: str = typer.Option(..., help="Key id; secret must exist in CSE_REVIEW_KEY_<KEY_ID>"),
    note: str = typer.Option(""),
    project_root: Path = typer.Option(Path.cwd(), help="Repository root"),
) -> None:
    """Append a cryptographically signed, source-bound human review decision."""

    signed = make_decision(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=metric_code,
        filing_sha256=filing_sha256,
        reviewer_id=reviewer_id,
        decision=decision,
        note=note,
        key_id=key_id,
    )
    destination = project_root.resolve() / DEFAULT_DECISIONS_RELATIVE_PATH
    append_decision(destination, signed)
    typer.echo(json.dumps({"status": "SIGNED_AND_APPENDED", "path": str(destination), "decision": signed.as_dict()}, indent=2))


if __name__ == "__main__":
    app()
