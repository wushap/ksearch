"""CLI debug lifecycle integration tests."""

import json

from typer.testing import CliRunner

from ksearch.__main__ import app
from ksearch.models import ResultEntry


runner = CliRunner()


class _StubDependency:
    def __init__(self, *args, **kwargs):
        pass


def _debug_session_dir(home_dir):
    sessions = sorted((home_dir / ".ksearch" / "debug").glob("cli-*"))
    assert len(sessions) == 1
    return sessions[0]


def _install_search_stubs(monkeypatch, iterative_engine_cls):
    monkeypatch.setattr("ksearch.cli.search.CacheManager", _StubDependency)
    monkeypatch.setattr("ksearch.cli.search.SearXNGClient", _StubDependency)
    monkeypatch.setattr("ksearch.cli.search.ContentConverter", _StubDependency)
    monkeypatch.setattr("ksearch.cli.search.SearchEngine", _StubDependency)
    monkeypatch.setattr("ksearch.cli.search.build_kbase", lambda config: object())
    monkeypatch.setattr("ksearch.cli.search.IterativeSearchEngine", iterative_engine_cls)
    monkeypatch.setattr("ksearch.cli.search.format_markdown", lambda results, keyword: f"{keyword}:{len(results)}")


def test_search_debug_logs_config_snapshot_and_result_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeIterativeEngine:
        def __init__(self, _kbase, _searxng, _converter, _cache, config):
            self.config = config

        def search(self, keyword):
            return [
                ResultEntry(
                    url="https://example.com/asyncio",
                    title="Asyncio Notes",
                    content="Cancellation propagation details.",
                    file_path="/tmp/asyncio.md",
                    cached=False,
                    source="web",
                    cached_date="2026-05-11",
                )
            ]

    _install_search_stubs(monkeypatch, FakeIterativeEngine)

    result = runner.invoke(
        app,
        [
            "--debug",
            "search",
            "asyncio",
            "--max-results",
            "2",
            "--timeout",
            "7",
        ],
    )

    assert result.exit_code == 0

    session_dir = _debug_session_dir(tmp_path)
    context_payload = json.loads((session_dir / "context.json").read_text(encoding="utf-8"))
    result_payload = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))

    assert context_payload["config_snapshot"]["max_results"] == 2
    assert context_payload["config_snapshot"]["timeout"] == 7
    assert context_payload["command_context"]["keyword"] == "asyncio"
    assert result_payload["success"] is True
    assert result_payload["summary"]["result_count"] == 1


def test_search_debug_logs_failure_result_with_error_message(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeIterativeEngine:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, keyword):
            raise RuntimeError("iterative backend failed")

    _install_search_stubs(monkeypatch, FakeIterativeEngine)

    result = runner.invoke(app, ["--debug", "search", "asyncio"])

    assert result.exit_code == 1

    session_dir = _debug_session_dir(tmp_path)
    result_payload = json.loads((session_dir / "result.json").read_text(encoding="utf-8"))

    assert result_payload["success"] is False
    assert result_payload["error"]["message"] == "iterative backend failed"
