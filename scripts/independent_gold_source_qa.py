#!/usr/bin/env python3
"""Independent source QA for the 100-issuer CSE gold fixture.

This deliberately does NOT import or call V1/V2 extraction logic. It treats the
fixture as a set of claims and verifies those claims against official CSE PDFs
using PyMuPDF geometry/text only.

Results are AI/source QA evidence. They must not be relabelled MANUAL_QA without
human sign-off.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "golden_financial_facts.json"
BASE_URL = "https://cdn.cse.lk/cmt/upload_report_file/"
FLOW_METRICS = {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT", "EPS_BASIC", "EPS_DILUTED"}
PER_SHARE = {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}
MONETARY = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}

ALIASES: dict[str, tuple[re.Pattern[str], ...]] = {
    "TOP_LINE": tuple(re.compile(p, re.I) for p in (
        r"\brevenue\b", r"\btotal revenue\b", r"\bturnover\b", r"\bgross income\b",
        r"\btotal operating income\b", r"\binterest income\b", r"\binsurance revenue\b",
        r"\bgross written premium", r"\bnet earned premium", r"\boperating income\b",
        r"\btotal income\b",
    )),
    "OPERATING_PROFIT": tuple(re.compile(p, re.I) for p in (
        r"\boperating profit\b", r"\bprofit from operations?\b",
        r"\bresults? from operating activities\b", r"\boperating results?\b",
        r"\bprofit from operating activities\b", r"\bprofit before vat",
    )),
    "PBT": tuple(re.compile(p, re.I) for p in (
        r"\bprofit.*before.*tax", r"\bloss.*before.*tax",
        r"\bprofit before taxation\b", r"\bprofit before income tax\b",
    )),
    "PAT": tuple(re.compile(p, re.I) for p in (
        r"\bprofit.*after.*tax", r"\bloss.*after.*tax",
        r"\bprofit.*for the (?:period|quarter)\b", r"\bloss.*for the (?:period|quarter)\b",
        r"\bnet profit\b", r"\bnet loss\b",
    )),
    "EPS_BASIC": tuple(re.compile(p, re.I) for p in (
        r"\bbasic earnings per share\b", r"\bbasic.*earnings.*share",
        r"\bearnings per share.*basic", r"\bbasic eps\b",
    )),
    "EPS_DILUTED": tuple(re.compile(p, re.I) for p in (
        r"\bdiluted earnings per share\b", r"\bdiluted.*earnings.*share",
        r"\bearnings per share.*diluted", r"\bdiluted eps\b",
    )),
    "NAVPS": tuple(re.compile(p, re.I) for p in (
        r"\bnet assets? per share\b", r"\bnet asset value per share\b",
        r"\bnav per share\b", r"\bnavps\b",
    )),
    "TOTAL_ASSETS": (re.compile(r"\btotal assets\b", re.I),),
    "TOTAL_EQUITY": tuple(re.compile(p, re.I) for p in (
        r"\btotal equity\b", r"\btotal shareholders'? funds\b",
        r"\btotal shareholders'? equity\b",
    )),
    "TOTAL_LIABILITIES": (re.compile(r"\btotal liabilities\b", re.I),),
}

PERIOD_PATTERNS = (
    re.compile(r"30\s*(?:th)?\s*june\s*2026", re.I),
    re.compile(r"30[.\-/ ]0?6[.\-/ ]2026", re.I),
    re.compile(r"30[.\-/ ]jun(?:e)?[.\-/ ]26", re.I),
    re.compile(r"30\s*jun(?:e)?\s*2026", re.I),
)
THREE_MONTH_PATTERNS = (
    re.compile(r"\bthree\s+months?\b", re.I),
    re.compile(r"\b3\s*months?\b", re.I),
    re.compile(r"\b03\s*months?\b", re.I),
    re.compile(r"\bquarter\s+ended\b", re.I),
    re.compile(r"\bfor the quarter\b", re.I),
)


@dataclass(frozen=True)
class Match:
    page: int
    row_text: str
    raw_number: Decimal
    scale: Decimal
    normalized: Decimal
    header_context: str
    period_ok: bool
    duration_ok: bool
    entity_ok: bool
    score: int


def norm_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def parse_num(text: str) -> Decimal | None:
    s = text.strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"(?i)(?:rs\.?|lkr)", "", s).strip()
    if s in {"-", "—", ""} or not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s):
        return None
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    return -val if neg else val


def derive_urls(local_path: str) -> list[str]:
    name = Path(local_path).name
    name = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", name)
    names = [name]
    m = re.match(r"^(\d+_\d+)", name)
    if m:
        base = m.group(1) + ".pdf"
        if base not in names:
            names.append(base)
    return [BASE_URL + urllib.parse.quote(n, safe="._-()'") for n in names]


def download(urls: list[str], destination: Path) -> tuple[str, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for url in urls:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 CSE-independent-gold-QA/1.0",
                "Accept": "application/pdf,*/*",
            },
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=45) as response:
                    payload = response.read()
                if not payload.startswith(b"%PDF"):
                    raise RuntimeError("response is not a PDF")
                destination.write_bytes(payload)
                return url, hashlib.sha256(payload).hexdigest()
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(1.0 + attempt)
    raise RuntimeError(last_error or "download failed")


def page_scale(text: str) -> Decimal:
    t = text.casefold().replace("’", "'").replace("‘", "'")
    if re.search(r"(?:rs\.?|lkr)\s*[' ]?000\b", t):
        return Decimal("1000")
    if re.search(r"(?:rs\.?|lkr)\s*(?:mn|million)\b", t):
        return Decimal("1000000")
    if re.search(r"(?:rs\.?|lkr)\s*(?:bn|billion)\b", t):
        return Decimal("1000000000")
    return Decimal("1")


def group_rows(words: list[tuple[Any, ...]]) -> list[list[tuple[Any, ...]]]:
    rows: dict[tuple[int, int], list[tuple[Any, ...]]] = defaultdict(list)
    for word in words:
        if len(word) >= 8:
            rows[(int(word[5]), int(word[6]))].append(word)
    result = []
    for row in rows.values():
        row.sort(key=lambda w: float(w[0]))
        result.append(row)
    result.sort(key=lambda row: (float(row[0][1]), float(row[0][0])))
    return result


def row_text(row: list[tuple[Any, ...]]) -> str:
    return " ".join(str(w[4]) for w in row)


def alias_ok(metric: str, text: str) -> bool:
    return any(p.search(text) for p in ALIASES.get(metric, ()))


def period_ok(text: str, target: str) -> bool:
    if target == "2026-06-30":
        return any(p.search(text) for p in PERIOD_PATTERNS)
    y, m, d = target.split("-")
    month = {"12": "december", "03": "march", "06": "june"}.get(m)
    return bool(month and re.search(rf"\b{int(d)}\s+{month}\s+{y}\b", text, re.I))


def duration_ok(text: str) -> bool:
    return any(p.search(text) for p in THREE_MONTH_PATTERNS)


def entity_ok(scope: str, text: str) -> bool:
    t = text.casefold()
    if scope == "BANK":
        return "bank" in t or ("company" in t and "group" not in t)
    if scope == "COMPANY":
        return "company" in t or not any(k in t for k in ("group", "consolidated"))
    return False


def header_context(words: list[tuple[Any, ...]], x: float, y: float) -> str:
    chosen = []
    for w in words:
        wx0, wy0, wx1, _ = map(float, w[:4])
        cx = (wx0 + wx1) / 2
        if y - 260 <= wy0 <= y + 4 and abs(cx - x) <= 95:
            chosen.append(w)
    chosen.sort(key=lambda w: (float(w[1]), float(w[0])))
    return " ".join(str(w[4]) for w in chosen)[-1200:]


def close(a: Decimal, b: Decimal) -> bool:
    if a == b:
        return True
    tol = max(Decimal("0.0005"), abs(b) * Decimal("0.0000005"))
    return abs(a - b) <= tol


def candidate_scales(metric: str, detected: Decimal) -> tuple[Decimal, ...]:
    if metric in PER_SHARE:
        return (Decimal("1"),)
    ordered = [detected, Decimal("1"), Decimal("1000"), Decimal("1000000")]
    out = []
    for scale in ordered:
        if scale not in out:
            out.append(scale)
    return tuple(out)


def prepare_pages(doc: fitz.Document) -> list[tuple[int, str, list[tuple[Any, ...]], list[list[tuple[Any, ...]]], Decimal]]:
    pages = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        ptext = page.get_text("text")
        words = page.get_text("words")
        if not words:
            continue
        pages.append((page_index, ptext, words, group_rows(words), page_scale(ptext)))
    return pages


def find_matches(
    pages: list[tuple[int, str, list[tuple[Any, ...]], list[list[tuple[Any, ...]]], Decimal]],
    metric: str,
    expected: Decimal,
    scope: str,
    target_period: str,
) -> list[Match]:
    matches = []
    for page_index, ptext, words, rows, detected_scale in pages:
        p_period = period_ok(ptext, target_period)
        p_duration = duration_ok(ptext)
        p_entity = entity_ok(scope, ptext)
        for row in rows:
            text = row_text(row)
            if not alias_ok(metric, text):
                continue
            for w in row:
                raw = parse_num(str(w[4]))
                if raw is None:
                    continue
                x = (float(w[0]) + float(w[2])) / 2
                y = (float(w[1]) + float(w[3])) / 2
                ctx = header_context(words, x, y)
                c_period = period_ok(ctx, target_period) or p_period
                c_duration = duration_ok(ctx) or (
                    p_duration and "three months" in ptext.casefold()[:3000]
                )
                c_entity = entity_ok(scope, ctx) or (
                    p_entity and not any(k in ctx.casefold() for k in ("group", "consolidated"))
                )
                for scale in candidate_scales(metric, detected_scale):
                    normalized = raw * scale
                    if not close(normalized, expected):
                        continue
                    score = 6
                    score += 4 if scale == detected_scale else -2
                    score += 3 if c_period else 0
                    score += 3 if c_entity else 0
                    if metric in FLOW_METRICS:
                        score += 3 if c_duration else -2
                    matches.append(
                        Match(
                            page=page_index + 1,
                            row_text=text[:700],
                            raw_number=raw,
                            scale=scale,
                            normalized=normalized,
                            header_context=ctx,
                            period_ok=c_period,
                            duration_ok=(c_duration if metric in FLOW_METRICS else True),
                            entity_ok=c_entity,
                            score=score,
                        )
                    )
    return sorted(matches, key=lambda m: (-m.score, m.page))


def classify(metric: str, matches: list[Match]) -> tuple[str, str]:
    if not matches:
        return "FAIL", "Expected value not found on a matching source row with acceptable scale."
    best = matches[0]
    threshold = 12 if metric in FLOW_METRICS else 10
    if best.score >= threshold and best.period_ok and best.entity_ok and best.duration_ok:
        return "PASS_STRONG", "Exact value and required source context independently located."
    return "REVIEW", "Exact value located, but period/duration/entity/scale context needs visual adjudication."


def issuer_identity_ok(
    pages: list[tuple[int, str, list[tuple[Any, ...]], list[list[tuple[Any, ...]]], Decimal]],
    issuer: str,
) -> bool:
    text = " ".join(page[1] for page in pages[:3])
    if norm_name(issuer) in norm_name(text):
        return True
    tokens = [t for t in re.findall(r"[a-z0-9]+", issuer.casefold()) if len(t) > 3]
    return sum(t in text.casefold() for t in tokens) >= max(1, min(2, len(tokens)))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "gold_gate" / "independent_ai_qa",
    )
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".qa_cache" / "gold_pdfs")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.35)
    args = parser.parse_args()

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if args.limit:
        fixture = fixture[: args.limit]

    fact_rows: list[dict[str, Any]] = []
    issuer_rows: list[dict[str, Any]] = []
    download_errors: list[dict[str, str]] = []

    for index, item in enumerate(fixture, start=1):
        issuer = str(item["issuer_name"])
        symbol = str(item["symbol"])
        scope = str(item["entity_scope"])
        period = str(item["period_end"])
        urls = derive_urls(str(item["pdf"]))
        cache = args.cache_dir / f"{index:03d}_{symbol.replace('.', '_')}.pdf"
        print(f"[{index:03d}/{len(fixture)}] {issuer}", flush=True)
        try:
            used_url, sha256 = download(urls, cache)
            time.sleep(args.sleep)
            doc = fitz.open(cache)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            download_errors.append(
                {"issuer": issuer, "symbol": symbol, "error": message, "url": urls[0]}
            )
            issuer_rows.append(
                {
                    "issuer_index": index,
                    "issuer_name": issuer,
                    "symbol": symbol,
                    "period_end": period,
                    "scope": scope,
                    "pdf_url": urls[0],
                    "pdf_sha256": "",
                    "fact_count": len(item.get("facts", {})),
                    "pass_strong": 0,
                    "review": 0,
                    "fail": len(item.get("facts", {})),
                    "issuer_result": "DOWNLOAD_FAIL",
                    "identity_ok": False,
                    "prior_verification_status": item.get("verification_status", ""),
                }
            )
            continue

        pages = prepare_pages(doc)
        identity = issuer_identity_ok(pages, issuer)
        counts: Counter[str] = Counter()
        for metric, value in item.get("facts", {}).items():
            expected = Decimal(str(value))
            matches = find_matches(pages, str(metric), expected, scope, period)
            result, note = classify(str(metric), matches)
            if not identity and result == "PASS_STRONG":
                result = "REVIEW"
                note = "Fact matched, but issuer identity was not independently confirmed."
            counts[result] += 1
            best = matches[0] if matches else None
            fact_rows.append(
                {
                    "issuer_index": index,
                    "issuer_name": issuer,
                    "symbol": symbol,
                    "period_end": period,
                    "scope": scope,
                    "metric_code": metric,
                    "expected_value": str(expected),
                    "qa_result": result,
                    "evidence_page": best.page if best else "",
                    "source_raw_value": str(best.raw_number) if best else "",
                    "source_scale": str(best.scale) if best else "",
                    "recomputed_value": str(best.normalized) if best else "",
                    "period_ok": bool(best.period_ok) if best else False,
                    "duration_ok": bool(best.duration_ok) if best else False,
                    "entity_ok": bool(best.entity_ok) if best else False,
                    "evidence_score": best.score if best else 0,
                    "source_row": best.row_text if best else "",
                    "column_context": best.header_context if best else "",
                    "pdf_url": used_url,
                    "pdf_sha256": sha256,
                    "prior_verification_status": item.get("verification_status", ""),
                    "note": note,
                }
            )

        total = len(item.get("facts", {}))
        strong = counts["PASS_STRONG"]
        review = counts["REVIEW"]
        fail = counts["FAIL"]
        issuer_result = (
            "AI_QA_FAIL" if fail else "AI_QA_REVIEW" if review else "AI_QA_PASS"
        )
        issuer_rows.append(
            {
                "issuer_index": index,
                "issuer_name": issuer,
                "symbol": symbol,
                "period_end": period,
                "scope": scope,
                "pdf_url": used_url,
                "pdf_sha256": sha256,
                "fact_count": total,
                "pass_strong": strong,
                "review": review,
                "fail": fail,
                "issuer_result": issuer_result,
                "identity_ok": identity,
                "prior_verification_status": item.get("verification_status", ""),
            }
        )
        doc.close()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    fact_fields = [
        "issuer_index","issuer_name","symbol","period_end","scope","metric_code",
        "expected_value","qa_result","evidence_page","source_raw_value","source_scale",
        "recomputed_value","period_ok","duration_ok","entity_ok","evidence_score",
        "source_row","column_context","pdf_url","pdf_sha256",
        "prior_verification_status","note",
    ]
    issuer_fields = [
        "issuer_index","issuer_name","symbol","period_end","scope","pdf_url","pdf_sha256",
        "fact_count","pass_strong","review","fail","issuer_result","identity_ok",
        "prior_verification_status",
    ]
    write_csv(out / "fact_qa.csv", fact_rows, fact_fields)
    write_csv(out / "issuer_qa.csv", issuer_rows, issuer_fields)

    fact_counts = Counter(row["qa_result"] for row in fact_rows)
    issuer_counts = Counter(row["issuer_result"] for row in issuer_rows)
    summary = {
        "method": (
            "Independent AI/source QA using official CSE PDFs and PyMuPDF geometry only; "
            "no V1/V2 extractor calls."
        ),
        "fixture_count": len(fixture),
        "fact_count": len(fact_rows),
        "issuer_results": dict(issuer_counts),
        "fact_results": dict(fact_counts),
        "download_error_count": len(download_errors),
        "download_errors": download_errors,
        "manual_qa_count_before": sum(
            item.get("verification_status") == "MANUAL_QA" for item in fixture
        ),
        "human_gate_satisfied_by_this_run": False,
        "reason": "AI source QA supports but does not replace MANUAL_QA human sign-off.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    review_issuers = [r for r in issuer_rows if r["issuer_result"] != "AI_QA_PASS"]
    report = [
        "# Independent CSE Gold Source QA",
        "",
        "**AI/source QA evidence - not MANUAL_QA human sign-off.**",
        "",
        f"- Issuers attempted: **{len(fixture)}**",
        f"- Facts checked: **{len(fact_rows)}**",
        f"- AI_QA_PASS issuers: **{issuer_counts.get('AI_QA_PASS', 0)}**",
        f"- AI_QA_REVIEW issuers: **{issuer_counts.get('AI_QA_REVIEW', 0)}**",
        f"- AI_QA_FAIL issuers: **{issuer_counts.get('AI_QA_FAIL', 0)}**",
        f"- Download failures: **{len(download_errors)}**",
        f"- Strong fact passes: **{fact_counts.get('PASS_STRONG', 0)}**",
        f"- Fact reviews: **{fact_counts.get('REVIEW', 0)}**",
        f"- Fact fails: **{fact_counts.get('FAIL', 0)}**",
        "",
        "## Method",
        "",
        "Every fixture claim was checked against the official CSE PDF referenced by the",
        "production corpus filename. Numeric value, row label, source scale, current",
        "period, three-month duration where required, and entity context were evaluated",
        "using independent PyMuPDF text/geometry. No V1/V2 extraction function is called.",
        "",
        "## Issuers requiring adjudication",
        "",
        "| Issuer | Result | Strong | Review | Fail | PDF |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in review_issuers:
        report.append(
            f"| {r['issuer_name']} | {r['issuer_result']} | {r['pass_strong']} | "
            f"{r['review']} | {r['fail']} | {r['pdf_url']} |"
        )
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
