from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.reporting.excel import ACCEPTED_STATUSES, VISIBLE_METRICS

HONEST_MISS_STATUSES = frozenset(
    {
        "SOURCE_CONFIRMED_NOT_REPORTED",
        "HISTORICAL_PRICE_NOT_AVAILABLE",
        "EXACT_QUARTER_NOT_REPORTED",
        "CUMULATIVE_ONLY",
    }
)
PARSER_GAP_STATUSES = frozenset(
    {
        "NOT_FOUND_BY_PARSER",
        "VALUE_CONTEXT_UNRESOLVED",
        "UNIT_NOT_RESOLVED",
    }
)

DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    ("PAT / PBT / Operating Profit / Top Line", "FLOW",
     "Standalone Company/Bank exact three-month quarter. Cumulative/FY values are never published as the quarter.",
     "Detected currency and scale"),
    ("EPS Selected", "PER_SHARE", "Diluted EPS when reported; otherwise basic. Both variants stay in the fact table.",
     "Never inherit statement scale"),
    ("NAVPS", "PER_SHARE", "Standalone Company/Bank net assets per share at period end.", "LKR/share"),
    ("Total Equity / Total Assets", "STOCK", "Standalone Company/Bank balance at period end from the statement of financial position.",
     "Detected currency and scale"),
    ("Total Liabilities", "STOCK",
     "Printed Company/Bank total liabilities row only. Never Assets minus Equity, never Group copied onto Company, never silent current+non-current assembly on the publish path.",
     "Normalized LKR"),
    ("Quarter-end Price", "PER_SHARE",
     "Exact security class; filing first, then official CSE history, then last trade on or before quarter end. Never a later live snapshot.",
     "LKR/share"),
    ("Debt to Equity", "RATIO", "Total Liabilities / Total Equity for the same issuer and period.", "Multiple (x)"),
    ("ROE / ROA / NPM (Quarter)", "RATIO", "Same-quarter PAT over equity, assets, or top line. No TTM.", "Percentage"),
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _compact_facts(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for row in rows:
        compacted.append(
            {
                "issuer": row.get("issuer_name", ""),
                "symbol": row.get("symbol", ""),
                "period": row.get("period_end", ""),
                "metric": row.get("metric_code", ""),
                "status": row.get("status", ""),
                "value": row.get("normalized_value", ""),
                "entity": row.get("entity_scope", ""),
                "page": row.get("source_page", ""),
                "method": row.get("extraction_method", ""),
                "certainty": row.get("certainty_band", ""),
                "line": (row.get("source_line") or "")[:180],
            }
        )
    return compacted


def _compact_reviews(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "issuer": row.get("issuer_name", ""),
            "symbol": row.get("symbol", ""),
            "period": row.get("period_end", ""),
            "metric": row.get("metric_code", ""),
            "reason": row.get("reason", ""),
            "detail": (row.get("detail") or "")[:240],
        }
        for row in rows
    ]


def _compact_prices(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "issuer": row.get("issuer_name", ""),
            "symbol": row.get("symbol", ""),
            "period": row.get("period_end", ""),
            "value": row.get("value", ""),
            "method": row.get("source_method", ""),
            "status": row.get("status", ""),
            "page": row.get("source_page", ""),
        }
        for row in rows
    ]


def _bucket_counts(status_counts: dict[str, int], wanted: frozenset[str]) -> dict[str, int]:
    return {status: count for status, count in sorted(status_counts.items()) if status in wanted and count}


def _miss_buckets(
    fact_status_counts: dict[str, int],
    price_status_counts: dict[str, int],
) -> dict[str, Any]:
    combined: Counter[str] = Counter(fact_status_counts)
    combined.update(price_status_counts)
    honest = _bucket_counts(dict(combined), HONEST_MISS_STATUSES)
    parser = _bucket_counts(dict(combined), PARSER_GAP_STATUSES)
    return {
        "honest": honest,
        "honest_total": sum(honest.values()),
        "parser": parser,
        "parser_total": sum(parser.values()),
    }


