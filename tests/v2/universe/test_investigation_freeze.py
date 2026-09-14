from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from cse_financial_etl.v2.diagnostics.investigation_freeze import (
    INVESTIGATION_BASE_SHA,
    collect_investigation_freeze,
)
from cse_financial_etl.v2.governance.historical_floors import HISTORICAL_MIN_DRAFT_PUBLISHABLE

ROOT = Path(__file__).resolve().parents[3]
FREEZE_PATH = ROOT / "tests" / "v2" / "universe" / "investigation_freeze.json"


def test_investigation_freeze_pins_base_sha_engine_and_floors() -> None:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    assert freeze["investigation_base_sha"] == INVESTIGATION_BASE_SHA
    assert freeze["extraction_engine"] == "v1"
    assert freeze["min_draft_publishable"] == HISTORICAL_MIN_DRAFT_PUBLISHABLE
    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    assert app["extraction"]["engine"] == "v1"
    coverage = yaml.safe_load(
        (ROOT / "configs" / "coverage_baseline.yml").read_text(encoding="utf-8")
    )
    assert coverage["min_draft_publishable"] == HISTORICAL_MIN_DRAFT_PUBLISHABLE
    live = collect_investigation_freeze(ROOT)
    for relative, digest in freeze["file_sha256"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == digest
        assert live.file_sha256[relative] == digest


def test_source_manifest_schema_is_stable() -> None:
    from cse_financial_etl.v2.contracts.investigation import SourceManifestRow

    required = {
        "filing_version_id",
        "issuer_id",
        "symbol",
        "local_file",
        "pdf_sha256",
        "file_size",
    }
    assert required <= set(SourceManifestRow.model_fields)
