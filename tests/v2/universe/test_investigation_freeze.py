from __future__ import annotations

import json
from pathlib import Path

import yaml

from cse_financial_etl.v2.diagnostics.investigation_freeze import INVESTIGATION_BASE_SHA
from cse_financial_etl.v2.governance.historical_floors import HISTORICAL_MIN_DRAFT_PUBLISHABLE

ROOT = Path(__file__).resolve().parents[3]
FREEZE_PATH = ROOT / "tests" / "v2" / "universe" / "investigation_freeze.json"


def test_investigation_freeze_pins_base_sha_engine_and_floors() -> None:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    assert freeze["investigation_base_sha"] == INVESTIGATION_BASE_SHA
    assert freeze["extraction_engine"] == "v1"
    assert freeze["min_draft_publishable"] == HISTORICAL_MIN_DRAFT_PUBLISHABLE
    assert freeze["actual_code_sha"]
    assert freeze["code_sha"]
    assert "working_tree_dirty" in freeze
    assert freeze.get("branch")
    assert "config_hash" in freeze
    assert "concept_registry_hash" in freeze
    assert "issuer_master_sha256" in freeze
    assert "uv_lock_sha256" in freeze

    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    assert app["extraction"]["engine"] == "v2"
    assert app["publication"]["release_mode"] == "DRAFT"
    coverage = yaml.safe_load(
        (ROOT / "configs" / "coverage_baseline.yml").read_text(encoding="utf-8")
    )
    assert coverage["min_draft_publishable"] == HISTORICAL_MIN_DRAFT_PUBLISHABLE

    # This JSON is a historical investigation snapshot. Its hashes describe the
    # files at the recorded code SHA, not the current evolving branch. Validate
    # the snapshot's internal integrity instead of rewriting history whenever
    # current files change.
    for relative, digest in freeze["file_sha256"].items():
        assert relative
        assert isinstance(digest, str)
        assert len(digest) == 64
        int(digest, 16)

    assert freeze["uv_lock_sha256"] == freeze["file_sha256"]["uv.lock"]
    assert freeze["config_hash"] == freeze["file_sha256"]["configs/app.yml"]
    assert freeze["concept_registry_hash"] == freeze["file_sha256"][
        "src/cse_financial_etl/v2/taxonomy/registry.py"
    ]
    assert freeze["source_snapshot_id"] == freeze["file_sha256"][
        "tests/v2/universe/locked_source_manifest.json"
    ]


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
