import json
from pathlib import Path

from ksearch.debug_logging import (
    finish_debug_session,
    log_event,
    reset_debug_session_for_tests,
    start_debug_session,
    write_context,
)


def test_start_debug_session_creates_expected_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    reset_debug_session_for_tests()

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


def test_log_event_truncates_and_redacts_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    reset_debug_session_for_tests()

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
