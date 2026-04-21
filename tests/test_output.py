"""Tests for kb.output module."""

from kb.output import format_markdown, format_paths
from kb.models import ResultEntry


def test_format_markdown_with_cached_results():
    entries = [
        ResultEntry(
            url="https://example.com/a",
            title="Cached Article",
            content="# Content A\n\nThis is cached.",
            file_path="/path/to/a.md",
            cached=True,
            source="google",
            cached_date="2026-04-21 10:00:00",
        ),
        ResultEntry(
            url="https://example.com/b",
            title="New Article",
            content="# Content B\n\nThis is new.",
            file_path="/path/to/b.md",
            cached=False,
            source="duckduckgo",
            cached_date="",
        ),
    ]

    output = format_markdown(entries, "test keyword")

    assert "# 搜索结果: \"test keyword\"" in output
    assert "[cached] Cached Article" in output
    assert "New Article" in output
    assert "总计: 2条结果" in output


def test_format_markdown_empty_results():
    output = format_markdown([], "nonexistent")

    assert "# 搜索结果: \"nonexistent\"" in output
    assert "无结果" in output


def test_format_paths():
    entries = [
        ResultEntry(
            url="https://example.com/a",
            title="A",
            content="",
            file_path="/path/to/a.md",
            cached=True,
            source="google",
            cached_date="",
        ),
        ResultEntry(
            url="https://example.com/b",
            title="B",
            content="",
            file_path="/path/to/b.md",
            cached=False,
            source="duckduckgo",
            cached_date="",
        ),
    ]

    output = format_paths(entries)

    assert "/path/to/a.md" in output
    assert "/path/to/b.md" in output
    assert output.count("\n") == 2


def test_format_paths_empty():
    output = format_paths([])

    assert output == ""