def _coverage(facts: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    codes = ["ALL", *[code for code, _label in VISIBLE_METRICS]]
    for metric in codes:
        subset = facts if metric == "ALL" else [row for row in facts if row.get("metric_code") == metric]
        extracted = [row for row in subset if row.get("status") in ACCEPTED_STATUSES]
        bands = Counter(row.get("certainty_band") or "NONE" for row in subset)
        rows.append(
            {
                "metric": metric,
                "total": len(subset),
                "extracted": len(extracted),
                "coverage": round(len(extracted) / len(subset), 4) if subset else 0,
                "high": bands["HIGH"],
                "medium": bands["MEDIUM"],
                "low": bands["LOW"],
            }
        )
    return rows


def generate_run_dashboard(
    project_root: Path,
    as_of_date: date,
    periods: Iterable[date],
    run_id: str,
    run_dir: Path,
    statistics: dict[str, Any] | None = None,
) -> Path:
    """Write a self-contained HTML dashboard next to this run's snapshot workbook."""

    as_of = as_of_date.isoformat()
    period_list = [period.isoformat() if isinstance(period, date) else str(period) for period in periods]
    facts = _read_csv(project_root / "outputs" / f"normalized_facts_{as_of}.csv")
    prices = _read_csv(project_root / "outputs" / f"quarter_end_prices_{as_of}.csv")
    reviews = _read_csv(project_root / "outputs" / f"review_queue_{as_of}.csv")
    gold_path = project_root / "outputs" / f"golden_validation_{as_of}.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
    stats = statistics or {}
    if not stats:
        manifest = run_dir / "run_manifest.json"
        if manifest.exists():
            stats = json.loads(manifest.read_text(encoding="utf-8"))
    # Prefer live gold validation file; fall back to manifest only if file missing.
    if not gold and stats.get("golden_validation_sample_size"):
        gold = {
            "passed": stats.get("golden_validation_passed")
            or int(
                round(
                    float(stats.get("golden_validation_accuracy") or 0)
                    * float(stats.get("golden_validation_sample_size") or 0)
                )
            ),
            "sample_size": stats.get("golden_validation_sample_size"),
            "accuracy": stats.get("golden_validation_accuracy"),
        }
    fixture_summary = gold.get("field_accuracy") or {}
    if not fixture_summary.get("issuer_count"):
        try:
            from cse_financial_etl.reporting.accuracy import summarize_gold_fixture

            fixture_summary = {
                **summarize_gold_fixture(
                    project_root / "tests" / "fixtures" / "golden_financial_facts.json"
                ),
                **fixture_summary,
            }
        except Exception:
            pass
    fact_status_counts = stats.get("fact_status_counts") or dict(
        Counter(row.get("status") or "UNKNOWN" for row in facts)
    )
    price_status_counts = stats.get("price_status_counts") or dict(
        Counter(row.get("status") or "UNKNOWN" for row in prices)
    )
    published = int(fact_status_counts.get("EXTRACTED") or 0) + int(
        fact_status_counts.get("EXTRACTED_DERIVED") or 0
    )
    payload = {
        "run_id": run_id,
        "as_of": as_of,
        "status": stats.get("run_status") or stats.get("status", ""),
        "periods": period_list,
        "security_count": stats.get("security_count", 0),
        "issuer_count": stats.get("issuer_count", 0),
        "filings": {
            "selected": stats.get("selected_filing_count", 0),
            "downloaded": stats.get("downloaded_filing_count", 0),
            "extracted": stats.get("extracted_filing_count", 0),
        },
        "errors": stats.get("pipeline_error_count", 0),
        "gates": (stats.get("production_gates") or {}).get("hit_count", 0),
        "published_facts": published,
        "gold": {
            "passed": gold.get("passed", 0),
            "sample": gold.get("sample_size", 0),
            "accuracy": gold.get("accuracy"),
            "issuer_count": gold.get("issuer_count")
            or fixture_summary.get("issuer_count")
            or 0,
            "manual_issuers": fixture_summary.get("manual_issuers", 0),
            "seeded_issuers": fixture_summary.get("seeded_issuers", 0),
            "by_metric": gold.get("by_metric", {}),
            "field_accuracy": gold.get("field_accuracy") or fixture_summary,
        },
        "code_version": stats.get("code_version", ""),
        "git_commit_sha": stats.get("git_commit_sha", ""),
        "git_branch": stats.get("git_branch", ""),
        "working_tree_dirty": stats.get("working_tree_dirty"),
        "equation_validation": stats.get("equation_validation", {}),
        "retry_summary": stats.get("retry_summary", {}),
        "fact_status_counts": fact_status_counts,
        "price_status_counts": price_status_counts,
        "miss_buckets": _miss_buckets(fact_status_counts, price_status_counts),
        "review_reasons": dict(Counter(row.get("reason") or "UNKNOWN" for row in reviews).most_common()),
        "coverage": _coverage(facts),
        "facts": _compact_facts(facts),
        "reviews": _compact_reviews(reviews),
        "prices": _compact_prices(prices),
        "definitions": [
            {"metric": metric, "kind": kind, "definition": definition, "scaling": scaling}
            for metric, kind, definition, scaling in DEFINITIONS
        ],
    }
    html = _render_html(payload)
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "dashboard.html"
    output_path.write_text(html, encoding="utf-8")
    latest = project_root / "outputs" / f"run_dashboard_{as_of}.html"
    latest.write_text(html, encoding="utf-8")
    return output_path


def _render_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>CSE ETL Run {payload["run_id"][:8]}</title>
  <style>
    :root {{
      --navy: #17365d;
      --blue: #1f4e78;
      --mid: #5b9bd5;
      --ink: #1a2332;
      --muted: #5b6777;
      --line: #d9e2f3;
      --bg: #f4f7fb;
      --card: #ffffff;
      --ok: #548235;
      --warn: #b45309;
      --bad: #9b1c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    header {{
      background: linear-gradient(135deg, #0f2e59 0%, #1b4f72 100%);
      color: #fff;
      padding: 22px 28px 18px;
    }}
    header h1 {{ margin: 0 0 8px; font-size: 22px; font-weight: 650; letter-spacing: -0.02em; }}
    header p {{ margin: 0; color: #cfe0f2; font-size: 13px; line-height: 1.45; }}
    header .meta {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }}
    header .chip {{
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.18);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      color: #e8f1fa;
    }}
    nav {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      padding: 12px 28px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    nav button {{
      border: 0;
      background: transparent;
      color: var(--blue);
      padding: 8px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
    }}
    nav button.active {{ background: var(--navy); color: #fff; }}
    main {{ padding: 20px 28px 48px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px 16px;
    }}
    .card .label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .card .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
    .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 12px; }}
    input, select {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 13px;
      min-width: 180px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; background: #fff; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 7px 8px; text-align: left; vertical-align: top; }}
    th {{ background: var(--navy); color: #fff; position: sticky; top: 52px; }}
    tbody tr:hover {{ background: #eef5fb; }}
    .pill {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 650;
    }}
    .ok {{ background: #e7f4dc; color: var(--ok); }}
    .warn {{ background: #fff4d6; color: var(--warn); }}
    .bad {{ background: #fde8e8; color: var(--bad); }}
    .muted {{ color: var(--muted); }}
    .note {{ color: var(--muted); font-size: 12px; margin: 8px 0 0; }}
    h2 {{ font-size: 16px; margin: 0 0 12px; }}
  </style>
</head>
<body>
  <header>
    <h1>CSE ETL run dashboard</h1>
    <p id="subtitle"></p>
    <div class="meta" id="header-meta"></div>
  </header>
  <nav id="tabs"></nav>
  <main id="root"></main>
  <script id="run-data" type="application/json">{data}</script>
  <script>
    const DATA = JSON.parse(document.getElementById("run-data").textContent);
    const TABS = ["overview","coverage","review","facts","prices","gold","definitions"];
    const LABELS = {{
      overview: "Overview", coverage: "Coverage", review: "Review queue",
      facts: "Facts", prices: "Prices", gold: "Gold", definitions: "Definitions"
    }};
    const state = {{ tab: "overview", q: "", metric: "", status: "", reason: "", certainty: "" }};

    function pill(value) {{
      const text = String(value || "");
      const ok = /EXTRACTED|PASSED|OK|COMPLETED/.test(text) && !/REVIEW|REQUIRED/.test(text);
      const bad = /FAIL|ERROR|UNRESOLVED|GATE/.test(text);
      const cls = ok ? "ok" : bad ? "bad" : "warn";
      return `<span class="pill ${{cls}}">${{esc(text)}}</span>`;
    }}
    function esc(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }})[ch]);
    }}
    function matches(row, keys) {{
      const q = state.q.trim().toLowerCase();
      if (!q) return true;
      return keys.some((key) => String(row[key] || "").toLowerCase().includes(q));
    }}
    function table(headers, rows, renderRow) {{
      if (!rows.length) return `<div class="card muted">No rows for this filter.</div>`;
      const shown = rows.slice(0, 400);
      return `<table><thead><tr>${{headers.map((h) => `<th>${{esc(h)}}</th>`).join("")}}</tr></thead>
        <tbody>${{shown.map(renderRow).join("")}}</tbody></table>
        <p class="note">Showing ${{shown.length}} of ${{rows.length}} rows.</p>`;
    }}
    function searchBar(extra) {{
      return `<div class="toolbar">
        <input id="q" placeholder="Search issuer, symbol, metric…" value="${{esc(state.q)}}"/>
        ${{extra || ""}}
      </div>`;
    }}
    function renderOverview() {{
      const goldSample = Number(DATA.gold.sample || 0);
      const goldPassed = Number(DATA.gold.passed || 0);
      const goldAcc = DATA.gold.accuracy == null ? "n/a" : `${{(Number(DATA.gold.accuracy) * 100).toFixed(1)}}%`;
      const goldLabel = goldSample
        ? `${{goldPassed.toLocaleString()}} / ${{goldSample.toLocaleString()}}`
        : "n/a";
      const buckets = DATA.miss_buckets || {{ honest: {{}}, parser: {{}}, honest_total: 0, parser_total: 0 }};
      const reviews = Object.values(DATA.review_reasons || {{}}).reduce((n, v) => n + v, 0);
      const eq = DATA.equation_validation || {{}};
      const retry = DATA.retry_summary || {{}};
      const meta = document.getElementById("header-meta");
      if (meta) {{
        meta.innerHTML = [
          `Run ${{esc((DATA.run_id || "").slice(0, 8))}}`,
          `As of ${{esc(DATA.as_of)}}`,
          `Git ${{esc((DATA.git_commit_sha || "").slice(0, 12) || "n/a")}}`,
          `Branch ${{esc(DATA.git_branch || "n/a")}}`,
          DATA.working_tree_dirty ? "Working tree dirty" : "Clean tree",
        ].map((text) => `<span class="chip">${{text}}</span>`).join("");
      }}
      const published = Number(DATA.published_facts || 0).toLocaleString();
      const hero = `<div class="grid">
          <div class="card"><div class="label">Run status</div><div class="value">${{pill(DATA.status || "n/a")}}</div></div>
          <div class="card"><div class="label">Gold checks</div><div class="value">${{esc(goldLabel)}}</div>
            <p class="note">${{esc(DATA.gold.issuer_count || 0)}} issuers · accuracy ${{esc(goldAcc)}}</p></div>
          <div class="card"><div class="label">Published facts (E+D)</div><div class="value">${{esc(published)}}</div></div>
          <div class="card"><div class="label">Production gates</div><div class="value">${{esc(DATA.gates)}}</div></div>
        </div>
        <div class="grid">
          <div class="card"><div class="label">Manual gold issuers</div><div class="value">${{esc(DATA.gold.manual_issuers || 0)}}</div></div>
          <div class="card"><div class="label">Seeded gold issuers</div><div class="value">${{esc(DATA.gold.seeded_issuers || 0)}}</div>
            <p class="note">Seeded rows are regression anchors, not independent PDF truth.</p></div>
          <div class="card"><div class="label">Equation FAIL</div><div class="value">${{esc(eq.FAIL || 0)}}</div>
            <p class="note">PASS ${{esc(eq.PASS || 0)}} · WARN ${{esc(eq.WARN || 0)}}</p></div>
          <div class="card"><div class="label">Retry recovered</div><div class="value">${{esc(retry.recovered || 0)}}</div>
            <p class="note">${{esc(retry.filings || 0)}} filings · ${{esc(retry.attempts || 0)}} attempts</p></div>
        </div>
        <div class="grid">
          <div class="card"><div class="label">Securities</div><div class="value">${{esc(DATA.security_count)}}</div></div>
          <div class="card"><div class="label">Issuers</div><div class="value">${{esc(DATA.issuer_count)}}</div></div>
          <div class="card"><div class="label">Filings extracted</div><div class="value">${{esc(DATA.filings.extracted)}}</div></div>
          <div class="card"><div class="label">Review items</div><div class="value">${{esc(reviews)}}</div></div>
          <div class="card"><div class="label">Honest misses</div><div class="value">${{esc(buckets.honest_total || 0)}}</div></div>
          <div class="card"><div class="label">Parser gaps</div><div class="value">${{esc(buckets.parser_total || 0)}}</div></div>
          <div class="card"><div class="label">Pipeline errors</div><div class="value">${{esc(DATA.errors)}}</div></div>
          <div class="card"><div class="label">Code version</div><div class="value">${{esc(DATA.code_version || "n/a")}}</div></div>
        </div>`;
      const facts = DATA.fact_status_counts || {{}};
      const statusRows = Object.entries(facts).map(([k, v]) => `<tr><td>${{esc(k)}}</td><td>${{esc(v)}}</td></tr>`).join("");
      const reasonRows = Object.entries(DATA.review_reasons || {{}}).map(([k, v]) => `<tr><td>${{esc(k)}}</td><td>${{esc(v)}}</td></tr>`).join("");
      const honestRows = Object.entries(buckets.honest || {{}}).map(([k, v]) => `<tr><td>${{esc(k)}}</td><td>${{esc(v)}}</td></tr>`).join("");
      const parserRows = Object.entries(buckets.parser || {{}}).map(([k, v]) => `<tr><td>${{esc(k)}}</td><td>${{esc(v)}}</td></tr>`).join("");
      return hero + `
        <div class="grid">
          <div class="card"><h2>Fact statuses</h2><table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>${{statusRows}}</tbody></table></div>
          <div class="card"><h2>Review reasons</h2><table><thead><tr><th>Reason</th><th>Count</th></tr></thead><tbody>${{reasonRows}}</tbody></table></div>
        </div>
        <div class="grid">
          <div class="card"><h2>Honest misses</h2><p class="note">Printed absence or no dated historical price. Not a parser gap.</p><table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>${{honestRows}}</tbody></table></div>
          <div class="card"><h2>Parser gaps</h2><p class="note">Line may exist in the filing but was not bound to a Company/Bank cell.</p><table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>${{parserRows}}</tbody></table></div>
        </div>
        <p class="note">Workbook for this run is snapshot-only. This page is the audit, coverage and review surface.</p>`;
    }}
    function renderCoverage() {{
      return table(
        ["Metric", "Total", "Extracted", "Coverage", "High", "Medium", "Low"],
        DATA.coverage,
        (row) => `<tr><td>${{esc(row.metric)}}</td><td>${{esc(row.total)}}</td><td>${{esc(row.extracted)}}</td>
          <td>${{(row.coverage * 100).toFixed(1)}}%</td><td>${{esc(row.high)}}</td><td>${{esc(row.medium)}}</td><td>${{esc(row.low)}}</td></tr>`
      );
    }}
    function renderReview() {{
      const reasons = [...new Set(DATA.reviews.map((r) => r.reason).filter(Boolean))].sort();
      const extra = `<select id="reason"><option value="">All reasons</option>${{reasons.map((r) =>
        `<option ${{r === state.reason ? "selected" : ""}}>${{esc(r)}}</option>`).join("")}}</select>`;
      const rows = DATA.reviews.filter((row) => (!state.reason || row.reason === state.reason) && matches(row, ["issuer","symbol","metric","reason","detail"]));
      return searchBar(extra) + table(
        ["Issuer", "Symbol", "Period", "Metric", "Reason", "Detail"],
        rows,
        (row) => `<tr><td>${{esc(row.issuer)}}</td><td>${{esc(row.symbol)}}</td><td>${{esc(row.period)}}</td>
          <td>${{esc(row.metric)}}</td><td>${{pill(row.reason)}}</td><td>${{esc(row.detail)}}</td></tr>`
      );
    }}
    function renderFacts() {{
      const metrics = [...new Set(DATA.facts.map((r) => r.metric).filter(Boolean))].sort();
      const statuses = [...new Set(DATA.facts.map((r) => r.status).filter(Boolean))].sort();
      const extra = `<select id="metric"><option value="">All metrics</option>${{metrics.map((m) =>
        `<option ${{m === state.metric ? "selected" : ""}}>${{esc(m)}}</option>`).join("")}}</select>
        <select id="status"><option value="">All statuses</option>${{statuses.map((s) =>
        `<option ${{s === state.status ? "selected" : ""}}>${{esc(s)}}</option>`).join("")}}</select>
        <select id="certainty"><option value="">All certainty</option>
        <option value="published" ${{state.certainty === "published" ? "selected" : ""}}>Published (not LOW)</option>
        <option value="LOW" ${{state.certainty === "LOW" ? "selected" : ""}}>LOW_CERTAINTY only</option></select>`;
      const rows = DATA.facts.filter((row) =>
        (!state.metric || row.metric === state.metric) &&
        (!state.status || row.status === state.status) &&
        (!state.certainty || (state.certainty === "LOW" ? row.certainty === "LOW" || row.status === "LOW_CERTAINTY" : row.certainty !== "LOW" && row.status !== "LOW_CERTAINTY")) &&
        matches(row, ["issuer","symbol","metric","status","line"])
      );
      return searchBar(extra) + table(
        ["Issuer", "Symbol", "Period", "Metric", "Status", "Value", "Entity", "Page", "Method", "Line"],
        rows,
        (row) => `<tr><td>${{esc(row.issuer)}}</td><td>${{esc(row.symbol)}}</td><td>${{esc(row.period)}}</td>
          <td>${{esc(row.metric)}}</td><td>${{pill(row.status)}}</td><td>${{esc(row.value)}}</td>
          <td>${{esc(row.entity)}}</td><td>${{esc(row.page)}}</td><td>${{esc(row.method)}}</td><td>${{esc(row.line)}}</td></tr>`
      );
    }}
    function renderPrices() {{
      const rows = DATA.prices.filter((row) => matches(row, ["issuer","symbol","method","status"]));
      return searchBar() + table(
        ["Issuer", "Symbol", "Period", "Value", "Method", "Status", "Page"],
        rows,
        (row) => `<tr><td>${{esc(row.issuer)}}</td><td>${{esc(row.symbol)}}</td><td>${{esc(row.period)}}</td>
          <td>${{esc(row.value)}}</td><td>${{esc(row.method)}}</td><td>${{pill(row.status)}}</td><td>${{esc(row.page)}}</td></tr>`
      );
    }}
    function renderGold() {{
      const metrics = Object.entries(DATA.gold.by_metric || {{}}).map(([metric, row]) => ({{ metric, ...row }}));
      const field = (DATA.gold.field_accuracy && DATA.gold.field_accuracy.field_accuracy)
        ? DATA.gold.field_accuracy.field_accuracy
        : (DATA.gold.field_accuracy || {{}});
      const pct = (value) => value == null ? "n/a" : `${{(Number(value) * 100).toFixed(1)}}%`;
      return `<div class="grid">
          <div class="card"><div class="label">Numeric accuracy</div><div class="value">${{DATA.gold.accuracy == null ? "n/a" : (DATA.gold.accuracy * 100).toFixed(1) + "%"}}</div></div>
          <div class="card"><div class="label">Passed / sample</div><div class="value">${{esc(DATA.gold.passed)}} / ${{esc(DATA.gold.sample)}}</div>
            <p class="note">${{esc(DATA.gold.issuer_count || 0)}} issuers (manual ${{esc(DATA.gold.manual_issuers || 0)}} · seeded ${{esc(DATA.gold.seeded_issuers || 0)}})</p></div>
          <div class="card"><div class="label">Wrong-populated rate</div><div class="value">${{esc(pct(field.wrong_populated_value_rate))}}</div></div>
          <div class="card"><div class="label">False-missing rate</div><div class="value">${{esc(pct(field.false_missing_rate))}}</div></div>
        </div>` + table(
        ["Metric", "Sample", "Passed", "Failed", "Accuracy"],
        metrics,
        (row) => `<tr><td>${{esc(row.metric)}}</td><td>${{esc(row.sample_size)}}</td><td>${{esc(row.passed)}}</td>
          <td>${{esc(row.failed)}}</td><td>${{row.accuracy == null ? "" : (row.accuracy * 100).toFixed(1) + "%"}}</td></tr>`
      );
    }}
    function renderDefinitions() {{
      return table(
        ["Metric", "Type", "Definition", "Scaling"],
        DATA.definitions,
        (row) => `<tr><td>${{esc(row.metric)}}</td><td>${{esc(row.kind)}}</td><td>${{esc(row.definition)}}</td><td>${{esc(row.scaling)}}</td></tr>`
      );
    }}
    const views = {{
      overview: renderOverview, coverage: renderCoverage, review: renderReview,
      facts: renderFacts, prices: renderPrices, gold: renderGold, definitions: renderDefinitions
    }};
    function paint() {{
      document.getElementById("subtitle").textContent =
        `Run ${{DATA.run_id}}  ·  market ${{DATA.as_of}}  ·  periods ${{(DATA.periods || []).join(" · ")}}`;
      document.getElementById("tabs").innerHTML = TABS.map((tab) =>
        `<button data-tab="${{tab}}" class="${{tab === state.tab ? "active" : ""}}">${{LABELS[tab]}}</button>`
      ).join("");
      document.getElementById("root").innerHTML = views[state.tab]();
      document.querySelectorAll("nav button").forEach((btn) => btn.addEventListener("click", () => {{
        state.tab = btn.dataset.tab;
        paint();
      }}));
      const q = document.getElementById("q");
      if (q) q.addEventListener("input", (event) => {{ state.q = event.target.value; paint(); q.focus(); q.setSelectionRange(state.q.length, state.q.length); }});
      const metric = document.getElementById("metric");
      if (metric) metric.addEventListener("change", (event) => {{ state.metric = event.target.value; paint(); }});
      const status = document.getElementById("status");
      if (status) status.addEventListener("change", (event) => {{ state.status = event.target.value; paint(); }});
      const reason = document.getElementById("reason");
      if (reason) reason.addEventListener("change", (event) => {{ state.reason = event.target.value; paint(); }});
      const certainty = document.getElementById("certainty");
      if (certainty) certainty.addEventListener("change", (event) => {{ state.certainty = event.target.value; paint(); }});
    }}
    paint();
  </script>
</body>
</html>
"""
