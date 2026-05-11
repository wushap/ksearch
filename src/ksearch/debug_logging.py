from __future__ import annotations

import contextvars
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


_SESSION = contextvars.ContextVar("ksearch_debug_session", default=None)
_REDACT_KEYS = {"token", "api_key", "password", "secret"}
_PREVIEW_LIMITS = {
    "content_preview": 500,
    "prompt_preview": 1000,
    "response_preview": 1000,
}


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


def reset_debug_session_for_tests() -> None:
    _SESSION.set(None)


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


def start_debug_session(*, argv: list[str], cwd: str, command: str) -> DebugSession:
    timestamp = datetime.now().strftime("cli-%Y%m%d-%H%M%S")
    debug_dir = _debug_root() / timestamp
    debug_dir.mkdir(parents=True, exist_ok=False)

    session_logger = logging.getLogger(f"ksearch.debug.{timestamp}")
    session_logger.setLevel(logging.DEBUG)
    session_logger.handlers.clear()
    handler = logging.FileHandler(debug_dir / "session.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    session_logger.addHandler(handler)
    session_logger.propagate = False

    session = DebugSession(
        argv=argv,
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
    session = _SESSION.get()
    if session is None:
        return
    session.context.update(_sanitize(payload))
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
    session = _SESSION.get()
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


def finish_debug_session(
    *,
    success: bool,
    command: str,
    summary: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    session = _SESSION.get()
    if session is None or session.finished:
        return
    session.finished = True
    payload = {
        "success": success,
        "command": command,
        "started_at": session.started_at_iso,
        "finished_at": datetime.now().isoformat(),
        "elapsed_ms": int((time.time() - session.started_at) * 1000),
        "summary": _sanitize(summary or {}),
        "error": _sanitize(error or {}),
    }
    with (session.debug_dir / "result.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    session.logger.info("debug session finished")
