from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
import traceback
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, QuarterPrice

CACHE_SCHEMA_VERSION = 1


class ProcessingTimeoutError(TimeoutError):
    """A PDF/OCR worker exceeded its hard wall-clock budget and was terminated."""


class ProcessingChildError(RuntimeError):
    """A process-isolated PDF/OCR worker exited without a usable result."""


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _source_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _stable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _stable(asdict(value))
    if isinstance(value, dict):
        return {
            str(key): _stable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, set):
        return sorted((_stable(item) for item in value), key=str)
    return repr(value)


def _cache_key(
    *,
    kind: str,
    source_sha256: str,
    issuer_name: str,
    period_end: date,
    symbols: Iterable[str],
    cache_namespace: str,
    business_options: dict[str, Any],
) -> str:
    payload = {
        "schema": CACHE_SCHEMA_VERSION,
        "kind": kind,
        "source_sha256": source_sha256,
        "issuer_name": issuer_name,
        "period_end": period_end.isoformat(),
        "symbols": list(symbols),
        "cache_namespace": cache_namespace,
        "business_options": _stable(business_options),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fact_from_json(row: dict[str, Any]) -> ExtractedFact:
    payload = dict(row)
    payload["period_end"] = date.fromisoformat(str(payload["period_end"]))
    payload["raw_value"] = (
        Decimal(str(payload["raw_value"]))
        if payload.get("raw_value") not in (None, "")
        else None
    )
    payload["normalized_value"] = (
        Decimal(str(payload["normalized_value"]))
        if payload.get("normalized_value") not in (None, "")
        else None
    )
    return ExtractedFact(**payload)


def _price_to_json(price: QuarterPrice) -> dict[str, Any]:
    payload = asdict(price)
    payload["period_end"] = price.period_end.isoformat()
    payload["value"] = str(price.value) if price.value is not None else None
    return payload


def _price_from_json(row: dict[str, Any]) -> QuarterPrice:
    payload = dict(row)
    payload["period_end"] = date.fromisoformat(str(payload["period_end"]))
    payload["value"] = (
        Decimal(str(payload["value"])) if payload.get("value") not in (None, "") else None
    )
    return QuarterPrice(**payload)


def _read_fact_cache(path: Path, source_sha256: str) -> list[ExtractedFact] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        if payload.get("source_sha256") != source_sha256:
            return None
        rows = payload.get("facts")
        if not isinstance(rows, list):
            return None
        return [_fact_from_json(row) for row in rows if isinstance(row, dict)]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _read_price_cache(path: Path, source_sha256: str) -> list[QuarterPrice] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        if payload.get("source_sha256") != source_sha256:
            return None
        rows = payload.get("prices")
        if not isinstance(rows, list):
            return None
        return [_price_from_json(row) for row in rows if isinstance(row, dict)]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _diagnostic_cache_dir(result_cache_dir: Path, cache_key: str) -> Path:
    return result_cache_dir / "diagnostics" / cache_key


def _restore_diagnostics(
    result_cache_dir: Path,
    cache_key: str,
    diagnostics_dir: Path | None,
) -> None:
    if diagnostics_dir is None:
        return
    source = _diagnostic_cache_dir(result_cache_dir, cache_key)
    if not source.exists():
        return
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    for path in source.glob("*.json"):
        shutil.copy2(path, diagnostics_dir / path.name)
    (diagnostics_dir / "resilient_cache.json").write_text(
        json.dumps({"cache_hit": True, "cache_key": cache_key}, indent=2),
        encoding="utf-8",
    )


def _snapshot_diagnostics(
    result_cache_dir: Path,
    cache_key: str,
    diagnostics_dir: Path | None,
) -> None:
    if diagnostics_dir is None or not diagnostics_dir.exists():
        return
    destination = _diagnostic_cache_dir(result_cache_dir, cache_key)
    destination.mkdir(parents=True, exist_ok=True)
    for path in diagnostics_dir.glob("*.json"):
        if path.name == "resilient_cache.json":
            continue
        shutil.copy2(path, destination / path.name)


def _configure_child(project_root: Path) -> None:
    from cse_financial_etl.config import (
        load_issuers,
        load_metric_catalog,
        load_unit_pattern_config,
    )
    from cse_financial_etl.extraction.semantic_matcher import (
        apply_metric_catalog,
        get_semantic_matcher,
    )
    from cse_financial_etl.extraction.unit_detector import configure_unit_patterns

    load_issuers(project_root)
    apply_metric_catalog(load_metric_catalog(project_root))
    configure_unit_patterns(load_unit_pattern_config(project_root))
    get_semantic_matcher.cache_clear()


def _become_process_group_leader() -> None:
    if os.name == "nt":
        return
    setsid = getattr(os, "setsid", None)
    if setsid is not None:
        with suppress(OSError):
            setsid()


def _send_child_error(send: Connection, exc: BaseException) -> None:
    with suppress(BaseException):
        send.send(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc()[-12000:],
            }
        )


