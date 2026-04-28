"""Tests for kbase.search module."""

import tempfile
import os
from unittest.mock import Mock, patch

from kbase.search import SearchEngine
from kbase.cache import CacheManager
from kbase.searxng import SearXNGClient
from kbase.converter import ContentConverter
from kbase.models import SearchResult, ResultEntry


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