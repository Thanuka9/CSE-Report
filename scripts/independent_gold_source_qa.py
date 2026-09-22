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
        r"\boperating.*profit\b",
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
        r"\bearnings per ordinary share.*basic", r"\bbasic.*per share",
    )),
    "EPS_DILUTED": tuple(re.compile(p, re.I) for p in (
        r"\bdiluted earnings per share\b", r"\bdiluted.*earnings.*share",
        r"\bearnings per share.*diluted", r"\bdiluted eps\b",
        r"\bearnings per ordinary share.*diluted", r"\bdiluted.*per share",
    )),
    "NAVPS": tuple(re.compile(p, re.I) for p in (
        r"\bnet assets? per share\b", r"\bnet asset value per share\b",
        r"\bnav per share\b", r"\bnavps\b", r"\bnet asset per share\b",
        r"\bnet assets per ordinary share\b", r"\bnet asset value per ordinary share\b",
    )),
    "TOTAL_ASSETS": (re.compile(r"\btotal assets\b", re.I),),
    "TOTAL_EQUITY": tuple(re.compile(p, re.I) for p in (
        r"\btotal equity\b", r"\btotal shareholders'? funds\b",
        r"\btotal shareholders'? equity\b",
        r"\bequity attributable to.*(?:owners|equity holders)\b",
        r"\btotal.*equity attributable to.*(?:owners|equity holders)\b",
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
    declared_scale: Decimal
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
    """Detect a statement unit declaration, not narrative monetary prose."""
    normalized = text.casefold().replace("’", "'").replace("‘", "'")
    # '000 is declaration syntax, not ordinary narrative prose, so it is safe to
    # detect even when the PDF merges a whole table header into one long text line.
    if re.search(r"(?:rs\.?|lkr)\s*[' ]?000s?\b", normalized):
        return Decimal("1000")
    for line in normalized.splitlines():
        t = line.strip()
        # Mn/Bn words also occur in narrative; only trust compact declaration lines.
        if len(t) > 90:
            continue
        if re.search(r"(?:rs\.?|lkr)\s*(?:mn|million)\b", t):
            return Decimal("1000000")
        if re.search(r"(?:rs\.?|lkr)\s*(?:bn|billion)\b", t):
            return Decimal("1000000000")
    return Decimal("1")


def _y_center(word: tuple[Any, ...]) -> float:
    return (float(word[1]) + float(word[3])) / 2.0


def group_rows(words: list[tuple[Any, ...]]) -> list[list[tuple[Any, ...]]]:
    """Cluster words by visual baseline, ignoring PyMuPDF block/line IDs.

    CSE tables often split a visible row into separate logical PDF blocks, which
    made the first verifier miss correct facts such as JKH PAT/PBT/OP.
    """
    ordered = sorted((w for w in words if len(w) >= 5), key=lambda w: (_y_center(w), float(w[0])))
    rows: list[list[tuple[Any, ...]]] = []
    centers: list[float] = []
    for word in ordered:
        yc = _y_center(word)
        best = None
        best_dist = 10.0
        for idx, center in enumerate(centers[-4:], start=max(0, len(centers) - 4)):
            dist = abs(yc - center)
            if dist <= 4.5 and dist < best_dist:
                best = idx
                best_dist = dist
        if best is None:
            rows.append([word])
            centers.append(yc)
        else:
            rows[best].append(word)
            centers[best] = sum(_y_center(w) for w in rows[best]) / len(rows[best])
    for row in rows:
        row.sort(key=lambda w: float(w[0]))
    rows.sort(key=lambda row: (_y_center(row[0]), float(row[0][0])))
    return rows


def row_text(row: list[tuple[Any, ...]]) -> str:
    return " ".join(str(w[4]) for w in row)


def alias_ok(metric: str, text: str) -> bool:
    return any(p.search(text) for p in ALIASES.get(metric, ()))


def period_ok(text: str, target: str) -> bool:
    if target == "2026-06-30":
        if any(p.search(text) for p in PERIOD_PATTERNS):
            return True
        compact = text.casefold()
        return bool(
            re.search(r"30\s*(?:th)?\s*june\b", compact)
            and re.search(r"\b2026\b", compact)
        )
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
        if y - 320 <= wy0 <= y + 4 and abs(cx - x) <= 140:
            chosen.append(w)
    chosen.sort(key=lambda w: (float(w[1]), float(w[0])))
    return " ".join(str(w[4]) for w in chosen)[-1800:]


def row_band_text(
    words: list[tuple[Any, ...]],
    number_word: tuple[Any, ...],
    rows: list[list[tuple[Any, ...]]],
    metric: str,
) -> str:
    """Recover the visible row around a number regardless of PDF block splitting."""
    yc = _y_center(number_word)
    x0 = float(number_word[0])
    same = [
        w
        for w in words
        if abs(_y_center(w) - yc) <= 5.0 and float(w[0]) <= x0 + 320
    ]
    same.sort(key=lambda w: float(w[0]))
    text = " ".join(str(w[4]) for w in same)
    if alias_ok(metric, text):
        return text

    # Wrapped labels may sit one or two visual baselines away from the numeric row,
    # or PyMuPDF may split the label into a separate block entirely.
    nearby: list[tuple[float, str]] = []
    for row in rows:
        if not row:
            continue
        ry = sum(_y_center(w) for w in row) / len(row)
        dist = abs(yc - ry)
        if dist > 52:
            continue
        rtext = " ".join(str(w[4]) for w in row)
        if alias_ok(metric, rtext):
            left_penalty = 0.0 if min(float(w[0]) for w in row) < x0 else 18.0
            nearby.append((dist + left_penalty, rtext))
    if nearby:
        nearby.sort(key=lambda item: item[0])
        return f"{nearby[0][1]} {text}"
    return text


def nearest_year(words: list[tuple[Any, ...]], x: float, y: float) -> str | None:
    candidates: list[tuple[float, str]] = []
    for w in words:
        token = str(w[4]).strip()
        if token not in {"2024", "2025", "2026", "2027"}:
            continue
        wy = _y_center(w)
        if not (y - 320 <= wy <= y + 4):
            continue
        cx = (float(w[0]) + float(w[2])) / 2
        candidates.append((abs(cx - x) + max(0.0, y - wy) * 0.08, token))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def column_entity_ok(scope: str, words: list[tuple[Any, ...]], x: float, y: float, page_text: str) -> bool:
    ctx = header_context(words, x, y).casefold()
    page = page_text.casefold()

    labels: list[tuple[float, str]] = []
    for w in words:
        token = str(w[4]).strip().casefold()
        if token not in {"company", "bank", "group", "consolidated", "separate"}:
            continue
        wy = _y_center(w)
        if not (y - 360 <= wy <= y + 4):
            continue
        cx = (float(w[0]) + float(w[2])) / 2
        labels.append((abs(cx - x) + max(0.0, y - wy) * 0.04, token))
    labels.sort()
    nearest = labels[0][1] if labels else None

    if scope == "BANK":
        if nearest == "bank":
            return True
        if "bank" in ctx and "group" not in ctx:
            return True
        if "bank" in page and "group" not in page and "consolidated" not in page:
            return True
        return False
    if scope == "COMPANY":
        if nearest in {"company", "separate"}:
            return True
        if "company" in ctx or "separate" in ctx:
            return True
        if "company income statement" in page or "company statement of financial position" in page:
            return True
        if "group" not in page and "consolidated" not in page:
            return True
        return False
    return False


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
        document_text = " ".join(page[1] for page in pages[:4])
        p_period = period_ok(ptext, target_period) or period_ok(document_text, target_period)
        p_duration = duration_ok(ptext) or duration_ok(document_text)
        for w in words:
            raw = parse_num(str(w[4]))
            if raw is None:
                continue
            x = (float(w[0]) + float(w[2])) / 2
            y = (float(w[1]) + float(w[3])) / 2
            text = row_band_text(words, w, rows, metric)
            if not alias_ok(metric, text):
                continue
            ctx = header_context(words, x, y)
            year = nearest_year(words, x, y)
            target_year = target_period[:4]
            c_period = p_period and (year in {None, target_year})
            c_duration = duration_ok(ctx) or p_duration
            c_entity = column_entity_ok(scope, words, x, y, ptext)
            effective_declared_scale = (
                Decimal("1") if metric in PER_SHARE else detected_scale
            )
            for scale in candidate_scales(metric, effective_declared_scale):
                normalized = raw * scale
                if not close(normalized, expected):
                    continue
                score = 6
                if scale == effective_declared_scale:
                    score += 4
                elif metric in MONETARY and effective_declared_scale != Decimal("1"):
                    score -= 4
                else:
                    score -= 1
                score += 3 if c_period else -2
                score += 3 if c_entity else -2
                if metric in FLOW_METRICS:
                    score += 3 if c_duration else -2
                matches.append(
                    Match(
                        page=page_index + 1,
                        row_text=text[:900],
                        raw_number=raw,
                        scale=scale,
                        normalized=normalized,
                        declared_scale=effective_declared_scale,
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
        return "FAIL", "Expected value was not independently located on an applicable source row."
    best = matches[0]
    scale_problem = metric in MONETARY and best.scale != Decimal("1") and best.score < 10
    if scale_problem:
        return "REVIEW", "Numeric claim was located, but source scale needs adjudication."
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
                    "declared_scale": str(best.declared_scale) if best else "",
                    "scale_consistent": bool(best.scale == best.declared_scale) if best else False,
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
        "declared_scale","scale_consistent","recomputed_value","period_ok","duration_ok",
        "entity_ok","evidence_score",
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
