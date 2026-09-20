"""Reconcile freeze vs E13 selection and measure V1 / V2 / V1-assisted on one SHA cohort.

Measurement deliverable for docs/v2/CSE_V1_TO_V2_ACTUAL_UNIVERSE_RECOVERY.md §2–4.
Does not promote V2 or change floors. Independent PDF adjudication of V1-only
rows is sampled/flagged — full blind gold is out of scope for this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PERIODS = ("2025-12-31", "2026-03-31", "2026-06-30")
RUN_ID = "same_input_2026-09-09"
TARGET_METRICS = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "NAVPS",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}


def _norm_path(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/").lower()


def _parse_pdf(path: Path) -> dict[str, str] | None:
    """Parse local PDF stem. Accepts sha16 freeze names and CSE download names."""
    m = re.match(
        r"^(?P<period>\d{4}-\d{2}-\d{2})_(?P<filing_id>\d+)_(?P<rest>.+)$",
        path.stem,
    )
    if not m:
        return None
    rest = m.group("rest")
    sha16_m = re.fullmatch(r"[0-9a-f]{16}", rest)
    return {
        "period_end": m.group("period"),
        "filing_id": m.group("filing_id"),
        "name_rest": rest,
        "naming": "sha16" if sha16_m else "cse_download",
        "sha16": sha16_m.group(0) if sha16_m else "",
        "issuer_dir": path.parent.name,
        "local_path": str(path.relative_to(ROOT)).replace("\\", "/"),
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_local_pdfs(*, naming: str | None = None, hash_full: bool = False) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for pdf in sorted((ROOT / "data/raw/filings").rglob("*.pdf")):
        meta = _parse_pdf(pdf)
        if meta is None or meta["period_end"] not in PERIODS:
            continue
        if naming is not None and meta["naming"] != naming:
            continue
        row = {**meta, "abs_path": str(pdf.resolve())}
        if hash_full:
            row["pdf_sha256"] = _sha256(pdf)
        else:
            row["pdf_sha256"] = None
        items.append(row)
    return items


def select_by_rule(
    items: list[dict[str, Any]], *, prefer: str
) -> dict[tuple[str, str], dict[str, Any]]:
    """One PDF per (issuer_dir, period). prefer=max|min filing_id."""

    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["issuer_dir"], item["period_end"])
        prev = chosen.get(key)
        if prev is None:
            chosen[key] = item
            continue
        a, b = int(item["filing_id"]), int(prev["filing_id"])
        if prefer == "max" and a > b:
            chosen[key] = item
        elif prefer == "min" and a < b:
            chosen[key] = item
    return chosen


def load_expected_slots() -> list[dict[str, Any]]:
    path = ROOT / "outputs/expected_disclosures_2026-09-09.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_issuer_master() -> dict[str, dict[str, Any]]:
    path = ROOT / "outputs/issuer_security_master_2026-09-09.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_name: dict[str, dict[str, Any]] = {}
    for issuer in data.get("issuers") or ():
        name = str(issuer.get("legal_name") or "").strip().upper()
        by_name[name] = issuer
    return by_name


def slug_to_guess_name(slug: str) -> str:
    return slug.replace("_", " ").upper()


def reconcile(out_dir: Path) -> dict[str, Any]:
    freeze_items = discover_local_pdfs(naming="sha16", hash_full=False)
    e13_items = discover_local_pdfs(naming="cse_download", hash_full=False)
    by_freeze = select_by_rule(freeze_items, prefer="min")
    by_e13 = select_by_rule(e13_items, prefer="max")

    expected = load_expected_slots()
    master = load_issuer_master()
    dirs = {p.name for p in (ROOT / "data/raw/filings").iterdir() if p.is_dir()}

    def match_dir(legal_name: str) -> str | None:
        from cse_financial_etl.sources.cse import safe_slug

        slug = safe_slug(legal_name)
        if slug in dirs:
            return slug
        target = re.sub(r"[^A-Z0-9]", "", legal_name.upper())
        for d in dirs:
            if re.sub(r"[^A-Z0-9]", "", d.upper()) == target:
                return d
        compact = slug.replace("_CO_", "_").replace("__", "_")
        if compact in dirs:
            return compact
        return None

    # Enrich E13 download cohort with issuer master fields; hash selected PDFs only.
    e13_like: list[dict[str, Any]] = []
    for item in sorted(by_e13.values(), key=lambda r: (r["issuer_dir"], r["period_end"])):
        # Best-effort legal_name from expected via issuer_dir match
        legal = None
        issuer_id = None
        for slot in expected:
            if slot.get("period_end") != item["period_end"]:
                continue
            d = match_dir(str(slot.get("legal_name") or ""))
            if d == item["issuer_dir"]:
                legal = str(slot.get("legal_name") or "")
                issuer_id = slot.get("issuer_id")
                break
        issuer = master.get((legal or "").upper()) or {}
        symbols = list(issuer.get("symbols") or ())
        pdf_path = Path(item["abs_path"])
        e13_like.append(
            {
                **item,
                "pdf_sha256": _sha256(pdf_path),
                "bytes": pdf_path.stat().st_size,
                "legal_name": legal,
                "issuer_id_master": issuer.get("issuer_id") or issuer_id,
                "symbol": symbols[0] if symbols else None,
                "issuer_type": issuer.get("issuer_type"),
            }
        )

    freeze_path = out_dir / "input_manifest.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8")) if freeze_path.is_file() else {}
    freeze_shas = {f["pdf_sha256"] for f in freeze.get("filings") or ()}
    e13_shas = {f["pdf_sha256"] for f in e13_like}

    freeze_keys = set(by_freeze)
    e13_keys = set(by_e13)
    only_e13_keys = sorted(e13_keys - freeze_keys)
    only_freeze_keys = sorted(freeze_keys - e13_keys)

    # When both naming styles exist for same (issuer, period), compare bytes if freeze has SHA.
    same_key_byte_mismatch = 0
    freeze_sha_by_key: dict[tuple[str, str], str] = {}
    for f in freeze.get("filings") or ():
        freeze_sha_by_key[(f["issuer_dir"], f["period_end"])] = f["pdf_sha256"]
    for row in e13_like:
        key = (row["issuer_dir"], row["period_end"])
        fsha = freeze_sha_by_key.get(key)
        if fsha and fsha != row["pdf_sha256"]:
            same_key_byte_mismatch += 1

    report = {
        "id": "same-input-reconcile",
        "run_id": RUN_ID,
        "historic_e13_selected_filing_count": 829,
        "expected_disclosure_slots": len(expected),
        "sha16_named_local_pdfs_in_periods": len(freeze_items),
        "cse_download_named_local_pdfs_in_periods": len(e13_items),
        "freeze_min_filing_id_sha16_count": len(by_freeze),
        "e13_cse_download_selection_count": len(e13_like),
        "selection_count_matches_e13_829": len(e13_like) == 829,
        "issuer_period_keys_only_in_e13_downloads": len(only_e13_keys),
        "issuer_period_keys_only_in_sha16_freeze": len(only_freeze_keys),
        "freeze_vs_e13_sha_overlap": len(freeze_shas & e13_shas),
        "only_in_freeze_sha": len(freeze_shas - e13_shas),
        "only_in_e13_sha": len(e13_shas - freeze_shas),
        "same_issuer_period_sha_mismatch_freeze_vs_e13": same_key_byte_mismatch,
        "bronze_metadata_files": len(list((ROOT / "data/bronze/document_metadata").glob("*.json"))),
        "gap_to_829": 829 - len(e13_like),
        "only_e13_key_samples": [
            {"issuer_dir": k[0], "period_end": k[1], "filing_id": by_e13[k]["filing_id"]}
            for k in only_e13_keys[:25]
        ],
        "note": (
            "Historic E13 selected_filing_count=829 matches local CSE download-named PDFs "
            "(period_filingId_timestamp…). The prior same-input freeze counted only "
            "sha16-named copies (period_filingId_<16hex>), which yielded 812. "
            "Pinned cohort for three-way measure = the 829 CSE download-named files, "
            "SHA256-hashed. Overlap of freeze SHAs with E13 download SHAs may be low "
            "even when issuer-period keys overlap, if the two naming trees hold different "
            "bytes for the same slot."
        ),
    }
    (out_dir / "reconcile_812_vs_829.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    cohort = {
        "id": "same-input-pinned-cohort",
        "run_id": RUN_ID,
        "rule": "cse_download_named_local_pdfs_in_target_periods_one_per_issuer_period",
        "filings_selected": len(e13_like),
        "historic_e13_selected_filing_count": 829,
        "selection_count_matches_e13_829": len(e13_like) == 829,
        "filings": e13_like,
    }
    (out_dir / "pinned_cohort.json").write_text(
        json.dumps(cohort, indent=2) + "\n", encoding="utf-8"
    )
    return cohort


def _fact_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("symbol") or row.get("issuer_id") or ""),
        str(row.get("metric_code") or ""),
        str(row.get("entity_scope") or ""),
        str(row.get("period_end") or ""),
        str(row.get("duration_months") if row.get("duration_months") is not None else ""),
        str(row.get("comparison_role") or ""),
        _num(row.get("normalized_value")),
    )


def _num(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return str(Decimal(str(value)))
    except Exception:
        return str(value)


def run_v1_on_pdf(item: dict[str, Any]) -> list[dict[str, Any]]:
    from cse_financial_etl.extraction.statement_extractor import extract_filing

    pdf = Path(item["abs_path"])
    period = date.fromisoformat(item["period_end"])
    facts = extract_filing(
        pdf,
        item.get("legal_name") or item["issuer_dir"],
        item.get("symbol") or item["issuer_dir"],
        period,
    )
    out: list[dict[str, Any]] = []
    for fact in facts or ():
        metric = getattr(fact, "metric_code", None) or getattr(fact, "metric", None)
        if metric is None:
            continue
        code = metric if isinstance(metric, str) else getattr(metric, "value", str(metric))
        if code not in TARGET_METRICS:
            continue
        out.append(
            {
                "engine": "v1",
                "symbol": item.get("symbol"),
                "issuer_dir": item["issuer_dir"],
                "pdf_sha256": item["pdf_sha256"],
                "metric_code": code,
                "entity_scope": getattr(fact, "entity_scope", None),
                "period_end": item["period_end"],
                "duration_months": getattr(fact, "duration_months", None),
                "comparison_role": getattr(fact, "comparison_role", None),
                "normalized_value": getattr(fact, "normalized_value", None)
                or getattr(fact, "value", None),
                "publication_status": "V1_EXTRACTED",
                "raw_text": getattr(fact, "raw_text", None),
            }
        )
    return out


def run_v2_on_pdf(item: dict[str, Any], *, assisted: bool) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from datetime import date as date_cls

    from cse_financial_etl.v2.contracts.enums import EntityScope
    from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
    from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts

    pdf = Path(item["abs_path"])
    result = run_pdf_pipeline(
        pdf,
        issuer_id=str(item.get("symbol") or item["issuer_dir"]),
        filing_version_id=f"{item.get('symbol') or item['issuer_dir']}-{item['period_end']}",
        issuer_name=str(item.get("legal_name") or ""),
        issuer_type=str(item.get("issuer_type") or ""),
        v1_source_observations=assisted,
    )
    reason_counts: Counter[str] = Counter()
    concept_resolved = 0
    for cand in result.candidates:
        for code in cand.reason_codes or ():
            reason_counts[code] += 1
        if cand.concept is not None and cand.concept.metric_code in TARGET_METRICS:
            if cand.concept_status.value == "RESOLVED":
                concept_resolved += 1
    period = date_cls.fromisoformat(item["period_end"])
    selected = ()
    selected_derived = ()
    selected_entity = None
    for ent in (EntityScope.COMPANY, EntityScope.GROUP, EntityScope.BANK):
        sel = select_pipeline_facts(result.source_facts, period_end=period, expected_entity=ent)
        if sel:
            selected = sel
            selected_entity = ent.value
            selected_derived = select_pipeline_facts(
                result.derived_facts, period_end=period, expected_entity=ent
            )
            break
    stats = {
        "candidates": len(result.candidates),
        "source_facts": len(result.source_facts),
        "eligible": sum(1 for f in result.source_facts if f.publication_status.value == "ELIGIBLE"),
        "withheld": sum(1 for f in result.source_facts if f.publication_status.value != "ELIGIBLE"),
        "draft_selected_target": sum(1 for f in selected if f.metric_code in TARGET_METRICS),
        "draft_selected_derived": len(selected_derived),
        "draft_selected_source_plus_derived": sum(
            1 for f in selected if f.metric_code in TARGET_METRICS
        )
        + len(selected_derived),
        "target_concept_resolved_candidates": concept_resolved,
        "v1_discovery_candidates": sum(
            1 for c in result.candidates if "V1_OBSERVATION_UNION" in (c.reason_codes or ())
        ),
        "discovery_only_pending_verify": sum(
            1
            for c in result.candidates
            if "DISCOVERY_ONLY" in (c.reason_codes or ())
            or "CONTEXT_UNRESOLVED_PENDING_V2_VERIFY" in (c.reason_codes or ())
        ),
        "context_bridged_candidates": sum(
            1 for c in result.candidates if "CONTEXT_BRIDGED_SOURCE_OWNED" in (c.reason_codes or ())
        ),
        "blocker_ENTITY_NOT_RESOLVED": int(reason_counts.get("ENTITY_NOT_RESOLVED", 0)),
        "blocker_CONCEPT_UNRESOLVED": int(reason_counts.get("CONCEPT_UNRESOLVED", 0)),
        "blocker_PERIOD_NOT_RESOLVED": int(reason_counts.get("PERIOD_NOT_RESOLVED", 0)),
    }
    out: list[dict[str, Any]] = []
    for fact in result.source_facts:
        if fact.metric_code not in TARGET_METRICS:
            continue
        out.append(
            {
                "engine": "v2_assisted" if assisted else "v2",
                "symbol": item.get("symbol"),
                "issuer_dir": item["issuer_dir"],
                "pdf_sha256": item["pdf_sha256"],
                "metric_code": fact.metric_code,
                "entity_scope": None if fact.entity_scope is None else fact.entity_scope.value,
                "period_end": None if fact.period_end is None else fact.period_end.isoformat(),
                "duration_months": fact.duration_months,
                "comparison_role": None
                if fact.comparison_role is None
                else fact.comparison_role.value,
                "normalized_value": str(fact.normalized_value),
                "publication_status": fact.publication_status.value,
                "reason_codes": list(fact.reason_codes or ()),
                "draft_selected_entity": selected_entity,
                "draft_selected": fact.fact_id in {f.fact_id for f in selected},
            }
        )
    return out, stats


def measure_cohort(cohort: dict[str, Any], *, limit: int, workers: int) -> dict[str, Any]:
    filings = list(cohort["filings"])
    if limit > 0:
        filings = filings[:limit]
    v1_rows: list[dict[str, Any]] = []
    v2_rows: list[dict[str, Any]] = []
    assisted_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    v2_stats = Counter()
    assisted_stats = Counter()

    def one(item: dict[str, Any]) -> dict[str, Any]:
        local: dict[str, Any] = {
            "item": item,
            "v1": [],
            "v2": [],
            "assisted": [],
            "error": None,
            "engine_errors": {},
        }
        try:
            local["v1"] = run_v1_on_pdf(item)
        except Exception as exc:  # noqa: BLE001
            local["engine_errors"]["v1"] = f"{type(exc).__name__}: {exc}"
        try:
            local["v2"], s2 = run_v2_on_pdf(item, assisted=False)
            local["v2_stats"] = s2
        except Exception as exc:  # noqa: BLE001
            local["engine_errors"]["v2"] = f"{type(exc).__name__}: {exc}"
        try:
            local["assisted"], sa = run_v2_on_pdf(item, assisted=True)
            local["assisted_stats"] = sa
        except Exception as exc:  # noqa: BLE001
            local["engine_errors"]["assisted"] = f"{type(exc).__name__}: {exc}"
        if local["engine_errors"]:
            local["error"] = "; ".join(f"{k}={v}" for k, v in local["engine_errors"].items())
            local["trace"] = traceback.format_exc(limit=5)
        return local

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, item) for item in filings]
        for i, fut in enumerate(as_completed(futures), start=1):
            result = fut.result()
            if result["error"]:
                errors.append(
                    {
                        "abs_path": result["item"].get("abs_path"),
                        "pdf_sha256": result["item"].get("pdf_sha256"),
                        "error": result["error"],
                    }
                )
            v1_rows.extend(result["v1"])
            v2_rows.extend(result["v2"])
            assisted_rows.extend(result["assisted"])
            for k, v in (result.get("v2_stats") or {}).items():
                v2_stats[k] += v
            for k, v in (result.get("assisted_stats") or {}).items():
                assisted_stats[k] += v
            if i % 25 == 0 or i == len(futures):
                print(f"  measured {i}/{len(futures)} errors={len(errors)}")

    def eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            r
            for r in rows
            if r.get("publication_status") in {"ELIGIBLE", "V1_EXTRACTED"}
        ]

    v1_e = eligible(v1_rows)
    v2_e = eligible(v2_rows)
    as_e = eligible(assisted_rows)
    v1_keys = {_fact_key(r) for r in v1_e}
    v2_keys = {_fact_key(r) for r in v2_e}
    as_keys = {_fact_key(r) for r in as_e}

    v1_only = v1_keys - v2_keys
    newly_in_assisted = as_keys - v2_keys
    lost_vs_v2 = v2_keys - as_keys
    both_v1_v2 = v1_keys & v2_keys

    # Withheld: V2 source facts that are not ELIGIBLE (from assisted run stats)
    summary = {
        "id": "same-input-three-way-measure",
        "run_id": RUN_ID,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "filings_attempted": len(filings),
        "filings_error": len(errors),
        "target_metrics": sorted(TARGET_METRICS),
        "kpi": {
            "v1_target_fact_rows": len(v1_e),
            "v2_eligible_source_facts": len(v2_e),
            "v1_assisted_eligible_source_facts": len(as_e),
            "identical_v1_v2_keys": len(both_v1_v2),
            "v1_only_keys_vs_v2": len(v1_only),
            "newly_recovered_keys_by_adapter_vs_v2": len(newly_in_assisted),
            "keys_lost_in_assisted_vs_v2": len(lost_vs_v2),
            "net_eligible_delta_assisted_minus_v2": len(as_e) - len(v2_e),
            "v2_draft_selected_target_sum": int(v2_stats.get("draft_selected_target", 0)),
            "assisted_draft_selected_target_sum": int(
                assisted_stats.get("draft_selected_target", 0)
            ),
            "net_draft_selected_delta_assisted_minus_v2": int(
                assisted_stats.get("draft_selected_target", 0)
            )
            - int(v2_stats.get("draft_selected_target", 0)),
            "v2_draft_selected_derived_sum": int(v2_stats.get("draft_selected_derived", 0)),
            "assisted_draft_selected_derived_sum": int(
                assisted_stats.get("draft_selected_derived", 0)
            ),
            "v2_draft_selected_source_plus_derived_sum": int(
                v2_stats.get("draft_selected_source_plus_derived", 0)
            ),
            "assisted_draft_selected_source_plus_derived_sum": int(
                assisted_stats.get("draft_selected_source_plus_derived", 0)
            ),
            "e13_draft_publishable_reference": 3854,
            "kpi_definition_note": (
                "draft_selected_target = production-selected SOURCE target metrics only. "
                "source_plus_derived approximates E13 draft_publishable but is not identical "
                "(entity preference COMPANY→GROUP→BANK; E13 used production release rules)."
            ),
            "assisted_context_bridged_candidates_sum": int(
                assisted_stats.get("context_bridged_candidates", 0)
            ),
            "v2_withheld_source_facts_sum": int(v2_stats.get("withheld", 0)),
            "assisted_withheld_source_facts_sum": int(assisted_stats.get("withheld", 0)),
            "assisted_v1_discovery_candidates_sum": int(
                assisted_stats.get("v1_discovery_candidates", 0)
            ),
            "assisted_discovery_only_pending_verify_sum": int(
                assisted_stats.get("discovery_only_pending_verify", 0)
            ),
            "v2_target_concept_resolved_candidates_sum": int(
                v2_stats.get("target_concept_resolved_candidates", 0)
            ),
            "v2_blocker_ENTITY_NOT_RESOLVED_sum": int(
                v2_stats.get("blocker_ENTITY_NOT_RESOLVED", 0)
            ),
            "v2_blocker_CONCEPT_UNRESOLVED_sum": int(v2_stats.get("blocker_CONCEPT_UNRESOLVED", 0)),
            "v2_blocker_PERIOD_NOT_RESOLVED_sum": int(
                v2_stats.get("blocker_PERIOD_NOT_RESOLVED", 0)
            ),
        },
        "pipeline_counters": {
            "v2": dict(v2_stats),
            "v1_assisted": dict(assisted_stats),
        },
        "caveats": [
            "V1_ONLY keys are engine-differential observations, not yet independently PDF-adjudicated source-valid labels.",
            "Adapter currently unions DISCOVERY_ONLY candidates; eligible lift requires V2 context verification of those cells.",
            "Draft-publishable here counts TARGET metric SourceFacts with publication_status=ELIGIBLE (source-only, not derived).",
        ],
        "errors_sample": errors[:20],
    }
    return {
        "summary": summary,
        "v1_rows": v1_rows,
        "v2_rows": v2_rows,
        "assisted_rows": assisted_rows,
    }


def write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="0 = full pinned cohort")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reconcile-only", action="store_true")
    parser.add_argument(
        "--reuse-cohort",
        action="store_true",
        help="Reuse pinned_cohort.json when it already selects 829 filings",
    )
    args = parser.parse_args()

    out_dir = ROOT / "reports" / "v1_v2_same_input" / RUN_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    cohort_path = out_dir / "pinned_cohort.json"
    if args.reuse_cohort and cohort_path.is_file():
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        print(
            f"reusing pinned cohort={cohort.get('filings_selected')} "
            f"matches829={cohort.get('selection_count_matches_e13_829')}"
        )
    else:
        print("reconciling…")
        cohort = reconcile(out_dir)
        print(
            f"pinned cohort={cohort['filings_selected']} "
            f"matches829={cohort['selection_count_matches_e13_829']}"
        )
    if args.reconcile_only:
        return 0

    print(f"measuring three-way limit={args.limit or 'ALL'} workers={args.workers}")
    measured = measure_cohort(cohort, limit=args.limit, workers=args.workers)
    summary = measured["summary"]
    (out_dir / "three_way_measure_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    write_ledger(out_dir / "ledger_v1.csv", measured["v1_rows"])
    write_ledger(out_dir / "ledger_v2.csv", measured["v2_rows"])
    write_ledger(out_dir / "ledger_v1_assisted_v2.csv", measured["assisted_rows"])
    (out_dir / "gap_summary.json").write_text(
        json.dumps(
            {
                "id": "v1-v2-gap-summary",
                "run_id": RUN_ID,
                "status": "MEASURED_THREE_WAY",
                "pinned_cohort_count": cohort.get("filings_selected"),
                "selection_count_matches_e13_829": cohort.get("selection_count_matches_e13_829"),
                "counts": summary["kpi"],
                "pipeline_counters": summary.get("pipeline_counters"),
                "caveats": summary["caveats"],
                "filings_attempted": summary["filings_attempted"],
                "filings_error": summary["filings_error"],
                "python_note": "Requires CPython >=3.12 (project requires-python).",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["kpi"], indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
