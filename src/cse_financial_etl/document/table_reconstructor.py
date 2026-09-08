"""Reconstruct table structure from page geometry.

Contract (audit finding 1):

* The reconstructor consumes the canonical :class:`PageIR` (``.lines`` with token
  geometry, ``.width``) — never an ad-hoc wrapper.
* Body cells are bound to stable geometric column intervals derived from the
  right-edge clusters of numeric tokens.  A blank intermediate cell or a note
  column can therefore never shift a value into a neighbouring column.
* Each page may contain several tables.  A new table starts whenever a header
  region (lines carrying year/date tokens and header cue words) appears after
  body rows of the previous table.  Header phrases, title lines, caption
  phrases and in-body unit-only lines are preserved with their geometry so the
  compiler can bind them spatially instead of guessing.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from cse_financial_etl.document.document_ir import (
    BBox,
    CanonicalDocumentIR,
    HeaderPhraseIR,
    LineIR,
    PageIR,
    TableCellIR,
    TableColumnIR,
    TableIR,
    TokenIR,
    UnitLineIR,
)

_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_DATE_NUMERIC_RE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})$|^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?,?$",
    re.I,
)
_DAY_RE = re.compile(r"^\d{1,2}(?:st|nd|rd|th)?,?$", re.I)
_DAY_MONTH_PHRASE_RE = re.compile(
    r"^(?:as at\s+)?\d{1,2}(?:st|nd|rd|th)?[\s,.-]*(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?,?$",
    re.I,
)
_NUMERIC_RE = re.compile(r"^\(?-?[\d][\d,]*(?:\.\d+)?\)?%?$|^\(?-?\.\d+\)?%?$")
_DASH_TOKENS = {"-", "–", "—", "‑", "−"}
_HEADER_CUE_RE = re.compile(
    r"\b(group|company|bank|consolidated|separate|quarter|months?|ended|ending|"
    r"as at|year|period|audited|unaudited|reviewed|restated|notes?|change|"
    r"current|comparative|for the|to)\b",
    re.I,
)
_UNIT_WORD_RE = re.compile(
    r"^\(?(?:rs\.?|lkr|usd|us\$|\$|rupees?|sri lanka(?:n)? rupees?|mn\.?|million|bn\.?|billion|"
    r"'?000|thousands?|in thousands|cents?|%)\)?\.?$",
    re.I,
)
_UNIT_PHRASE_RE = re.compile(
    r"^\(?(?:in\s+)?(?:"
    r"(?:rs\.?|lkr|usd|us\$|rupees?|sri\s+lankan?\s+rupees?)\s*'?(?:000|mn\.?|millions?|bn\.?|billions?|thousands?)?"
    r"|'?000|(?:thousand|million|billion)s?|%|cents?)\.?\)?$",
    re.I,
)
_ANNOTATION_RE = re.compile(r"^\(?(?:un)?audited\)?$|^\(?reviewed\)?$|^\(?restated\)?$|^\(?re-?stated\)?$", re.I)
_SECTION_END_RE = re.compile(r":\s*$")


@dataclass
class _Row:
    line: LineIR
    label_tokens: list[TokenIR] = field(default_factory=list)
    numeric_tokens: list[TokenIR] = field(default_factory=list)
    kind: str = "text"  # body | header | unit | text
    merged_label_prefix: str = ""


def reconstruct_tables(document: CanonicalDocumentIR) -> CanonicalDocumentIR:
    """Attach TableIR objects to each page (header regions + geometry-bound body cells)."""

    pages: list[PageIR] = []
    for page in document.pages:
        tables = tuple(reconstruct_page_tables(page))
        pages.append(
            PageIR(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                tokens=page.tokens,
                lines=page.lines,
                tables=tables,
            )
        )
    return CanonicalDocumentIR(
        pages=tuple(pages),
        quality=document.quality,
        source_sha256=document.source_sha256,
        source_path=document.source_path,
    )


# ---------------------------------------------------------------------------
# token / line classification
# ---------------------------------------------------------------------------


def token_kind(text: str) -> str:
    """Classify a token: NUM | DASH | YEAR | DATE | PCT | TEXT."""

    cleaned = text.strip()
    if not cleaned:
        return "TEXT"
    if cleaned in _DASH_TOKENS:
        return "DASH"
    if cleaned == "%":
        return "PCT"
    if _YEAR_RE.match(cleaned):
        return "YEAR"
    if _DATE_NUMERIC_RE.match(cleaned):
        return "DATE"
    if _NUMERIC_RE.match(cleaned.replace(" ", "")):
        return "NUM"
    return "TEXT"


def _is_numeric_value_token(kind: str) -> bool:
    return kind in {"NUM", "DASH"}


_STATEMENT_TITLE_RE = re.compile(
    r"income statement|statement of|balance sheet|financial position|cash flows?|"
    r"comprehensive income|changes in equity|profit or loss|statements? of",
    re.I,
)
_ENTITY_WORD_RE = re.compile(r"\b(group|company|bank|consolidated|separate)\b", re.I)
# Maximum horizontal gap (points) between a number and the following word for the pair to be
# read as prose ("Act No. 07 of 2007").  Values in a column to the LEFT of the label zone are
# separated from the label by a clear column gutter and must stay numeric.
_PROSE_GAP_MAX = 9.0


def _effective_kinds(tokens: tuple[TokenIR, ...]) -> list[str]:
    """Token kinds after header-aware corrections.

    * A day number directly followed by a month word (``30 June``) is a DAY, not a value.
    * Short bare numbers preceding the first text token (``5.1 Revenue``) are label numbering.
    """

    kinds = [token_kind(t.text) for t in tokens]
    for i, kind in enumerate(kinds):
        if (
            kind == "NUM"
            and i + 1 < len(tokens)
            and _MONTH_RE.match(tokens[i + 1].text)
            and re.fullmatch(r"\d{1,2}", tokens[i].text.strip())
        ):
            kinds[i] = "DAY"
            continue
        if kind in {"NUM", "YEAR"} and i + 1 < len(tokens):
            follower = tokens[i + 1].text.strip()
            gap = tokens[i + 1].bbox.x0 - tokens[i].bbox.x1
            if (
                kinds[i + 1] == "TEXT"
                and gap <= _PROSE_GAP_MAX  # a value column left of the label sits further away
                and re.fullmatch(r"[A-Za-z][A-Za-z'-]*[.,;:]?", follower)
                and not _ANNOTATION_RE.match(follower)
                and not _HEADER_CUE_RE.search(follower)
                and not _UNIT_WORD_RE.match(follower)
            ):
                # "Act No. 07 of 2007", "14 John Keells ..." - a number embedded in prose.
                kinds[i] = "INLINE"
    first_text = next((i for i, k in enumerate(kinds) if k == "TEXT"), None)
    if first_text is not None and first_text > 0:
        leading = kinds[:first_text]
        adjacent = tokens[first_text].bbox.x0 - tokens[first_text - 1].bbox.x1 <= 12.0
        if (
            adjacent
            and all(k == "NUM" for k in leading)
            and all(re.fullmatch(r"\d{1,2}(?:\.\d{1,2})*", tokens[i].text.strip()) for i in range(first_text))
        ):
            for i in range(first_text):
                kinds[i] = "LABELNUM"
    return kinds


def _classify_line(line: LineIR) -> _Row:
    row = _Row(line=line)
    kinds = _effective_kinds(line.tokens)
    value_kinds = [k for k in kinds if k in {"NUM", "DASH"}]
    header_like = [k for k in kinds if k in {"YEAR", "DATE", "DAY"}]
    texts = [t.text for t, k in zip(line.tokens, kinds, strict=False) if k in {"TEXT", "LABELNUM", "INLINE"}]
    lower_text = line.text.lower()

    if _STATEMENT_TITLE_RE.search(lower_text) and all(
        re.fullmatch(r"\d{1,3}", t.text.strip()) for t, k in zip(line.tokens, kinds, strict=False) if k == "NUM"
    ):
        # Statement title (optionally followed by a page number).
        row.kind = "text"
        return row
    # A line whose numeric content is years/dates only is a header line.
    if (
        header_like
        and not [k for k in kinds if k == "NUM"]
        and (len(texts) <= 9 or (_HEADER_CUE_RE.search(lower_text) and not lower_text.rstrip().endswith(".")))
    ):
        row.kind = "header"
        return row
    if value_kinds:
        # Body row: values + label. Bare years inside a value row are values.
        for token, kind in zip(line.tokens, kinds, strict=False):
            if kind in {"NUM", "DASH", "YEAR", "DATE", "PCT"}:
                row.numeric_tokens.append(token)
            else:
                row.label_tokens.append(token)
        if not row.label_tokens and all(token_kind(t.text) == "DASH" for t in row.numeric_tokens):
            row.kind = "text"
        elif not row.label_tokens and len(row.numeric_tokens) == 1 and re.fullmatch(
            r"\d{1,3}", row.numeric_tokens[0].text.strip()
        ):
            row.kind = "text"  # bare page number
        else:
            row.kind = "body"
        return row
    if texts and all(_UNIT_PHRASE_RE.match(t) or _UNIT_WORD_RE.match(t) for t in texts):
        row.kind = "unit"
        return row
    entity_words = _ENTITY_WORD_RE.findall(lower_text)
    other_words = [w for w in re.findall(r"[a-z]+", lower_text) if w not in {"group", "company", "bank", "consolidated", "separate", "the"}]
    if _HEADER_CUE_RE.search(lower_text) and (
        _ANNOTATION_RE.search(lower_text)
        or (entity_words and len(other_words) <= 2)
        or re.search(r"\b(?:quarter|months?|year|period)\s+(?:ended|ending|to)\b", lower_text)
        or re.search(r"\bas at\b", lower_text)
        or re.search(r"^\s*notes?\s*$", lower_text)
        or re.search(r"\bchange\b", lower_text)
    ):
        row.kind = "header_cue"
        return row
    row.kind = "text"
    return row


# ---------------------------------------------------------------------------
# table segmentation
# ---------------------------------------------------------------------------


def reconstruct_page_tables(page: PageIR) -> list[TableIR]:
    if not page.lines:
        return []
    rows = [_classify_line(line) for line in page.lines]
    segments = _segment_tables(rows)
    tables: list[TableIR] = []
    for seg in segments:
        table = _build_table(page, rows, seg)
        if table is not None:
            tables.append(table)
    return tables


@dataclass
class _Segment:
    title_idx: list[int] = field(default_factory=list)
    header_idx: list[int] = field(default_factory=list)
    body_idx: list[int] = field(default_factory=list)  # includes in-body text / unit lines
    footer_idx: list[int] = field(default_factory=list)


def _segment_tables(rows: list[_Row]) -> list[_Segment]:
    """Split a page into table segments at header regions that follow body rows."""

    segments: list[_Segment] = []
    current = _Segment()
    i = 0
    n = len(rows)
    while i < n:
        row = rows[i]
        if row.kind in {"header", "header_cue", "unit", "text"} and not current.body_idx:
            # Still in the pre-body region of the current table.
            if row.kind in {"header", "header_cue"}:
                current.header_idx.append(i)
            elif current.header_idx:
                # unit/text lines inside the header block stay with the header.
                current.header_idx.append(i)
            else:
                current.title_idx.append(i)
            i += 1
            continue
        if row.kind == "body":
            current.body_idx.append(i)
            i += 1
            continue
        # Non-body line after body rows: look ahead over the run of non-body lines.
        j = i
        run: list[int] = []
        while j < n and rows[j].kind != "body":
            run.append(j)
            j += 1
        has_period_header = any(rows[k].kind == "header" for k in run)
        if has_period_header and j < n:
            # New table starts: preceding text lines are title/footer split at first header/cue.
            first_header = next(k for k in run if rows[k].kind in {"header", "header_cue"})
            # Text lines immediately before the header are the new title; earlier ones footer.
            footer: list[int] = []
            title: list[int] = []
            for k in run:
                if k < first_header:
                    title.append(k)
                else:
                    break
            # Title lines directly preceding the header; anything before a blank gap is footer.
            # Heuristic: keep at most 4 title lines, the rest are footer of the previous table.
            if len(title) > 4:
                footer = title[:-4]
                title = title[-4:]
            current.footer_idx.extend(footer)
            segments.append(current)
            current = _Segment(title_idx=title)
            for k in run:
                if k >= first_header:
                    current.header_idx.append(k)
            i = j
            continue
        if j >= n:
            # Trailing non-body lines: footer of the current table.
            current.footer_idx.extend(run)
            i = j
            continue
        # In-body text/unit lines (section headers, multi-line labels, unit-only rows).
        current.body_idx.extend(run)
        i = j
    segments.append(current)
    kept: list[_Segment] = []
    for seg in segments:
        body_rows = [i for i in seg.body_idx if rows[i].kind == "body"]
        if not body_rows:
            continue
        if len(body_rows) == 1 and not seg.header_idx:
            continue  # a lone numeric line (page number, footnote) is not a table
        kept.append(seg)
    return kept


# ---------------------------------------------------------------------------
# column detection and cell binding
# ---------------------------------------------------------------------------


def _cluster_right_edges(values: list[float], eps: float) -> list[list[float]]:
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= eps:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return clusters


def _column_eps(page_width: float) -> float:
    return max(6.0, page_width * 0.011)


def _merge_weak_clusters(clusters: list[list[float]], eps: float) -> list[list[float]]:
    """Merge single-token clusters into a close neighbour; drop isolated strays."""

    if len(clusters) <= 1:
        return clusters
    merged: list[list[float]] = []
    for cluster in clusters:
        if merged and (len(cluster) == 1 or len(merged[-1]) == 1):
            gap = min(cluster) - max(merged[-1])
            if gap <= eps * 2.5:
                merged[-1] = merged[-1] + cluster
                continue
        merged.append(cluster)
    strong = [c for c in merged if len(c) >= 2]
    return strong or merged


def _build_table(page: PageIR, rows: list[_Row], seg: _Segment) -> TableIR | None:
    body_rows = [rows[i] for i in seg.body_idx if rows[i].kind == "body"]
    if not body_rows:
        return None
    eps = _column_eps(page.width)
    right_edges: list[float] = []
    for row in body_rows:
        for token in row.numeric_tokens:
            if token_kind(token.text) in {"PCT", "DASH"}:
                continue  # dashes/percent signs are bound afterwards, never define columns
            right_edges.append(token.bbox.x1)
    clusters = _cluster_right_edges(right_edges, eps)
    if not clusters and body_rows:
        # Dash-only table (all blanks): keep dash geometry as columns.
        clusters = _cluster_right_edges(
            [t.bbox.x1 for row in body_rows for t in row.numeric_tokens if token_kind(t.text) == "DASH"],
            eps,
        )
    if not clusters:
        return None
    clusters = _merge_weak_clusters(clusters, eps)
    centres = [sum(c) / len(c) for c in clusters]
    # Build stable intervals: boundaries at midpoints between neighbouring centres.
    bounds: list[tuple[float, float]] = []
    for idx, centre in enumerate(centres):
        left = (centres[idx - 1] + centre) / 2 if idx > 0 else centre - _typical_width(clusters[idx], body_rows, centre, eps)
        right = (centre + centres[idx + 1]) / 2 if idx + 1 < len(centres) else centre + eps * 2
        bounds.append((left, right))

    # Assign numeric tokens to columns by right edge nearest centre within interval.
    cells: list[TableCellIR] = []
    cell_count = [0] * len(centres)
    pct_hits = [0] * len(centres)
    small_int_hits = [0] * len(centres)
    row_line_ids: dict[int, tuple[str, ...]] = {}
    label_x0: list[float] = []
    label_x1: list[float] = []
    body_row_indices: list[int] = []
    [i for i in seg.body_idx if rows[i].kind == "body"]
    pending_prefix: list[str] = []
    pending_ids: list[str] = []
    unit_lines: list[UnitLineIR] = []
    header_rows: list[int] = []
    for i in seg.body_idx:
        row = rows[i]
        if row.kind == "unit":
            phrases = tuple(
                HeaderPhraseIR(row_idx=i, text=t.text, bbox=t.bbox, kind="UNIT") for t in row.line.tokens
            )
            unit_lines.append(UnitLineIR(row_idx=i, text=row.line.text, bbox=row.line.bbox, phrases=phrases))
            continue
        if row.kind != "body":
            # Label-only line: candidate continuation prefix for the next body row.
            text = row.line.text.strip()
            if text and not _SECTION_END_RE.search(text) and row.kind == "text":
                pending_prefix.append(text)
                pending_ids.append(row.line.line_id)
            else:
                pending_prefix.clear()
                pending_ids.clear()
            continue
        # Geometric re-binding: a numeric-looking token that was read as label numbering but whose
        # right edge sits on an established value column is a cell of that column (tables that
        # place audited annual columns to the LEFT of the label zone).
        label_tokens = list(row.label_tokens)
        numeric_tokens = list(row.numeric_tokens)
        for t in row.label_tokens:
            if token_kind(t.text) != "NUM":
                continue
            col = _nearest_column(t.bbox.x1, centres, bounds)
            if col is not None and abs(t.bbox.x1 - centres[col]) <= eps and len(clusters[col]) >= 3:
                label_tokens.remove(t)
                numeric_tokens.append(t)
        label = " ".join(t.text for t in label_tokens).strip()
        merged_ids = [row.line.line_id]
        # Chain multi-line labels backwards while each piece reads as a continuation.
        k = len(pending_prefix) - 1
        while k >= 0 and _continuation_like(label, pending_prefix[k]):
            label = f"{pending_prefix[k]} {label}".strip()
            merged_ids.insert(0, pending_ids[k])
            k -= 1
        pending_prefix.clear()
        pending_ids.clear()
        row_line_ids[i] = tuple(merged_ids)
        body_row_indices.append(i)
        for t in label_tokens:
            label_x0.append(t.bbox.x0)
            label_x1.append(t.bbox.x1)
        cells.append(TableCellIR(row_idx=i, col_idx=0, raw_text=label, bbox=row.line.bbox))
        for token in numeric_tokens:
            kind = token_kind(token.text)
            if kind == "PCT":
                # Attach to nearest column on the left (percent suffix).
                col = _nearest_column(token.bbox.x0, centres, bounds, prefer_left=True)
                if col is not None:
                    pct_hits[col] += 1
                continue
            if kind == "DASH":
                col = _nearest_column(token.bbox.x1, centres, bounds, tolerance=eps * 3)
                if col is None:
                    col = _nearest_column(token.bbox.center_x, centres, bounds, tolerance=eps * 3)
            else:
                col = _nearest_column(token.bbox.x1, centres, bounds)
            if col is None:
                continue
            cell_count[col] += 1
            if kind == "NUM" and re.fullmatch(r"\d{1,2}(?:\.\d)?", token.text.strip()):
                small_int_hits[col] += 1
            if token.text.strip().endswith("%"):
                pct_hits[col] += 1
            cells.append(
                TableCellIR(row_idx=i, col_idx=col + 1, raw_text=token.text, bbox=token.bbox)
            )
    if not cells:
        return None
    # Column kinds.
    header_phrases = _header_phrases(rows, seg.header_idx)
    columns: list[TableColumnIR] = []
    label_zone = (min(label_x0), max(label_x1)) if label_x0 else None
    columns.append(
        TableColumnIR(
            col_idx=0,
            x_center=(label_zone[0] + label_zone[1]) / 2 if label_zone else 0.0,
            x_min=label_zone[0] if label_zone else 0.0,
            x_max=label_zone[1] if label_zone else 0.0,
            kind="LABEL",
            cell_count=len(body_row_indices),
        )
    )
    n_body = max(1, len(body_row_indices))
    for idx, centre in enumerate(centres):
        kind = "VALUE"
        bound_headers = [p for p in header_phrases if bounds[idx][0] <= p.bbox.center_x <= bounds[idx][1]]
        bound_kinds = {p.kind for p in bound_headers}
        if "NOTE" in bound_kinds and cell_count[idx] <= n_body:
            kind = "NOTE"
        elif (
            "CHANGE" in bound_kinds
            or any(p.kind == "UNIT" and p.text.strip() == "%" for p in bound_headers)
            or (cell_count[idx] and pct_hits[idx] >= max(1, cell_count[idx] // 2))
        ):
            kind = "PERCENT"
        elif (
            cell_count[idx]
            and small_int_hits[idx] == cell_count[idx]
            and len(centres) > 2
            and any(cell_count[j] and small_int_hits[j] < cell_count[j] for j in range(len(centres)) if j != idx)
        ):
            # Every cell is a 1-2 digit integer while other columns carry real amounts.
            kind = "NOTE"
        columns.append(
            TableColumnIR(
                col_idx=idx + 1,
                x_center=centre,
                x_min=bounds[idx][0],
                x_max=bounds[idx][1],
                kind=kind,
                cell_count=cell_count[idx],
            )
        )
    for i in seg.header_idx:
        header_rows.append(i)
    caption_phrases: list[HeaderPhraseIR] = []
    column_header_phrases: list[HeaderPhraseIR] = []
    first_value_left = bounds[0][0]
    for phrase in header_phrases:
        if label_zone is not None and phrase.bbox.x1 <= first_value_left and phrase.bbox.center_x < first_value_left:
            caption_phrases.append(phrase)
        else:
            column_header_phrases.append(phrase)
    title_texts = tuple(rows[i].line.text.strip() for i in seg.title_idx if rows[i].line.text.strip())
    footer_texts = tuple(rows[i].line.text.strip() for i in seg.footer_idx if rows[i].line.text.strip())
    all_idx = [*seg.title_idx, *seg.header_idx, *seg.body_idx, *seg.footer_idx]
    y0 = min(rows[i].line.bbox.y0 for i in all_idx)
    y1 = max(rows[i].line.bbox.y1 for i in all_idx)
    return TableIR(
        page_number=page.page_number,
        bbox=BBox(0.0, y0, page.width, y1),
        cells=tuple(cells),
        header_rows=tuple(header_rows),
        source_method="geometry_intervals",
        columns=tuple(columns),
        header_phrases=tuple(column_header_phrases),
        title_texts=title_texts,
        caption_phrases=tuple(caption_phrases),
        unit_lines=tuple(unit_lines),
        footer_texts=footer_texts,
        row_line_ids=row_line_ids,
        label_zone=label_zone,
    )


def _typical_width(cluster: list[float], body_rows: list[_Row], centre: float, eps: float) -> float:
    widths: list[float] = []
    for row in body_rows:
        for token in row.numeric_tokens:
            if abs(token.bbox.x1 - centre) <= eps:
                widths.append(token.bbox.x1 - token.bbox.x0)
    if not widths:
        return eps * 4
    return max(widths) + eps


def _nearest_column(
    x: float,
    centres: list[float],
    bounds: list[tuple[float, float]],
    *,
    prefer_left: bool = False,
    tolerance: float | None = None,
) -> int | None:
    best: int | None = None
    best_dist = float("inf")
    for idx, centre in enumerate(centres):
        left, right = bounds[idx]
        if prefer_left:
            if centre <= x + 2 and (x - centre) < best_dist:
                best, best_dist = idx, x - centre
            continue
        dist = abs(x - centre)
        if tolerance is None and left <= x <= right:
            return idx
        if dist < best_dist:
            best, best_dist = idx, dist
    if prefer_left:
        return best
    if best is None:
        return None
    if tolerance is not None:
        return best if best_dist <= tolerance else None
    # Outside every interval: only accept when reasonably close to a centre.
    if best_dist <= (bounds[best][1] - bounds[best][0]):
        return best
    return None


def _continuation_like(label: str, previous: str) -> bool:
    if not label:
        return False
    first = label[0]
    if first.islower() or first in "-–—(":
        return True
    return bool(previous and previous[-1:] in {",", "/", "&"})


def _header_phrases(rows: list[_Row], header_idx: list[int]) -> list[HeaderPhraseIR]:
    """Split header lines into geometric phrases (tokens separated by wide gaps)."""

    phrases: list[HeaderPhraseIR] = []
    for i in header_idx:
        row = rows[i]
        if row.kind == "unit":
            for token in row.line.tokens:
                phrases.append(HeaderPhraseIR(row_idx=i, text=token.text, bbox=token.bbox, kind="UNIT"))
            continue
        for text, bbox in _split_phrases(row.line.tokens):
            phrases.append(HeaderPhraseIR(row_idx=i, text=text, bbox=bbox, kind=_phrase_kind(text)))
    return phrases


def _split_phrases(tokens: tuple[TokenIR, ...]) -> list[tuple[str, BBox]]:
    if not tokens:
        return []
    heights = [t.bbox.y1 - t.bbox.y0 for t in tokens]
    typical = sorted(heights)[len(heights) // 2] or 8.0
    gap_limit = max(typical * 1.2, 9.0)
    kinds = _effective_kinds(tokens)
    groups: list[list[TokenIR]] = [[tokens[0]]]
    for idx, (prev, token) in enumerate(itertools.pairwise(tokens), start=1):
        gap = token.bbox.x0 - prev.bbox.x1
        prev_kind = kinds[idx - 1]
        cur_kind = kinds[idx]
        # Years / dates are always separate phrases unless glued in a long-form date.
        boundary = gap > gap_limit
        if cur_kind in {"YEAR", "DATE"} or prev_kind in {"YEAR", "DATE"}:
            boundary = True
        if cur_kind == "YEAR" and _MONTH_RE.match(prev.text):
            boundary = False
        if boundary:
            groups.append([token])
        else:
            groups[-1].append(token)
    # Two duration cues glued together ("Six months ended Quarter ended") are two phrases.
    kind_of = {id(t): k for t, k in zip(tokens, kinds, strict=False)}
    split_groups: list[list[TokenIR]] = []
    for group in groups:
        current: list[TokenIR] = []
        for pos, token in enumerate(group):
            current.append(token)
            nxt = group[pos + 1] if pos + 1 < len(group) else None
            if (
                nxt is not None
                and re.fullmatch(r"(?:ended|ending)[,.]?", token.text.strip(), re.I)
                and kind_of.get(id(nxt)) not in {"DAY", "DATE", "YEAR", "NUM"}
                and not _MONTH_RE.match(nxt.text)
            ):
                split_groups.append(current)
                current = []
        if current:
            split_groups.append(current)
    groups = split_groups
    out: list[tuple[str, BBox]] = []
    for group in groups:
        text = " ".join(t.text for t in group).strip()
        bbox = BBox(
            min(t.bbox.x0 for t in group),
            min(t.bbox.y0 for t in group),
            max(t.bbox.x1 for t in group),
            max(t.bbox.y1 for t in group),
        )
        out.append((text, bbox))
    return out


def _phrase_kind(text: str) -> str:
    lower = text.strip().lower()
    if not lower:
        return "TEXT"
    if _ANNOTATION_RE.match(lower):
        return "ANNOTATION"
    if _UNIT_PHRASE_RE.match(lower):
        return "UNIT"
    if re.fullmatch(r"\(?notes?\)?", lower):
        return "NOTE"
    if lower in {"%", "change", "% change", "change %", "variance", "var %", "var"} or re.fullmatch(
        r"(?:%\s*)?change(?:\s*%)?", lower
    ):
        return "CHANGE"
    kind = token_kind(text)
    if kind == "YEAR":
        return "YEAR"
    if kind == "DATE":
        return "DATE"
    if _DAY_MONTH_PHRASE_RE.match(lower):
        return "DAYMONTH"
    if re.search(r"\b(?:19|20)\d{2}\b", lower) and re.search(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", lower
    ):
        if re.search(r"\b(?:months?|quarter|year|period)\b|\bended\b|\bas at\b", lower):
            return "DURATION"
        return "DATE"
    if re.search(r"\b(?:three|six|nine|twelve|\d{1,2})\s+months?\b|\bquarter\b|\byear\s+(?:ended|ending|to)\b|"
                 r"\bperiod\s+(?:ended|ending)\b|\bas\s+at\b|\bmonths?\s+(?:ended|ending|to)\b", lower):
        return "DURATION"
    # A bare duration noun on its own header row ("Period" / "Year" above an "ended" row) is a
    # duration block phrase too; "Period" alone carries no month count (stays unknown).
    if re.fullmatch(r"(?:for\s+the\s+)?(?:period|year|half[\s-]?year|quarter)", lower):
        return "DURATION"
    if re.search(r"\b(group|company|bank|consolidated|separate)\b", lower):
        return "ENTITY"
    return "TEXT"


__all__ = [
    "reconstruct_page_tables",
    "reconstruct_tables",
    "token_kind",
]