def _financial_worker(
    send: Connection,
    project_root: str,
    pdf_path: str,
    issuer_name: str,
    symbol: str,
    period_end: str,
    text_cache_dir: str | None,
    kwargs: dict[str, Any],
) -> None:
    _become_process_group_leader()
    try:
        _configure_child(Path(project_root))
        from cse_financial_etl.extraction.statement_extractor import extract_filing

        facts = extract_filing(
            Path(pdf_path),
            issuer_name,
            symbol,
            date.fromisoformat(period_end),
            Path(text_cache_dir) if text_cache_dir else None,
            **kwargs,
        )
        send.send({"ok": True, "facts": [fact.as_json() for fact in facts]})
    except BaseException as exc:  # child boundary includes parser/system failures
        _send_child_error(send, exc)
    finally:
        send.close()


def _price_worker(
    send: Connection,
    pdf_path: str,
    issuer_name: str,
    symbols: list[str],
    period_end: str,
    text_cache_dir: str | None,
) -> None:
    _become_process_group_leader()
    try:
        from cse_financial_etl.extraction.statement_extractor import extract_quarter_prices

        prices = extract_quarter_prices(
            Path(pdf_path),
            issuer_name,
            symbols,
            date.fromisoformat(period_end),
            Path(text_cache_dir) if text_cache_dir else None,
        )
        send.send({"ok": True, "prices": [_price_to_json(price) for price in prices]})
    except BaseException as exc:
        _send_child_error(send, exc)
    finally:
        send.close()


def _posix_process_group_id(pid: int) -> int | None:
    getpgid = getattr(os, "getpgid", None)
    if getpgid is None:
        return None
    try:
        return int(getpgid(pid))
    except (OSError, ProcessLookupError):
        return None


def _signal_process_group(pgid: int, sig: int) -> bool:
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return False
    try:
        killpg(pgid, sig)
        return True
    except (OSError, ProcessLookupError):
        return False


def _terminate_process_tree(process: Any) -> None:
    if not getattr(process, "is_alive", lambda: False)():
        return
    pid = getattr(process, "pid", None)
    if pid is None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            process.terminate()
    else:
        pgid = _posix_process_group_id(pid)
        if pgid is None or pgid != pid or not _signal_process_group(pgid, int(signal.SIGTERM)):
            process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        if os.name == "nt":
            process.kill()
        else:
            pgid = _posix_process_group_id(pid)
            sigkill = int(getattr(signal, "SIGKILL", signal.SIGTERM))
            if pgid is None or pgid != pid or not _signal_process_group(pgid, sigkill):
                process.kill()
        process.join(timeout=5)


def _await_process_payload(
    process: Any,
    receive: Connection,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.01, timeout_seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_process_tree(process)
            raise ProcessingTimeoutError(
                f"PDF/OCR worker exceeded {timeout_seconds:.1f}s and its process tree was terminated"
            )
        if receive.poll(min(0.10, remaining)):
            try:
                payload = receive.recv()
            except EOFError as exc:
                process.join(timeout=1)
                raise ProcessingChildError(
                    f"PDF/OCR worker exited without a result (exitcode={process.exitcode})"
                ) from exc
            process.join(timeout=5)
            if process.is_alive():
                _terminate_process_tree(process)
            if not isinstance(payload, dict):
                raise ProcessingChildError("PDF/OCR worker returned a non-dict payload")
            if not payload.get("ok"):
                raise ProcessingChildError(
                    f"{payload.get('error_type', 'WorkerError')}: {payload.get('error', '')}\n"
                    f"{payload.get('traceback', '')}"
                )
            return payload
        if not process.is_alive():
            process.join(timeout=1)
            if receive.poll():
                continue
            raise ProcessingChildError(
                f"PDF/OCR worker exited without a result (exitcode={process.exitcode})"
            )


def _run_financial_isolated(
    *,
    project_root: Path,
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    text_cache_dir: Path | None,
    kwargs: dict[str, Any],
    timeout_seconds: float,
) -> list[ExtractedFact]:
    context = get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_financial_worker,
        args=(
            send,
            str(project_root),
            str(pdf_path),
            issuer_name,
            symbol,
            period_end.isoformat(),
            str(text_cache_dir) if text_cache_dir else None,
            kwargs,
        ),
        daemon=False,
    )
    process.start()
    send.close()
    try:
        payload = _await_process_payload(process, receive, timeout_seconds)
    finally:
        receive.close()
    rows = payload.get("facts")
    if not isinstance(rows, list):
        raise ProcessingChildError("PDF/OCR worker omitted fact rows")
    return [_fact_from_json(row) for row in rows if isinstance(row, dict)]


