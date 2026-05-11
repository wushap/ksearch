from __future__ import annotations

import contextvars
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any


_SESSION = contextvars.ContextVar("ksearch_debug_session", default=None)
_REDACT_KEYS = {"token", "api_key", "password", "secret"}
_PREVIEW_LIMITS = {
    "content_preview": 500,
    "prompt_preview": 1000,
    "response_preview": 1000,
}
_RESERVED_CONTEXT_KEYS = {"argv", "command", "cwd", "started_at"}


@dataclass
class DebugSession:
    argv: list[str]
    cwd: str
    command: str
    started_at: float
    started_at_iso: str
    debug_dir: Path
    logger: logging.Logger
    context: dict[str, Any] = field(default_factory=dict)
    finished: bool = False


def _debug_root() -> Path:
    return Path("~/.ksearch/debug").expanduser()


def _truncate_value(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    limit = _PREVIEW_LIMITS.get(key)
    if limit is None or len(value) <= limit:
        return value
    return value[:limit] + "..."


def _sanitize(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in _REDACT_KEYS:
                cleaned[key] = "***REDACTED***"
            else:
                cleaned[key] = _sanitize(item, lowered)
        return cleaned
    if isinstance(value, list):
        return [_sanitize(item, parent_key) for item in value]
    return _truncate_value(parent_key, value)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _filter_reserved_context(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in _RESERVED_CONTEXT_KEYS}


def _merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def _create_debug_dir() -> Path:
    timestamp = datetime.now().strftime("cli-%Y%m%d-%H%M%S")
    debug_root = _debug_root()

    for index in range(1000):
        suffix = "" if index == 0 else f"-{index}"
        debug_dir = debug_root / f"{timestamp}{suffix}"
        try:
            debug_dir.mkdir(parents=True, exist_ok=False)
            return debug_dir
        except FileExistsError:
            continue

    raise RuntimeError(f"unable to create debug directory under {debug_root}")


def _close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _active_session() -> DebugSession | None:
    session = _SESSION.get()
    if session is None or session.finished:
        return None
    return session


def _error_payload(error: Any) -> dict[str, Any]:
    if isinstance(error, dict):
        return _sanitize(error)

    if isinstance(error, BaseException):
        payload = {"type": error.__class__.__name__}
        message = str(error)
        if message:
            payload["message"] = message

        exit_code = getattr(error, "exit_code", None)
        if exit_code is None:
            exit_code = getattr(error, "code", None)
        if exit_code is not None:
            payload["exit_code"] = exit_code
        return payload

    if error is None:
        return {}

    return {"message": str(error)}


def start_debug_session(*, argv: list[str], cwd: str, command: str) -> DebugSession:
    active_session = _SESSION.get()
    if active_session is not None and not active_session.finished:
        raise RuntimeError("debug session already active")

    debug_dir = _create_debug_dir()
    try:
        session_logger = logging.getLogger(f"ksearch.debug.{debug_dir.name}")
        session_logger.setLevel(logging.DEBUG)
        _close_logger(session_logger)
        handler = logging.FileHandler(debug_dir / "session.log", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        session_logger.addHandler(handler)
        session_logger.propagate = False
    except Exception:
        shutil.rmtree(debug_dir)
        raise

    session = DebugSession(
        argv=list(argv),
        cwd=cwd,
        command=command,
        started_at=time.time(),
        started_at_iso=datetime.now().isoformat(),
        debug_dir=debug_dir,
        logger=session_logger,
    )
    _SESSION.set(session)
    session_logger.info("debug session started")
    return session


def write_context(payload: dict[str, Any]) -> None:
    session = _active_session()
    if session is None:
        return
    session.context = _merge_dicts(
        session.context,
        _sanitize(_filter_reserved_context(payload)),
    )
    context = {
        "argv": session.argv,
        "command": session.command,
        "cwd": session.cwd,
        "started_at": session.started_at_iso,
        **session.context,
    }
    with (session.debug_dir / "context.json").open("w", encoding="utf-8") as handle:
        json.dump(context, handle, indent=2, ensure_ascii=False)


def log_event(
    component: str,
    event: str,
    data: dict[str, Any] | None = None,
    level: str = "DEBUG",
) -> None:
    session = _active_session()
    if session is None:
        return
    sanitized = _sanitize(data or {})
    payload = {
        "ts": datetime.now().isoformat(),
        "level": level,
        "component": component,
        "event": event,
        "command": session.command,
        "elapsed_ms": int((time.time() - session.started_at) * 1000),
        "data": sanitized,
    }
    _append_jsonl(session.debug_dir / "events.jsonl", payload)
    session.logger.log(getattr(logging, level), f"{component} {event} {sanitized}")


def _command_component(command: str) -> str:
    normalized = command.replace(" ", ".")
    return f"ksearch.cli.{normalized}"


def _component_command(component: str) -> str:
    prefix = "ksearch.cli."
    if component.startswith(prefix):
        component = component[len(prefix) :]
    return component.replace(".", " ")


def begin_command(
    command: str,
    args: dict[str, Any],
    config_snapshot: dict[str, Any] | None = None,
) -> None:
    session = _active_session()
    if session is None:
        return

    session.command = command
    context = {"command_context": args}
    if config_snapshot is not None:
        context["config_snapshot"] = config_snapshot
    write_context(context)
    log_event(_command_component(command), "command_start", {"args": args}, level="INFO")


def complete_command(command: str, summary: dict[str, Any]) -> None:
    session = _active_session()
    if session is not None:
        session.command = command
    log_event(_command_component(command), "command_success", summary, level="INFO")
    finish_debug_session(success=True, command=command, summary=summary)


def fail_command(
    command: str,
    exc: Exception,
    summary: dict[str, Any] | None = None,
) -> None:
    session = _active_session()
    if session is not None:
        session.command = command

    error = _error_payload(exc)
    log_event(_command_component(command), "command_failure", error, level="ERROR")
    finish_debug_session(success=False, command=command, summary=summary or {}, error=error)


def finish_debug_session(
    *,
    success: bool,
    command: str,
    summary: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    session = _active_session()
    if session is None:
        return
    session.finished = True
    payload = {
        "success": success,
        "command": session.command,
        "started_at": session.started_at_iso,
        "finished_at": datetime.now().isoformat(),
        "elapsed_ms": int((time.time() - session.started_at) * 1000),
        "summary": _sanitize(summary or {}),
        "error": _sanitize(error or {}),
    }
    try:
        with (session.debug_dir / "result.json").open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        session.logger.info("debug session finished")
    finally:
        _close_logger(session.logger)
        _SESSION.set(None)


def log_command_start(
    component: str,
    *,
    config_snapshot: dict[str, Any] | None = None,
    command_context: dict[str, Any] | None = None,
) -> None:
    begin_command(
        _component_command(component),
        command_context or {},
        config_snapshot=config_snapshot,
    )


def log_command_success(
    component: str,
    *,
    summary: dict[str, Any] | None = None,
    context_updates: dict[str, Any] | None = None,
) -> None:
    if context_updates:
        write_context(context_updates)
    complete_command(_component_command(component), summary or {})


def log_command_failure(
    component: str,
    *,
    error: Any,
    summary: dict[str, Any] | None = None,
    context_updates: dict[str, Any] | None = None,
) -> None:
    if context_updates:
        write_context(context_updates)
    if isinstance(error, BaseException):
        exc = error
    else:
        exc = RuntimeError(str(error))
    fail_command(_component_command(component), exc, summary=summary)
