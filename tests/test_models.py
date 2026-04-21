"""Tests for kb.models module."""

from kb.models import CacheEntry, SearchResult, ResultEntry


def test_cache_entry_creation():
    entry = CacheEntry(
        url="https://example.com",
        file_path="/path/to/file.md",
        title="Example",
        keyword="test",
        cached_date="2026-04-21",
        engine="google",
        content="Example content",
    )
    assert entry.url == "https://example.com"
    assert entry.cached_date == "2026-04-21"


def test_search_result_creation():
    result = SearchResult(
        url="https://example.com",
        title="Example",
        content="Snippet",
        engine="google",
        published_date="2026-04-20",
    )
    assert result.url == "https://example.com"
    assert result.published_date == "2026-04-20"


def test_result_entry_creation():
    entry = ResultEntry(
        url="https://example.com",
        title="Example",
        content="Full content",
        file_path="/path/to/file.md",
        cached=True,
        source="google",
        cached_date="2026-04-21",
    )
    assert entry.cached is True
    assert entry.file_path == "/path/to/file.md"