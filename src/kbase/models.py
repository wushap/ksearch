"""Data models for kbase package."""

from dataclasses import dataclass


@dataclass
class CacheEntry:
    """Represents a cached entry in the local knowledge base."""
    url: str
    file_path: str
    title: str
    keyword: str
    cached_date: str
    engine: str
    content: str


@dataclass
class SearchResult:
    """Represents a result from SearXNG search."""
    url: str
    title: str
    content: str
    engine: str
    published_date: str


@dataclass
class ResultEntry:
    """Represents a unified result entry for output."""
    url: str
    title: str
    content: str
    file_path: str
    cached: bool
    source: str
    cached_date: str
