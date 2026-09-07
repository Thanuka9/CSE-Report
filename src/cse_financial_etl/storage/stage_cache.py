"""File-based stage cache and atomic promote helpers (section 52)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def cache_key(
    *,
    source_sha256: str,
    stage: str,
    versions: dict[str, str],
) -> str:
    """Build a deterministic cache key from source hash + stage version vector."""

    payload = {
        "source_sha256": source_sha256,
        "stage": stage,
        "versions": {k: versions[k] for k in sorted(versions)},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def default_version_vector() -> dict[str, str]:
    from cse_financial_etl import __version__

    return {
        "package": __version__,
        "ontology": "r2",
        "equations": "r2",
        "unit_policy": "r2",
        "metric_policy": "r2",
        "text_normalization": "r2",
        "fiscal_context": "r2",
    }


class StageCache:
    """Directory-backed cache for intermediate compiler artifacts."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str, name: str = "payload.json") -> Path:
        return self.root / key[:2] / key / name

    def get_json(self, key: str, name: str = "payload.json") -> dict[str, Any] | None:
        path = self.path_for(key, name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put_json(self, key: str, payload: dict[str, Any], name: str = "payload.json") -> Path:
        path = self.path_for(key, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str))
        return path


def atomic_write_text(path: Path, content: str) -> None:
    """Write via temp file + os.replace (Windows-safe same-volume promote)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
