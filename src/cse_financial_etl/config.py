from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cse_financial_etl import __version__


@dataclass(frozen=True, slots=True)
class AppConfig:
    auto_approve_threshold: float = 0.95
    manual_review_threshold: float = 0.80
    ocr_enabled: bool = True
    use_transformer: bool = False
    semantic_model: str = "rapidfuzz-token-set"
    max_file_bytes: int = 50 * 1024 * 1024
    http_timeout_seconds: int = 30
    http_max_retries: int = 3
    balance_sheet_relative: float = 0.005
    keep_review_diagnostics: bool = True


@dataclass(frozen=True, slots=True)
class IssuerProfile:
    issuer_id: str
    legal_name: str
    issuer_type: str
    standalone_scope_label: str


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def load_app_config(project_root: Path) -> AppConfig:
    payload = load_yaml(project_root / "configs" / "app.yml")
    extraction = payload.get("extraction") or {}
    http = payload.get("http") or {}
    validation = load_yaml(project_root / "configs" / "validation_rules.yml")
    thresholds = validation.get("thresholds") or {}
    tolerances = validation.get("tolerances") or {}
    return AppConfig(
        auto_approve_threshold=float(
            thresholds.get("auto_approve", extraction.get("auto_approve_threshold", 0.95))
        ),
        manual_review_threshold=float(
            thresholds.get("manual_review", extraction.get("manual_review_threshold", 0.80))
        ),
        ocr_enabled=bool(extraction.get("ocr_enabled", True)),
        use_transformer=bool(extraction.get("use_transformer", False)),
        semantic_model=str(extraction.get("semantic_model", "rapidfuzz-token-set")),
        max_file_bytes=int(http.get("max_file_bytes", 50 * 1024 * 1024)),
        http_timeout_seconds=int(http.get("timeout_seconds", 30)),
        http_max_retries=int(http.get("max_retries", 3)),
        balance_sheet_relative=float(tolerances.get("balance_sheet_relative", 0.005)),
        keep_review_diagnostics=bool(extraction.get("keep_review_diagnostics", True)),
    )


def load_metric_catalog(project_root: Path) -> dict[str, Any]:
    return load_yaml(project_root / "configs" / "metric_catalog.yml")


def load_unit_pattern_config(project_root: Path) -> dict[str, Any]:
    return load_yaml(project_root / "configs" / "unit_patterns.yml")


def load_coverage_baseline(project_root: Path) -> dict[str, Any]:
    return load_yaml(project_root / "configs" / "coverage_baseline.yml")


def load_issuers(project_root: Path) -> dict[str, IssuerProfile]:
    payload = load_yaml(project_root / "configs" / "issuers.yml")
    profiles: dict[str, IssuerProfile] = {}
    for issuer_id, raw in (payload.get("issuers") or {}).items():
        legal_name = str(raw.get("legal_name") or issuer_id).strip()
        profile = IssuerProfile(
            issuer_id=str(issuer_id),
            legal_name=legal_name,
            issuer_type=str(raw.get("issuer_type") or "GENERAL"),
            standalone_scope_label=str(raw.get("standalone_scope_label") or "COMPANY"),
        )
        profiles[legal_name.casefold()] = profile
    return profiles


def config_hash(project_root: Path) -> str:
    hasher = hashlib.sha256()
    config_dir = project_root / "configs"
    if config_dir.exists():
        for path in sorted(config_dir.glob("*.yml")):
            hasher.update(path.name.encode("utf-8"))
            hasher.update(path.read_bytes())
    return hasher.hexdigest()[:16]


def code_version() -> str:
    return __version__


def infer_issuer_type(issuer_name: str) -> str:
    upper = issuer_name.upper()
    if re_search_bank(upper):
        return "BANK"
    if any(token in upper for token in ("INSURANCE", "LIFE ASSURANCE", "ASSURANCE PLC", "TAKAFUL")):
        return "INSURANCE"
    if any(token in upper for token in ("FINANCE", "LEASING", "MICROFINANCE")):
        return "FINANCE_COMPANY"
    return "GENERAL"


def infer_entity_scope(issuer_name: str, issuers: dict[str, IssuerProfile] | None = None) -> str:
    if issuers:
        profile = issuers.get(issuer_name.casefold())
        if profile is not None:
            return profile.standalone_scope_label
    return "BANK" if infer_issuer_type(issuer_name) == "BANK" else "COMPANY"


def re_search_bank(upper_name: str) -> bool:
    return "BANK" in upper_name and "FOOD" not in upper_name
