"""Controlled V2 production smoke after DRAFT cutover.

Runs hybrid extraction using the committed default (`extraction.engine: v2`)
on a small real-PDF cohort, stamps one signed approval onto native facts,
renders DRAFT and OFFICIAL workbooks, and verifies V1 remains the rollback
backend.

Does not set release_mode OFFICIAL. Does not invent MANUAL_QA gold. Does not
overwrite dated production outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path

import yaml

from cse_financial_etl.config import load_issuers
from cse_financial_etl.contracts.release import (
    apply_review_decisions,
    fact_fingerprint,
    make_decision,
    sign_decision,
)
from cse_financial_etl.v2.contracts.enums import ReleaseMode, ReviewStatus
from cse_financial_etl.v2.contracts.release import ReleaseContext
from cse_financial_etl.v2.production.adapter import extract_filing_v2_bundle
from cse_financial_etl.v2.production.publish import publish_production_workbook
from cse_financial_etl.v2.production.review_propagation import (
    propagate_review_status_to_native_facts,
)
from cse_financial_etl.v2.reporting.release_view import count_eligible_facts

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports" / "v2_production_smoke"
SECRET = "v2-production-smoke-secret"
KEY_ID = "SMOKE-REVIEW-1"
PREFERRED_SYMBOLS = (
    "JKH.N0000",
    "DIAL.N0000",
    "COMB.N0000",
    "JAT.N0000",
    "AAF.N0000",
    "ABAN.N0000",
)


def _release_context(mode: ReleaseMode, run_id: str) -> ReleaseContext:
    return ReleaseContext(
        generation_id=run_id,
        run_id=run_id,
        mode=mode,
        code_sha="v2-production-smoke",
        policy_hash="v2-production-smoke",
        source_snapshot_id="v2-production-smoke",
    )


def _committed_engine() -> str:
    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    return str(app["extraction"]["engine"])


def _committed_release_mode() -> str:
    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    return str(app["publication"]["release_mode"])


def _pdf_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locate_pdf(relative: str) -> Path | None:
    listed = ROOT / relative
    if listed.exists():
        return listed
    folder = listed.parent
    if not folder.exists():
        return None
    matches = sorted(path for path in folder.glob("*.pdf") if "2026-06-30" in path.name)
    return matches[0] if matches else None


def _resolve_cases(limit: int) -> list[tuple[str, str, date, Path]]:
    fixtures = json.loads(
        (ROOT / "tests" / "fixtures" / "golden_financial_facts.json").read_text(encoding="utf-8")
    )
    by_symbol = {str(row.get("symbol")): row for row in fixtures}
    resolved: list[tuple[str, str, date, Path]] = []
    for symbol in PREFERRED_SYMBOLS:
        row = by_symbol.get(symbol)
        if not row:
            continue
        pdf = _locate_pdf(str(row.get("pdf") or ""))
        if pdf is None:
            continue
        resolved.append(
            (
                str(row["issuer_name"]),
                symbol,
                date.fromisoformat(str(row["period_end"])),
                pdf,
            )
        )
        if len(resolved) >= limit:
            return resolved
    for row in fixtures:
        symbol = str(row.get("symbol") or "")
        if any(item[1] == symbol for item in resolved):
            continue
        pdf = _locate_pdf(str(row.get("pdf") or ""))
        if pdf is None:
            continue
        resolved.append(
            (
                str(row["issuer_name"]),
                symbol,
                date.fromisoformat(str(row["period_end"])),
                pdf,
            )
        )
        if len(resolved) >= limit:
            break
    if not resolved:
        raise SystemExit("no smoke PDFs found under data/raw/filings")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    if _committed_engine() != "v2":
        raise SystemExit("refusing to run: committed extraction.engine is not v2")
    if _committed_release_mode() != "DRAFT":
        raise SystemExit("refusing to run: committed release_mode is not DRAFT")

    os.environ["CSE_REVIEW_KEY_SMOKE_REVIEW_1"] = SECRET
    issuers = load_issuers(ROOT)
    cases = _resolve_cases(args.limit)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    source_facts = []
    derived_facts = []
    extracted_rows = []
    filing_shas: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for issuer, symbol, period, pdf in cases:
        print(f"extracting {symbol} {pdf.name}", flush=True)
        try:
            bundle = extract_filing_v2_bundle(
                pdf, issuer, symbol, period, issuers=issuers
            )
        except Exception as exc:
            errors.append(
                {
                    "issuer_name": issuer,
                    "symbol": symbol,
                    "error": str(exc),
                }
            )
            continue
        source_facts.extend(bundle.source_facts)
        derived_facts.extend(bundle.derived_facts)
        extracted_rows.extend(bundle.production_facts)
        filing_shas[symbol] = _pdf_sha(pdf)

    approved_metric = None
    if extracted_rows:
        candidate = next(
            (
                row
                for row in extracted_rows
                if row.metric_code == "PAT"
                and row.normalized_value is not None
                and (row.status or "") in {"EXTRACTED", "EXTRACTED_DERIVED"}
            ),
            extracted_rows[0],
        )
        filing_sha = filing_shas.get(candidate.symbol) or "missing"
        signed = sign_decision(
            make_decision(
                issuer_name=candidate.issuer_name,
                symbol=candidate.symbol,
                period_end=candidate.period_end.isoformat(),
                metric_code=candidate.metric_code,
                filing_sha256=filing_sha,
                fact_fingerprint=fact_fingerprint(candidate),
                reviewer_id="v2-production-smoke",
                decision="APPROVED",
            ),
            secret=SECRET,
            key_id=KEY_ID,
        )
        reviewed, summary = apply_review_decisions(
            extracted_rows,
            [signed],
            filing_sha256=filing_sha,
        )
        source_facts, derived_facts = propagate_review_status_to_native_facts(
            reviewed, source_facts, derived_facts
        )
        approved_metric = {
            "symbol": candidate.symbol,
            "metric_code": candidate.metric_code,
            "approved_applied": summary.approved_applied,
            "native_approved": sum(
                1
                for fact in (*source_facts, *derived_facts)
                if fact.review_status is ReviewStatus.APPROVED
            ),
        }
    else:
        reviewed = []
        summary = None

    draft_count = count_eligible_facts(source_facts, derived_facts, mode=ReleaseMode.DRAFT)
    official_count = count_eligible_facts(
        source_facts, derived_facts, mode=ReleaseMode.OFFICIAL
    )
    draft_path = publish_production_workbook(
        release=_release_context(ReleaseMode.DRAFT, "v2-smoke-draft"),
        source_facts=source_facts,
        derived_facts=derived_facts,
        destination=OUT_DIR / "draft.xlsx",
    )
    official_path = publish_production_workbook(
        release=_release_context(ReleaseMode.OFFICIAL, "v2-smoke-official"),
        source_facts=source_facts,
        derived_facts=derived_facts,
        destination=OUT_DIR / "official.xlsx",
    )

    from cse_financial_etl.extraction.statement_extractor import extract_filing as v1_backend

    payload = {
        "committed_engine_before": "v2",
        "committed_engine_after": _committed_engine(),
        "release_mode": _committed_release_mode(),
        "pdfs_attempted": len(cases),
        "pdfs_extracted": len(cases) - len(errors),
        "errors": errors,
        "source_fact_count": len(source_facts),
        "derived_fact_count": len(derived_facts),
        "extracted_row_count": len(extracted_rows),
        "v2_draft_eligible_count": draft_count,
        "v2_official_eligible_count": official_count,
        "signed_approval": approved_metric,
        "review_summary": None if summary is None else summary.as_dict(),
        "draft_workbook": str(draft_path.relative_to(ROOT)).replace("\\", "/"),
        "official_workbook": str(official_path.relative_to(ROOT)).replace("\\", "/"),
        "gold_status": "MANUAL_QA 4/100; packet not auto-promoted",
        "official_publication": "NOT_CERTIFIED",
        "engine_flip": "DRAFT_CUTOVER_APPROVED",
        "v1_rollback_importable": callable(v1_backend),
    }
    (OUT_DIR / "smoke_summary.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    if payload["committed_engine_after"] != "v2":
        return 2
    if payload["release_mode"] != "DRAFT":
        return 5
    if not payload["v1_rollback_importable"]:
        return 6
    if payload["pdfs_extracted"] == 0:
        return 1
    if approved_metric and approved_metric["approved_applied"] != 1:
        return 3
    if approved_metric and official_count < 1:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
