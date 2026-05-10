"""Tests for ksearch CLI entry points."""

import os
import tempfile

from typer.testing import CliRunner

from ksearch.__main__ import app


runner = CliRunner()


def test_app_help_uses_ksearch_as_primary_name():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ksearch" in result.output


def test_health_command_runs_without_name_error(monkeypatch):
    """Health command should complete via legacy patch points."""

    class FakeEmbedder:
        created = False

        def __init__(self, *args, **kwargs):
            FakeEmbedder.created = True

        def health_check(self):
            return {
                "ollama": False,
                "ollama_error": "unavailable",
                "sentence_transformers": True,
                "ollama_models": [],
            }

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr("ksearch.cli_system.EmbeddingGenerator", FakeEmbedder)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert FakeEmbedder.created is True
    assert "Service Health" in result.output
    assert "SearXNG" in result.output


def test_search_command_accepts_kbase_dir_for_only_cache_flow():
    """Search CLI should allow pointing kbase search at a non-default directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        kbase_dir = os.path.join(tmpdir, "kbase")
        doc_path = os.path.join(tmpdir, "note.md")
        with open(doc_path, "w", encoding="utf-8") as handle:
            handle.write("# kbase Doc\n\nPython asyncio cancellation notes.")

        ingest_result = runner.invoke(
            app,
            ["kbase", "ingest", doc_path, "--kbase-dir", kbase_dir, "--source", "test"],
        )
        assert ingest_result.exit_code == 0

        result = runner.invoke(
            app,
            [
                "search",
                "Python asyncio cancellation",
                "--kbase",
                "chroma",
                "--kbase-dir",
                kbase_dir,
                "--only-cache",
            ],
        )

        assert result.exit_code == 0
        assert "kbase Doc" in result.output


def test_search_command_uses_iterative_defaults_from_config(monkeypatch):
    """Search should honor iterative defaults when no explicit iterative flag is passed."""

    class FakeCache:
        def __init__(self, *args, **kwargs):
            pass

    class FakeSearxng:
        def __init__(self, *args, **kwargs):
            pass

    class FakeConverter:
        def __init__(self, *args, **kwargs):
            pass

    class FakeSearchEngine:
        called = False

        def __init__(self, *args, **kwargs):
            pass

        def search(self, *args, **kwargs):
            FakeSearchEngine.called = True
            return []

    class FakeIterativeEngine:
        called = False
        config = None

        def __init__(self, _kbase, _searxng, _converter, _cache, config):
            FakeIterativeEngine.config = config

        def search(self, keyword):
            FakeIterativeEngine.called = True
            return []

    monkeypatch.setattr("ksearch.cli.search.load_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("ksearch.cli.search.CacheManager", FakeCache)
    monkeypatch.setattr("ksearch.cli.search.SearXNGClient", FakeSearxng)
    monkeypatch.setattr("ksearch.cli.search.ContentConverter", FakeConverter)
    monkeypatch.setattr("ksearch.cli.search.SearchEngine", FakeSearchEngine)
    monkeypatch.setattr("ksearch.cli.search.IterativeSearchEngine", FakeIterativeEngine)
    monkeypatch.setattr("ksearch.cli.search.build_kbase", lambda config: object())

    result = runner.invoke(app, ["search", "default iterative query"])

    assert result.exit_code == 0
    assert FakeIterativeEngine.called is True
    assert FakeIterativeEngine.config["iterative_enabled"] is True
    assert FakeSearchEngine.called is False


def test_query_command_searches_kbase_entries():
    with tempfile.TemporaryDirectory() as tmpdir:
        kbase_dir = os.path.join(tmpdir, "kbase")
        doc_path = os.path.join(tmpdir, "note.md")
        with open(doc_path, "w", encoding="utf-8") as handle:
            handle.write("# Asyncio Notes\n\nCancellation propagation reference.")

        ingest_result = runner.invoke(
            app,
            ["kbase", "ingest", doc_path, "--kbase-dir", kbase_dir, "--source", "test"],
        )
        assert ingest_result.exit_code == 0

        query_result = runner.invoke(
            app,
            ["kbase", "query", "Cancellation propagation", "--kbase-dir", kbase_dir],
        )

        assert query_result.exit_code == 0
        assert "Asyncio Notes" in query_result.output


def test_kbase_reset_command_reinitializes_kbase(monkeypatch):
    """Reset command should honor legacy kbase patch points at runtime."""

    class FakeKB:
        last_init = None
        reset_called = False

        def __init__(self, **kwargs):
            FakeKB.last_init = kwargs

        def reset(self):
            FakeKB.reset_called = True

    monkeypatch.setattr("ksearch.cli_kbase.KnowledgeBase", FakeKB)

    result = runner.invoke(
        app,
        [
            "kbase",
            "reset",
            "--confirm",
            "--mode",
            "chroma",
            "--kbase-dir",
            "/tmp/test-kbase",
            "--embedding-model",
            "mxbai-embed-large",
            "--embedding-dimension",
            "1024",
            "--ollama-url",
            "http://localhost:11434",
        ],
    )

    assert result.exit_code == 0
    assert FakeKB.reset_called is True
    assert FakeKB.last_init["embedding_model"] == "mxbai-embed-large"
    assert FakeKB.last_init["embedding_dimension"] == 1024


def test_stats_command_prints_unified_sections(monkeypatch):
    """Stats command should honor legacy stats patch points at runtime."""

    class FakeCache:
        created = False

        def __init__(self, *args, **kwargs):
            FakeCache.created = True

        def stats(self):
            return {
                "total_entries": 3,
                "keyword_count": 2,
                "total_size_bytes": 1200,
                "engines": {"google": 2},
                "domains": {"example.com": 2},
            }

    class FakeKB:
        created = False

        def __init__(self, **kwargs):
            FakeKB.created = True

        def stats(self):
            return {
                "total_entries": 4,
                "source_file_count": 2,
                "total_size_bytes": 2400,
                "sources": {"web": 3, "manual": 1},
                "mode": "chroma",
                "embedding_model": "nomic-embed-text",
                "embedding_dimension": 768,
            }

    monkeypatch.setattr("ksearch.cli_system.CacheManager", FakeCache)
    monkeypatch.setattr("ksearch.cli_system.KnowledgeBase", FakeKB)

    result = runner.invoke(app, ["stats"])

    assert result.exit_code == 0
    assert FakeCache.created is True
    assert FakeKB.created is True
    assert "Overview" in result.output
    assert "Cache Stats" in result.output
    assert "kbase stats" in result.output


def test_cli_search_uses_compatibility_searchengine_export():
    from ksearch.search import SearchEngine as SearchEngineCompat
    from ksearch.cli_search import SearchEngine as SearchEngineFromCLI

    assert SearchEngineFromCLI is SearchEngineCompat


def test_cli_package_is_importable():
    from ksearch.cli.search import register_search_command

    assert register_search_command is not None


def test_cli_compat_modules_remain_importable_and_callable():
    from ksearch.cli_kbase import register_kbase_commands
    from ksearch.cli_search import register_search_command
    from ksearch.cli_system import (
        register_config_command,
        register_health_command,
        register_stats_command,
    )

    assert callable(register_search_command)
    assert callable(register_kbase_commands)
    assert callable(register_stats_command)
    assert callable(register_config_command)
    assert callable(register_health_command)
