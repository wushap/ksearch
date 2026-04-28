"""Tests for kb.cache module."""

import tempfile
import os
import sqlite3

from ksearch.cache import CacheManager
from ksearch.models import CacheEntry


def test_cache_manager_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        assert os.path.exists(db_path)
        assert os.path.exists(store_dir)


def test_cache_manager_save():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        file_path = manager.save(
            url="https://example.com/article",
            content="# Article Content\n\nThis is the content.",
            keyword="test keyword",
            metadata={"title": "Article", "engine": "google"},
        )

        assert os.path.exists(file_path)
        assert manager.exists("https://example.com/article")


def test_cache_manager_exact_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        manager.save(
            url="https://example.com/article",
            content="Content",
            keyword="exact keyword",
            metadata={"title": "Article", "engine": "google"},
        )

        results = manager.exact_match("exact keyword")

        assert len(results) == 1
        assert results[0].url == "https://example.com/article"
        assert results[0].keyword == "exact keyword"


def test_cache_manager_partial_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        manager.save(
            url="https://example.com/a",
            content="Content A",
            keyword="python tutorial",
            metadata={"title": "A", "engine": "google"},
        )
        manager.save(
            url="https://example.com/b",
            content="Content B",
            keyword="rust tutorial",
            metadata={"title": "B", "engine": "duckduckgo"},
        )

        results = manager.partial_match("tutorial")

        assert len(results) == 2


def test_cache_manager_no_match():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        manager.save(
            url="https://example.com/article",
            content="Content",
            keyword="python",
            metadata={"title": "Article", "engine": "google"},
        )

        results = manager.exact_match("nonexistent")
        assert len(results) == 0

        results = manager.partial_match("nonexistent")
        assert len(results) == 0


def test_cache_manager_time_range_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        manager.save(
            url="https://example.com/new",
            content="New content",
            keyword="test",
            metadata={"title": "New", "engine": "google"},
        )

        results = manager.partial_match("test", time_range="week")
        assert len(results) >= 1


def test_cache_manager_get_file_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        file_path = manager.get_file_path("https://example.com/test")

        assert file_path.endswith(".md")
        assert store_dir in file_path


def test_cache_manager_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        manager.save(
            url="https://example.com/python",
            content="Python content",
            keyword="python",
            metadata={"title": "Python", "engine": "google"},
        )
        manager.save(
            url="https://docs.example.com/asyncio",
            content="Asyncio content",
            keyword="asyncio",
            metadata={"title": "Asyncio", "engine": "duckduckgo"},
        )
        manager.save(
            url="https://example.com/advanced",
            content="Advanced content",
            keyword="python",
            metadata={"title": "Advanced", "engine": "google"},
        )

        stats = manager.stats()

        assert stats["total_entries"] == 3
        assert stats["keyword_count"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["engines"]["google"] == 2
        assert stats["domains"]["example.com"] == 2
