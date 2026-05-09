"""Tests for ksearch.models module."""

from ksearch.models import CacheEntry, SearchResult, ResultEntry


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


def test_quality_assessment_dataclass():
    from ksearch.models import QualityAssessment
    qa = QualityAssessment(
        action="REFINE",
        confidence=0.6,
        gaps=["missing pricing info", "no recent data"],
        refinement_query="pricing details 2026",
        summary="Content lacks pricing and recent data",
    )
    assert qa.action == "REFINE"
    assert qa.confidence == 0.6
    assert len(qa.gaps) == 2


def test_optimization_result_dataclass():
    from ksearch.models import OptimizationResult, QualityAssessment
    assessment = QualityAssessment(
        action="COMPLETE", confidence=0.9, gaps=[], refinement_query="", summary="Good"
    )
    result = OptimizationResult(
        original_query="test query",
        final_content="optimized content",
        quality=assessment,
        iterations_used=2,
        elapsed_seconds=15.5,
        refinement_history=[{"iteration": 1, "confidence": 0.6}, {"iteration": 2, "confidence": 0.9}],
    )
    assert result.iterations_used == 2
    assert len(result.refinement_history) == 2