def _run_prices_isolated(
    *,
    pdf_path: Path,
    issuer_name: str,
    symbols: list[str],
    period_end: date,
    text_cache_dir: Path | None,
    timeout_seconds: float,
) -> list[QuarterPrice]:
    context = get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_price_worker,
        args=(
            send,
            str(pdf_path),
            issuer_name,
            symbols,
            period_end.isoformat(),
            str(text_cache_dir) if text_cache_dir else None,
        ),
        daemon=False,
    )
    process.start()
    send.close()
    try:
        payload = _await_process_payload(process, receive, timeout_seconds)
    finally:
        receive.close()
    rows = payload.get("prices")
    if not isinstance(rows, list):
        raise ProcessingChildError("PDF/OCR worker omitted price rows")
    return [_price_from_json(row) for row in rows if isinstance(row, dict)]


def extract_filing_resilient(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    text_cache_dir: Path | None = None,
    *,
    project_root: Path,
    result_cache_dir: Path | None,
    process_timeout_seconds: float,
    source_sha256: str | None = None,
    cache_namespace: str = "",
    **extract_kwargs: Any,
) -> list[ExtractedFact]:
    """Resume-safe financial extraction with hard process-tree cancellation.

    Successful filing results are keyed by source hash + code/config namespace + all
    accounting-relevant extraction options. A retry strategy therefore gets a different
    cache key when it changes unit/entity/period recovery flags. Diagnostics are cached
    with the result and restored into the current run directory on a cache hit.
    """

    source_sha = source_sha256 or _source_sha256(pdf_path)
    diagnostics_dir = extract_kwargs.get("diagnostics_dir")
    diagnostics_path = Path(diagnostics_dir) if diagnostics_dir is not None else None
    business_options = {
        key: value
        for key, value in extract_kwargs.items()
        if key not in {"diagnostics_dir", "text_cache_dir"}
    }
    key = _cache_key(
        kind="financial_facts",
        source_sha256=source_sha,
        issuer_name=issuer_name,
        period_end=period_end,
        symbols=[symbol],
        cache_namespace=cache_namespace,
        business_options=business_options,
    )
    cache_path = result_cache_dir / f"{key}.json" if result_cache_dir is not None else None
    if cache_path is not None:
        assert result_cache_dir is not None
        cached = _read_fact_cache(cache_path, source_sha)
        if cached is not None:
            _restore_diagnostics(result_cache_dir, key, diagnostics_path)
            return cached

    if process_timeout_seconds > 0:
        facts = _run_financial_isolated(
            project_root=project_root,
            pdf_path=pdf_path,
            issuer_name=issuer_name,
            symbol=symbol,
            period_end=period_end,
            text_cache_dir=text_cache_dir,
            kwargs=extract_kwargs,
            timeout_seconds=process_timeout_seconds,
        )
    else:
        from cse_financial_etl.extraction.statement_extractor import extract_filing

        facts = extract_filing(
            pdf_path,
            issuer_name,
            symbol,
            period_end,
            text_cache_dir,
            **extract_kwargs,
        )

    if cache_path is not None:
        assert result_cache_dir is not None
        _atomic_json(
            cache_path,
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "source_sha256": source_sha,
                "cache_key": key,
                "facts": [fact.as_json() for fact in facts],
            },
        )
        _snapshot_diagnostics(result_cache_dir, key, diagnostics_path)
    return facts


def extract_quarter_prices_resilient(
    pdf_path: Path,
    issuer_name: str,
    symbols: Iterable[str],
    period_end: date,
    text_cache_dir: Path | None = None,
    *,
    result_cache_dir: Path | None,
    process_timeout_seconds: float,
    source_sha256: str | None = None,
    cache_namespace: str = "",
) -> list[QuarterPrice]:
    """Resume-safe filing price extraction with the same hard process boundary."""

    symbol_list = list(symbols)
    source_sha = source_sha256 or _source_sha256(pdf_path)
    key = _cache_key(
        kind="quarter_prices",
        source_sha256=source_sha,
        issuer_name=issuer_name,
        period_end=period_end,
        symbols=symbol_list,
        cache_namespace=cache_namespace,
        business_options={},
    )
    cache_path = result_cache_dir / f"{key}.json" if result_cache_dir is not None else None
    if cache_path is not None:
        cached = _read_price_cache(cache_path, source_sha)
        if cached is not None:
            return cached

    if process_timeout_seconds > 0:
        prices = _run_prices_isolated(
            pdf_path=pdf_path,
            issuer_name=issuer_name,
            symbols=symbol_list,
            period_end=period_end,
            text_cache_dir=text_cache_dir,
            timeout_seconds=process_timeout_seconds,
        )
    else:
        from cse_financial_etl.extraction.statement_extractor import extract_quarter_prices

        prices = extract_quarter_prices(
            pdf_path,
            issuer_name,
            symbol_list,
            period_end,
            text_cache_dir,
        )

    if cache_path is not None:
        _atomic_json(
            cache_path,
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "source_sha256": source_sha,
                "cache_key": key,
                "prices": [_price_to_json(price) for price in prices],
            },
        )
    return prices
