"""Tests for ksearch.search module."""

import json
import tempfile
import os
from unittest.mock import Mock, patch

from ksearch.debug_logging import finish_debug_session, start_debug_session
from ksearch.search import SearchEngine
from ksearch.cache import CacheManager
from ksearch.searxng import SearXNGClient
from ksearch.converter import ContentConverter
from ksearch.models import SearchResult, ResultEntry


def test_search_engine_exact_match_no_network():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        cache = CacheManager(db_path, store_dir)
        cache.save(
            url="https://example.com/article",
            content="Cached content",
            keyword="exact match",
            metadata={"title": "Article", "engine": "google"},
        )

        searxng = Mock(spec=SearXNGClient)
        converter = Mock(spec=ContentConverter)

        engine = SearchEngine(cache, searxng, converter)
        results = engine.search("exact match", {"no_cache": False, "only_cache": False})

        # Exact match should not trigger network search
        searxng.search.assert_not_called()
        assert len(results) == 1
        assert results[0].cached is True


def test_search_engine_partial_match_with_network():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        cache = CacheManager(db_path, store_dir)
        cache.save(
            url="https://example.com/a",
            content="Content A",
            keyword="python tutorial",
            metadata={"title": "A", "engine": "google"},
        )

        searxng = Mock(spec=SearXNGClient)
        searxng.search.return_value = [
            SearchResult(
                url="https://example.com/b",
                title="New Result",
                content="Snippet",
                engine="duckduckgo",
                published_date="",
            )
        ]

        converter = Mock(spec=ContentConverter)
        converter.convert_url.return_value = "Converted content"

        engine = SearchEngine(cache, searxng, converter)
        results = engine.search("tutorial", {"no_cache": False, "only_cache": False, "time_range": None, "max_results": 10})

        # Partial match should trigger network search
        searxng.search.assert_called_once()
        assert len(results) == 2  # 1 cached + 1 network


def test_search_engine_no_cache_flag():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        cache = CacheManager(db_path, store_dir)
        cache.save(
            url="https://example.com/article",
            content="Cached content",
            keyword="test",
            metadata={"title": "Article", "engine": "google"},
        )

        searxng = Mock(spec=SearXNGClient)
        searxng.search.return_value = []

        converter = Mock(spec=ContentConverter)

        engine = SearchEngine(cache, searxng, converter)
        results = engine.search("test", {"no_cache": True, "only_cache": False, "time_range": None, "max_results": 10})

        # no_cache should skip local search
        searxng.search.assert_called_once()


def test_search_engine_only_cache_flag():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        cache = CacheManager(db_path, store_dir)

        searxng = Mock(spec=SearXNGClient)
        converter = Mock(spec=ContentConverter)

        engine = SearchEngine(cache, searxng, converter)
        results = engine.search("nonexistent", {"no_cache": False, "only_cache": True, "time_range": None, "max_results": 10})

        # only_cache should not trigger network search
        searxng.search.assert_not_called()
        assert len(results) == 0


def test_search_engine_skips_known_slow_urls():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        cache = CacheManager(db_path, store_dir)
        searxng = Mock(spec=SearXNGClient)
        searxng.search.return_value = [
            SearchResult(
                url="https://youtube.com/watch?v=abc",
                title="Video",
                content="",
                engine="duckduckgo",
                published_date="",
            ),
            SearchResult(
                url="https://example.com/article",
                title="Article",
                content="",
                engine="duckduckgo",
                published_date="",
            ),
        ]

        converter = Mock(spec=ContentConverter)
        converter.convert_url.return_value = "Converted content that is long enough."

        engine = SearchEngine(cache, searxng, converter)
        results = engine.search("python", {"no_cache": True, "only_cache": False, "max_results": 10})

        converter.convert_url.assert_called_once_with("https://example.com/article")
        assert len(results) == 1
        assert results[0].url == "https://example.com/article"


def test_search_engine_compatibility_export_points_to_searching_service():
    from ksearch.searching import SearchEngine as SearchEngineFromSearching
    from ksearch.searching.service import SearchEngine as SearchEngineFromService

    assert SearchEngine is SearchEngineFromSearching
    assert SearchEngine is SearchEngineFromService


def test_search_engine_logs_cache_and_network_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    cache = Mock()
    cache.exact_match.return_value = []
    cache.partial_match.return_value = []
    cache.save.return_value = str(tmp_path / "result.md")

    searxng = Mock(spec=SearXNGClient)
    searxng.search.return_value = [
        SearchResult(
            url="https://example.com/article",
            title="Example",
            content="Snippet",
            engine="google",
            published_date="",
        )
    ]

    converter = Mock(spec=ContentConverter)
    converter.convert_url.return_value = "Converted content that is definitely long enough."

    session = start_debug_session(
        argv=["--debug", "search", "python"],
        cwd="/work/tree",
        command="search",
    )

    engine = SearchEngine(cache, searxng, converter)
    results = engine.search(
        "python",
        {"no_cache": False, "only_cache": False, "time_range": None, "max_results": 10, "timeout": 30},
    )
    finish_debug_session(success=True, command="search", summary={"result_count": len(results)})

    events = [
        json.loads(line)
        for line in (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_names = [event["event"] for event in events]

    assert "cache_lookup" in event_names
    assert "network_search_start" in event_names
    assert "network_search_results" in event_names
    assert "conversion_complete" in event_names


def test_search_engine_exact_cache_path_logs_final_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    cache_entry = Mock()
    cache_entry.url = "https://example.com/article"
    cache_entry.title = "Cached"
    cache_entry.content = "Cached content"
    cache_entry.file_path = "/tmp/cached.md"
    cache_entry.engine = "cache"
    cache_entry.cached_date = "2026-05-11"

    cache = Mock()
    cache.exact_match.return_value = [cache_entry]
    cache.partial_match.return_value = []

    searxng = Mock(spec=SearXNGClient)
    converter = Mock(spec=ContentConverter)

    session = start_debug_session(
        argv=["--debug", "search", "python"],
        cwd="/work/tree",
        command="search",
    )

    engine = SearchEngine(cache, searxng, converter)
    results = engine.search("python", {"no_cache": False, "only_cache": False})
    finish_debug_session(success=True, command="search", summary={"result_count": len(results)})

    events = [
        json.loads(line)
        for line in (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    search_complete = [event for event in events if event["event"] == "search_complete"][-1]

    assert search_complete["data"]["result_count"] == 1
    assert search_complete["data"]["cached_count"] == 1
    assert search_complete["data"]["network_count"] == 0
