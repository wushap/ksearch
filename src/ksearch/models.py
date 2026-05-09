"""Data models for ksearch package."""

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


@dataclass
class QualityAssessment:
    """LLM-based quality assessment of content."""
    action: str              # "REFINE" or "COMPLETE"
    confidence: float        # 0.0 to 1.0
    gaps: list[str]          # identified information gaps
    refinement_query: str    # suggested follow-up query
    summary: str             # brief quality summary


@dataclass
class OptimizationResult:
    """Result of content optimization pipeline."""
    original_query: str
    final_content: str
    quality: QualityAssessment
    iterations_used: int
    elapsed_seconds: float
    refinement_history: list[dict]
