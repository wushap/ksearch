"""Tests for ksearch.cache module."""

import json
import tempfile
import os
import sqlite3
import hashlib

from ksearch.debug_logging import finish_debug_session, start_debug_session
from ksearch.cache import CacheManager
from ksearch.models import CacheEntry


def test_cache_layer_service_module_exists_and_matches_public_cache_manager():
    from ksearch.cache_layer.service import CacheManager as LayeredCacheManager

    assert CacheManager is LayeredCacheManager


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


def test_cache_manager_queries_work_without_keyword_index_files():
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

        index_dir = os.path.join(store_dir, "_index")
        if os.path.exists(index_dir):
            for filename in os.listdir(index_dir):
                os.remove(os.path.join(index_dir, filename))
            os.rmdir(index_dir)

        exact = manager.exact_match("python tutorial")
        partial = manager.partial_match("tutorial")

        assert len(exact) == 1
        assert exact[0].url == "https://example.com/a"
        assert len(partial) == 2


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


def test_cache_manager_save_uses_url_hash_filename():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)
        url = "https://example.com/path?a=1&b=2"

        file_path = manager.save(
            url=url,
            content="content",
            keyword="hashing",
            metadata={"title": "Hash Test", "engine": "google"},
        )

        expected_hash = hashlib.sha256(url.encode()).hexdigest()
        assert os.path.basename(file_path) == f"{expected_hash}.md"

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT file_hash, file_path FROM cache WHERE url = ?",
                (url,),
            ).fetchone()

        assert row is not None
        assert row[0] == expected_hash
        assert row[1] == file_path


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


def test_cache_manager_stats_normalizes_engine_names():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)

        manager.save(
            url="https://example.com/one",
            content="One",
            keyword="python",
            metadata={"title": "One", "engine": "startpage, brave"},
        )
        manager.save(
            url="https://example.com/two",
            content="Two",
            keyword="python",
            metadata={"title": "Two", "engine": " StartPage ,Brave "},
        )
        manager.save(
            url="https://example.com/three",
            content="Three",
            keyword="python",
            metadata={"title": "Three", "engine": ""},
        )

        stats = manager.stats()

        assert stats["engines"]["startpage"] == 2
        assert stats["engines"]["brave"] == 2
        assert stats["engines"]["unknown"] == 1


def test_cache_manager_exact_match_loads_content_from_store_layer():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store_dir = os.path.join(tmpdir, "store")

        manager = CacheManager(db_path, store_dir)
        manager.save(
            url="https://example.com/article",
            content="# Article",
            keyword="python",
            metadata={"title": "Example", "engine": "web"},
        )

        results = manager.exact_match("python")

        assert len(results) == 1
        assert results[0].content == "# Article"


def test_cache_manager_logs_save_and_lookup_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    db_path = os.path.join(tmp_path, "test.db")
    store_dir = os.path.join(tmp_path, "store")

    session = start_debug_session(
        argv=["--debug", "search", "python"],
        cwd="/work/tree",
        command="search",
    )

    manager = CacheManager(db_path, store_dir)
    manager.save(
        url="https://example.com/article",
        content="# Article Content\n\nThis is long enough to keep.",
        keyword="python",
        metadata={"title": "Article", "engine": "google"},
    )
    manager.exact_match("python")
    manager.partial_match("python")
    finish_debug_session(success=True, command="search", summary={"result_count": 1})

    events = [
        json.loads(line)
        for line in (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_names = [event["event"] for event in events]

    assert "cache_save" in event_names
    assert "cache_exact_match" in event_names
    assert "cache_partial_match" in event_names
