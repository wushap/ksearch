import json
from datetime import datetime
from pathlib import Path

import pytest

import ksearch.debug_logging as debug_logging
from ksearch.debug_logging import finish_debug_session, log_event, start_debug_session, write_context


@pytest.fixture(autouse=True)
def cleanup_debug_session():
    session = debug_logging._SESSION.get()
    if session is not None:
        debug_logging._close_logger(session.logger)
        debug_logging._SESSION.set(None)

    yield

    session = debug_logging._SESSION.get()
    if session is not None:
        debug_logging._close_logger(session.logger)
        debug_logging._SESSION.set(None)


def test_start_debug_session_creates_expected_artifacts_and_contents(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )
    write_context({"config_snapshot": {"ollama_url": "http://localhost:11434"}})
    log_event("ksearch.cli.health", "command_start", {"argv": ["--debug", "health"]})
    finish_debug_session(success=True, command="health", summary={"result_count": 0})

    debug_root = Path(tmp_path) / ".ksearch" / "debug"
    assert session.debug_dir.parent == debug_root
    assert (session.debug_dir / "session.log").exists()
    assert (session.debug_dir / "context.json").exists()
    assert (session.debug_dir / "events.jsonl").exists()
    assert (session.debug_dir / "result.json").exists()

    context_payload = json.loads((session.debug_dir / "context.json").read_text(encoding="utf-8"))
    assert context_payload["argv"] == ["--debug", "health"]
    assert context_payload["command"] == "health"
    assert context_payload["cwd"] == "/work/tree"
    assert context_payload["config_snapshot"]["ollama_url"] == "http://localhost:11434"

    result_payload = json.loads((session.debug_dir / "result.json").read_text(encoding="utf-8"))
    assert result_payload["success"] is True
    assert result_payload["command"] == "health"
    assert result_payload["summary"] == {"result_count": 0}


def test_log_event_truncates_and_redacts_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "search", "asyncio"],
        cwd="/work/tree",
        command="search",
    )
    log_event(
        "ksearch.knowledge.reranker",
        "score_document",
        {
            "content_preview": "x" * 900,
            "api_key": "top-secret",
            "nested": {"password": "hidden", "query": "python asyncio"},
        },
    )
    finish_debug_session(success=True, command="search", summary={"result_count": 1})

    lines = (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[-1])
    assert event["data"]["content_preview"].endswith("...")
    assert len(event["data"]["content_preview"]) == 503
    assert event["data"]["api_key"] == "***REDACTED***"
    assert event["data"]["nested"]["password"] == "***REDACTED***"


def test_finished_session_rejects_further_context_and_event_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "search", "asyncio"],
        cwd="/work/tree",
        command="search",
    )
    write_context({"config_snapshot": {"ollama_url": "http://localhost:11434"}})
    log_event("ksearch.cli.search", "command_start", {"argv": ["--debug", "search", "asyncio"]})
    finish_debug_session(success=True, command="search", summary={"result_count": 1})

    context_before = (session.debug_dir / "context.json").read_text(encoding="utf-8")
    event_lines_before = (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()

    write_context({"config_snapshot": {"ollama_url": "http://example.invalid"}})
    log_event("ksearch.cli.search", "command_end", {"result_count": 1})

    assert (session.debug_dir / "context.json").read_text(encoding="utf-8") == context_before
    assert (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() == event_lines_before


def test_write_context_merges_nested_dictionaries(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )
    write_context({"config_snapshot": {"ollama_url": "http://localhost:11434"}})
    write_context({"config_snapshot": {"timeout": 30}})
    finish_debug_session(success=True, command="health", summary={"result_count": 0})

    context_payload = json.loads((session.debug_dir / "context.json").read_text(encoding="utf-8"))
    assert context_payload["config_snapshot"] == {
        "ollama_url": "http://localhost:11434",
        "timeout": 30,
    }


def test_write_context_does_not_override_reserved_session_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )
    write_context(
        {
            "argv": ["--debug", "search"],
            "command": "search",
            "cwd": "/tmp/override",
            "started_at": "1999-01-01T00:00:00",
            "config_snapshot": {"ollama_url": "http://localhost:11434"},
        }
    )
    finish_debug_session(success=True, command="health", summary={"result_count": 0})

    context_payload = json.loads((session.debug_dir / "context.json").read_text(encoding="utf-8"))
    assert context_payload["argv"] == ["--debug", "health"]
    assert context_payload["command"] == "health"
    assert context_payload["cwd"] == "/work/tree"
    assert context_payload["started_at"] == session.started_at_iso
    assert context_payload["config_snapshot"]["ollama_url"] == "http://localhost:11434"


def test_finish_debug_session_cleans_up_even_if_result_write_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )

    def fail_dump(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as context:
        context.setattr("ksearch.debug_logging.json.dump", fail_dump)
        with pytest.raises(OSError, match="disk full"):
            finish_debug_session(
                success=True,
                command="health",
                summary={"result_count": 0},
            )

    assert session.finished is True
    assert session.logger.handlers == []

    next_session = start_debug_session(
        argv=["--debug", "search", "asyncio"],
        cwd="/work/tree",
        command="search",
    )
    finish_debug_session(success=True, command="search", summary={"result_count": 1})
    assert next_session.debug_dir.exists()


def test_start_debug_session_allows_two_finished_sessions_in_same_second(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    class FrozenDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 5, 11, 12, 0, 0)

    monkeypatch.setattr("ksearch.debug_logging.datetime", FrozenDateTime)

    first = start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )
    finish_debug_session(success=True, command="health", summary={"result_count": 0})
    second = start_debug_session(
        argv=["--debug", "search", "asyncio"],
        cwd="/work/tree",
        command="search",
    )
    finish_debug_session(success=True, command="search", summary={"result_count": 1})

    assert first.debug_dir != second.debug_dir
    assert first.debug_dir.name.startswith("cli-20260511-120000")
    assert second.debug_dir.name.startswith("cli-20260511-120000")


def test_start_debug_session_rejects_overlapping_active_session(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )

    with pytest.raises(RuntimeError, match="already active"):
        start_debug_session(
            argv=["--debug", "search"],
            cwd="/work/tree",
            command="search",
        )

    finish_debug_session(success=True, command="health", summary={"result_count": 0})


def test_start_debug_session_snapshots_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    argv = ["--debug", "health"]
    session = start_debug_session(
        argv=argv,
        cwd="/work/tree",
        command="health",
    )
    argv.append("--mutated")
    write_context({"config_snapshot": {"ollama_url": "http://localhost:11434"}})
    finish_debug_session(success=True, command="health", summary={"result_count": 0})

    context_payload = json.loads((session.debug_dir / "context.json").read_text(encoding="utf-8"))
    assert session.argv == ["--debug", "health"]
    assert context_payload["argv"] == ["--debug", "health"]


def test_finish_debug_session_uses_active_session_command(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session = start_debug_session(
        argv=["--debug", "health"],
        cwd="/work/tree",
        command="health",
    )
    finish_debug_session(success=True, command="search", summary={"result_count": 0})

    result_payload = json.loads((session.debug_dir / "result.json").read_text(encoding="utf-8"))
    assert result_payload["command"] == "health"


def test_start_debug_session_removes_directory_if_file_handler_creation_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))

    def fail_file_handler(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("ksearch.debug_logging.logging.FileHandler", fail_file_handler)

    with pytest.raises(OSError, match="permission denied"):
        start_debug_session(
            argv=["--debug", "health"],
            cwd="/work/tree",
            command="health",
        )

    debug_root = Path(tmp_path) / ".ksearch" / "debug"
    assert list(debug_root.glob("cli-*")) == []
