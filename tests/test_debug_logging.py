import json
from datetime import datetime
from pathlib import Path

from ksearch.debug_logging import finish_debug_session, log_event, start_debug_session, write_context


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


def test_start_debug_session_allows_two_sessions_in_same_second(tmp_path, monkeypatch):
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
    second = start_debug_session(
        argv=["--debug", "search", "asyncio"],
        cwd="/work/tree",
        command="search",
    )

    assert first.debug_dir != second.debug_dir
    assert first.debug_dir.name.startswith("cli-20260511-120000")
    assert second.debug_dir.name.startswith("cli-20260511-120000")
