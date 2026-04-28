"""Tests for ksearch CLI entry points."""

import os
import tempfile

from typer.testing import CliRunner

from ksearch.__main__ import app


runner = CliRunner()


def test_health_command_runs_without_name_error(monkeypatch):
    """Health command should complete even when services are unavailable."""

    class FakeEmbedder:
        def __init__(self, *args, **kwargs):
            pass

        def health_check(self):
            return {
                "ollama": False,
                "ollama_error": "unavailable",
                "sentence_transformers": True,
                "ollama_models": [],
            }

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr("ksearch.__main__.EmbeddingGenerator", FakeEmbedder)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert "Service Health" in result.output
    assert "SearXNG" in result.output


def test_search_command_accepts_kb_dir_for_only_cache_flow():
    """Search CLI should allow pointing KB search at a non-default directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        kb_dir = os.path.join(tmpdir, "kb")
        doc_path = os.path.join(tmpdir, "note.md")
        with open(doc_path, "w", encoding="utf-8") as handle:
            handle.write("# KB Doc\n\nPython asyncio cancellation notes.")

        ingest_result = runner.invoke(
            app,
            ["kb", "ingest", doc_path, "--kb-dir", kb_dir, "--source", "test"],
        )
        assert ingest_result.exit_code == 0

        result = runner.invoke(
            app,
            [
                "search",
                "Python asyncio cancellation",
                "--kb",
                "chroma",
                "--kb-dir",
                kb_dir,
                "--only-cache",
            ],
        )

        assert result.exit_code == 0
        assert "KB Doc" in result.output
