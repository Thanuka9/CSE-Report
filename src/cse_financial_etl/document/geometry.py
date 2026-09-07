"""Geometry helpers for row clustering, column banding, and proximity."""

from __future__ import annotations

from cse_financial_etl.document.document_ir import BBox, LineIR, TokenIR


def bbox_union(boxes: list[BBox]) -> BBox:
    return BBox(
        min(b.x0 for b in boxes),
        min(b.y0 for b in boxes),
        max(b.x1 for b in boxes),
        max(b.y1 for b in boxes),
    )


def horizontal_overlap(a: BBox, b: BBox) -> float:
    left = max(a.x0, b.x0)
    right = min(a.x1, b.x1)
    return max(0.0, right - left)


def vertical_distance(a: BBox, b: BBox) -> float:
    if a.y1 < b.y0:
        return b.y0 - a.y1
    if b.y1 < a.y0:
        return a.y0 - b.y1
    return 0.0


def cluster_tokens_into_rows(
    tokens: list[TokenIR], *, tolerance: float = 3.0
) -> list[list[TokenIR]]:
    rows: list[list[TokenIR]] = []
    centres: list[float] = []
    for token in sorted(tokens, key=lambda t: (t.bbox.center_y, t.bbox.x0)):
        best_i: int | None = None
        best_d = float("inf")
        for index in range(max(0, len(rows) - 4), len(rows)):
            distance = abs(token.bbox.center_y - centres[index])
            tol = max(tolerance, min(token.bbox.y1 - token.bbox.y0, 12.0) * 0.28)
            if distance <= tol and distance < best_d:
                best_i = index
                best_d = distance
        if best_i is None:
            rows.append([token])
            centres.append(token.bbox.center_y)
        else:
            rows[best_i].append(token)
            centres[best_i] = sum(t.bbox.center_y for t in rows[best_i]) / len(rows[best_i])
    return [sorted(row, key=lambda t: t.bbox.x0) for row in rows]


def line_label_and_numerics(line: LineIR) -> tuple[str, list[TokenIR]]:
    numerics = [t for t in line.tokens if _is_numeric(t.text)]
    label_tokens = [t for t in line.tokens if not _is_numeric(t.text)]
    return " ".join(t.text for t in label_tokens).strip(), numerics


def _is_numeric(text: str) -> bool:
    cleaned = text.replace(" ", "").replace(",", "")
    if cleaned in {"-", "–", "—"}:
        return True
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1]
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    if not cleaned:
        return False
    try:
        float(cleaned.replace(",", ""))
        return True
    except ValueError:
        return False
