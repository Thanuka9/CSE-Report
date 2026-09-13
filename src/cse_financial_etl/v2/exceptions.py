"""Typed V2 exceptions. Extraction failures must never be swallowed silently."""

from __future__ import annotations


class V2Error(Exception):
    """Base error for the isolated V2 engine."""


class MissingProvenanceError(V2Error):
    """A source-bearing object was constructed without a source reference."""


class ReleaseContextRequiredError(V2Error):
    """V2 publication or rendering was attempted without an explicit ReleaseContext."""


class UnauthorizedCoverageFloorReduction(V2Error):
    """A coverage floor was lowered without a complete governed acknowledgement."""


class WorkbookReconciliationFailed(V2Error):
    """Eligible release facts do not reconcile to displayed numeric workbook cells."""

    reason_code = "WORKBOOK_RECONCILIATION_FAILED"


class OcrRouteNotEnabledError(V2Error):
    """OCR/document-vision is Phase 11 and is not part of the initial native path."""


class WorkbookRendererNotEnabledError(V2Error):
    """The V2 workbook renderer is Phase 12 and is not yet the production renderer."""


class NativeParseError(V2Error):
    """PyMuPDF could not produce a deterministic CanonicalDocument."""
