"""Tests for iterative search convergence and boundary management."""

import pytest
from unittest.mock import Mock, MagicMock, patch
import time

from kbase.iterative import (
    ConvergenceEvaluator,
    ConvergenceResult,
    IterationBoundary,
    QueryClassifier,
    SufficiencyEvaluator,
    IterativeSearchEngine,
)
from kbase.kbase import KnowledgeBaseSearchResult
from kbase.models import ResultEntry


class TestConvergenceEvaluator:
    """Tests for ConvergenceEvaluator class."""

    @pytest.fixture
    def evaluator(self):
        """Create default convergence evaluator."""
        return ConvergenceEvaluator()

    @pytest.fixture
    def evaluator_custom(self):
        """Create convergence evaluator with custom thresholds."""
        return ConvergenceEvaluator(
            score_delta_threshold=0.10,
            overlap_threshold=0.60,
            redundancy_threshold=0.50,
        )

    def make_kbase_result(self, id: str, score: float, content: str = "test content") -> KnowledgeBaseSearchResult:
        """Helper to create KnowledgeBaseSearchResult."""
        return KnowledgeBaseSearchResult(
            id=id,
            content=content,
            file_path=f"/path/{id}",
            title=f"Title {id}",
            source="kbase",
            score=score,
            metadata={},
        )

    def test_check_convergence_with_none_prev_results(self, evaluator):
        """Test check_convergence with None prev_results (first iteration)."""
        current = [self.make_kbase_result("a", 0.8)]
        result = evaluator.check_convergence(None, current)

        assert result.is_converged is False
        assert result.score_delta == 1.0
        assert result.overlap_ratio == 0.0
        assert result.redundancy_ratio == 0.0
        assert result.factors_met == []

    def test_check_convergence_with_empty_prev_results(self, evaluator):
        """Test check_convergence with empty prev_results list."""
        current = [self.make_kbase_result("a", 0.8)]
        result = evaluator.check_convergence([], current)

        assert result.is_converged is False
        assert result.score_delta == 1.0
        assert result.overlap_ratio == 0.0
        assert result.redundancy_ratio == 0.0

    def test_convergence_when_two_factors_met(self, evaluator):
        """Test convergence when 2+ factors are met."""
        # Create results with same IDs (high overlap) and similar scores (low delta)
        prev = [self.make_kbase_result("a", 0.80), self.make_kbase_result("b", 0.75)]
        current = [self.make_kbase_result("a", 0.81), self.make_kbase_result("b", 0.76)]

        result = evaluator.check_convergence(prev, current)

        # Overlap ratio should be 100% (same IDs)
        assert result.overlap_ratio >= evaluator.overlap_threshold
        # Score delta should be small
        assert result.score_delta < evaluator.score_delta_threshold
        # Should have at least 2 factors met
        assert len(result.factors_met) >= 2
        assert result.is_converged is True

    def test_non_convergence_when_only_one_factor_met(self, evaluator):
        """Test non-convergence when only 1 factor is met."""
        # Create results with same IDs but different scores AND different content
        prev = [
            self.make_kbase_result("a", 0.10, "previous content for item a"),
            self.make_kbase_result("b", 0.15, "previous content for item b"),
        ]
        current = [
            self.make_kbase_result("a", 0.80, "current content for item a different"),
            self.make_kbase_result("b", 0.85, "current content for item b different"),
        ]

        result = evaluator.check_convergence(prev, current)

        # Overlap should meet threshold (same IDs)
        assert result.overlap_ratio >= evaluator.overlap_threshold
        # But score delta should be large
        assert result.score_delta >= evaluator.score_delta_threshold
        # Redundancy should not be met (different content)
        assert result.redundancy_ratio < evaluator.redundancy_threshold
        # Should only have 1 factor met (overlap)
        assert len(result.factors_met) == 1
        assert result.is_converged is False

    def test_score_delta_threshold_calculation(self, evaluator):
        """Test score_delta threshold calculation."""
        prev = [self.make_kbase_result("a", 0.80)]
        current = [self.make_kbase_result("b", 0.84)]  # 5% change

        result = evaluator.check_convergence(prev, current)

        # Score delta = |0.84 - 0.80| / 0.80 = 0.05
        assert abs(result.score_delta - 0.05) < 0.001

    def test_overlap_ratio_calculation(self, evaluator):
        """Test overlap_ratio calculation."""
        # 3 previous, 3 current, 2 overlap
        prev = [
            self.make_kbase_result("a", 0.8),
            self.make_kbase_result("b", 0.8),
            self.make_kbase_result("c", 0.8),
        ]
        current = [
            self.make_kbase_result("a", 0.8),
            self.make_kbase_result("b", 0.8),
            self.make_kbase_result("d", 0.8),
        ]

        result = evaluator.check_convergence(prev, current)

        # overlap_ratio = 2 / 3 = 0.667
        assert abs(result.overlap_ratio - 0.667) < 0.01

    def test_redundancy_ratio_calculation(self, evaluator):
        """Test redundancy_ratio calculation."""
        # Same content = high redundancy
        content = "identical test content here"
        prev = [self.make_kbase_result("a", 0.8, content)]
        current = [self.make_kbase_result("b", 0.8, content)]

        result = evaluator.check_convergence(prev, current)

        # Same content hash = 100% redundancy
        assert result.redundancy_ratio == 1.0

    def test_redundancy_ratio_different_content(self, evaluator):
        """Test redundancy_ratio with different content."""
        prev = [self.make_kbase_result("a", 0.8, "completely different content one")]
        current = [self.make_kbase_result("b", 0.8, "totally other content two")]

        result = evaluator.check_convergence(prev, current)

        # Different content = 0% redundancy
        assert result.redundancy_ratio == 0.0

    def test_custom_thresholds(self, evaluator_custom):
        """Test convergence with custom thresholds."""
        prev = [self.make_kbase_result("a", 0.80), self.make_kbase_result("b", 0.75)]
        current = [self.make_kbase_result("a", 0.85), self.make_kbase_result("b", 0.80)]

        result = evaluator_custom.check_convergence(prev, current)

        # With 0.10 threshold, score delta ~6.25% should pass
        assert result.score_delta < evaluator_custom.score_delta_threshold
        # Overlap = 100%
        assert result.overlap_ratio >= evaluator_custom.overlap_threshold


class TestIterationBoundary:
    """Tests for IterationBoundary class."""

    @pytest.fixture
    def boundary_default(self):
        """Create default iteration boundary."""
        return IterationBoundary()

    @pytest.fixture
    def boundary_custom(self):
        """Create iteration boundary with custom limits."""
        return IterationBoundary(max_iterations=3, max_time_seconds=60.0)

    def test_check_limits_iteration_exceeds_max(self, boundary_custom):
        """Test check_limits when iteration exceeds max."""
        result = boundary_custom.check_limits(iteration_count=3, elapsed_time=10.0)
        assert result is True  # Should stop

    def test_check_limits_iteration_within_bounds(self, boundary_custom):
        """Test check_limits when iteration within bounds."""
        result = boundary_custom.check_limits(iteration_count=2, elapsed_time=10.0)
        assert result is False  # Should continue

    def test_check_limits_time_exceeds_max(self, boundary_custom):
        """Test check_limits when time exceeds max."""
        result = boundary_custom.check_limits(iteration_count=1, elapsed_time=60.0)
        assert result is True  # Should stop

    def test_check_limits_time_within_bounds(self, boundary_custom):
        """Test check_limits when time within bounds."""
        result = boundary_custom.check_limits(iteration_count=1, elapsed_time=30.0)
        assert result is False  # Should continue

    def test_check_limits_both_within_bounds(self, boundary_default):
        """Test check_limits when both within bounds."""
        result = boundary_default.check_limits(iteration_count=3, elapsed_time=100.0)
        assert result is False  # Should continue

    def test_check_limits_both_exceed(self, boundary_custom):
        """Test check_limits when both exceed."""
        result = boundary_custom.check_limits(iteration_count=5, elapsed_time=90.0)
        assert result is True  # Should stop

    def test_default_max_iterations(self, boundary_default):
        """Test default max_iterations is 5."""
        assert boundary_default.max_iterations == 5

    def test_default_max_time_seconds(self, boundary_default):
        """Test default max_time_seconds is 180."""
        assert boundary_default.max_time_seconds == 180.0


class TestQueryClassifier:
    """Tests for QueryClassifier class."""

    @pytest.fixture
    def classifier(self):
        """Create query classifier."""
        return QueryClassifier()

    def test_fact_query_chinese_keywords(self, classifier):
        """Test fact query classification with Chinese keywords."""
        assert classifier.classify("如何学习编程") == "fact"
        assert classifier.classify("是什么是机器学习") == "fact"
        assert classifier.classify("怎么安装Python") == "fact"

    def test_fact_query_english_keywords(self, classifier):
        """Test fact query classification with English keywords."""
        assert classifier.classify("how to learn python") == "fact"
        assert classifier.classify("what is machine learning") == "fact"
        assert classifier.classify("definition of API") == "fact"

    def test_exploration_query_chinese_keywords(self, classifier):
        """Test exploration query classification with Chinese keywords."""
        assert classifier.classify("探索AI发展趋势") == "exploration"
        assert classifier.classify("对比不同数据库系统") == "exploration"
        assert classifier.classify("分析市场研究报告") == "exploration"

    def test_exploration_query_english_keywords(self, classifier):
        """Test exploration query classification with English keywords."""
        assert classifier.classify("explore AI trends") == "exploration"
        assert classifier.classify("compare database systems") == "exploration"
        assert classifier.classify("analyze market research") == "exploration"

    def test_short_query_defaults_to_fact(self, classifier):
        """Test short query (< 5 words) defaults to fact."""
        assert classifier.classify("python programming") == "fact"  # 2 words
        assert classifier.classify("test code") == "fact"  # 2 words
        assert classifier.classify("short query test") == "fact"  # 3 words

    def test_long_query_defaults_to_exploration(self, classifier):
        """Test long query defaults to exploration."""
        # No keywords, > 5 words
        assert classifier.classify("I want to understand more about this topic") == "exploration"
        assert classifier.classify("looking for comprehensive information on various subjects") == "exploration"

    def test_exploration_keyword_overrides_length(self, classifier):
        """Test exploration keyword overrides short length."""
        # Short query but has exploration keyword
        assert classifier.classify("explore python") == "exploration"  # 2 words

    def test_fact_keyword_detected_before_length_check(self, classifier):
        """Test fact keyword detected before length default."""
        # Longer query with fact keyword
        assert classifier.classify("how to implement this feature in my project") == "fact"

    def test_case_insensitive_matching(self, classifier):
        """Test keyword matching is case insensitive."""
        assert classifier.classify("HOW TO LEARN PYTHON") == "fact"
        assert classifier.classify("EXPLORE AI TRENDS") == "exploration"


class TestSufficiencyEvaluator:
    """Tests for SufficiencyEvaluator class."""

    @pytest.fixture
    def evaluator(self):
        """Create sufficiency evaluator."""
        return SufficiencyEvaluator()

    def make_kbase_result(self, score: float, content: str = "test content") -> KnowledgeBaseSearchResult:
        """Helper to create KnowledgeBaseSearchResult."""
        return KnowledgeBaseSearchResult(
            id=f"result_{score}",
            content=content,
            file_path="/path/test",
            title="Test",
            source="kbase",
            score=score,
            metadata={},
        )

    def test_score_with_empty_results(self, evaluator):
        """Test score with empty results returns 0.0."""
        score = evaluator.score([])
        assert score == 0.0

    def test_score_with_results_meeting_max_thresholds(self, evaluator):
        """Test score with results meeting max thresholds."""
        # 10+ results, high scores, good content length
        results = [self.make_kbase_result(0.9, "x" * 500) for _ in range(10)]

        score = evaluator.score(results)

        # Should be high: similarity ~0.9*0.4=0.36, count=1.0*0.3=0.3, coverage=1.0*0.3=0.3
        # Total ~0.96
        assert score > 0.9

    def test_score_with_results_between_min_max_thresholds(self, evaluator):
        """Test score with results between min/max thresholds."""
        # 5 results (between 3 and 10)
        results = [self.make_kbase_result(0.7, "x" * 300) for _ in range(5)]

        score = evaluator.score(results)

        # Should be in middle range
        assert 0.4 < score < 0.8

    def test_score_with_min_results(self, evaluator):
        """Test score with minimum results."""
        # 3 results (MIN_RESULTS_FOR_MIN_SCORE)
        results = [self.make_kbase_result(0.5, "x" * 200) for _ in range(3)]

        score = evaluator.score(results)

        # Count score = 0.3, contribution = 0.3 * 0.3 = 0.09
        # Similarity ~0.5 * 0.4 = 0.2
        # Coverage ~200/500 * 0.3 = 0.12
        # Total ~0.41
        assert score < 0.6

    def test_get_threshold_for_fact_queries(self, evaluator):
        """Test get_threshold for fact queries."""
        threshold = evaluator.get_threshold("fact")
        assert threshold == 0.7

    def test_get_threshold_for_exploration_queries(self, evaluator):
        """Test get_threshold for exploration queries."""
        threshold = evaluator.get_threshold("exploration")
        assert threshold == 0.4

    def test_get_threshold_unknown_type(self, evaluator):
        """Test get_threshold defaults to exploration for unknown."""
        threshold = evaluator.get_threshold("unknown")
        assert threshold == 0.4  # Exploration threshold

    def test_is_sufficient_meets_threshold(self, evaluator):
        """Test is_sufficient when score meets threshold."""
        assert evaluator.is_sufficient(0.8, 0.7) is True
        assert evaluator.is_sufficient(0.7, 0.7) is True  # Equal

    def test_is_sufficient_below_threshold(self, evaluator):
        """Test is_sufficient when score below threshold."""
        assert evaluator.is_sufficient(0.6, 0.7) is False
        assert evaluator.is_sufficient(0.3, 0.4) is False

    def test_score_weight_constants(self, evaluator):
        """Test weight constants sum to 1.0."""
        total_weight = (
            evaluator.WEIGHT_VECTOR_SIMILARITY
            + evaluator.WEIGHT_RESULT_COUNT
            + evaluator.WEIGHT_CONTENT_COVERAGE
        )
        assert total_weight == 1.0

    def test_threshold_constants(self, evaluator):
        """Test threshold constants."""
        assert evaluator.FACT_THRESHOLD == 0.7
        assert evaluator.EXPLORATION_THRESHOLD == 0.4
        assert evaluator.MIN_RESULTS_FOR_MAX_SCORE == 10
        assert evaluator.MIN_RESULTS_FOR_MIN_SCORE == 3


class TestIterativeSearchEngine:
    """Tests for IterativeSearchEngine class (integration-style with mocks)."""

    @pytest.fixture
    def mock_kbase(self):
        """Create mock KnowledgeBase."""
        kbase = Mock()
        kbase.search = Mock(return_value=[])
        kbase.ingest_file_from_content = Mock(return_value=1)
        return kbase

    @pytest.fixture
    def mock_searxng(self):
        """Create mock SearXNGClient."""
        client = Mock()
        # Mock search result structure
        result = Mock()
        result.url = "https://example.com"
        result.title = "Example Article"
        client.search = Mock(return_value=[result])
        return client

    @pytest.fixture
    def mock_converter(self):
        """Create mock ContentConverter."""
        converter = Mock()
        converter.convert_url = Mock(return_value="Example content from web")
        return converter

    @pytest.fixture
    def mock_cache(self):
        """Create mock CacheManager."""
        cache = Mock()
        cache.exists = Mock(return_value=False)
        return cache

    @pytest.fixture
    def config(self):
        """Create default config."""
        return {
            "max_iterations": 5,
            "max_time_seconds": 180,
            "kbase_top_k": 5,
            "max_results": 5,
            "fact_threshold": 0.7,
            "exploration_threshold": 0.4,
            "scoring_weights": {"vector": 0.4, "count": 0.3, "coverage": 0.3},
        }

    @pytest.fixture
    def engine(self, mock_kbase, mock_searxng, mock_converter, mock_cache, config):
        """Create IterativeSearchEngine with mocks."""
        return IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config=config,
        )

    def make_kbase_result(self, score: float = 0.9, idx: int = None) -> KnowledgeBaseSearchResult:
        """Helper to create KnowledgeBaseSearchResult with optional unique identifiers."""
        if idx is None:
            # Legacy behavior for simple tests
            return KnowledgeBaseSearchResult(
                id="kbase_result",
                content="kbase content",
                file_path="/kbase/path",
                title="kbase Title",
                source="kbase",
                score=score,
                metadata={"created_at": "2024-01-01"},
            )
        # Unique identifiers for deduplication tests
        return KnowledgeBaseSearchResult(
            id=f"kbase_result_{idx}",
            content=f"kbase content for result {idx} with enough text to meet coverage requirements and pass the sufficiency threshold calculation",
            file_path=f"/kbase/path/{idx}",
            title=f"kbase Title {idx}",
            source="kbase",
            score=score,
            metadata={"created_at": "2024-01-01"},
        )

    def test_search_returns_kbase_results_when_sufficient(self, engine):
        """Test search returns kbase results when sufficient."""
        # High-scoring kbase results with unique identifiers and long content
        kbase_results = [self.make_kbase_result(0.9, idx=i) for i in range(10)]
        engine.kbase.search = Mock(return_value=kbase_results)

        results = engine.search("how to test")

        # Should return exactly 10 kbase results without web search
        assert len(results) == 10
        assert all(r.source == "kbase" for r in results)
        engine.searxng.search.assert_not_called()

    def test_search_triggers_web_search_when_insufficient(self, mock_kbase, mock_searxng, engine):
        """Test search triggers web search when kbase insufficient."""
        # Low kbase results
        kbase_results = [self.make_kbase_result(0.3) for _ in range(2)]
        mock_kbase.search = Mock(return_value=kbase_results)

        # Set up web search
        web_result = Mock()
        web_result.url = "https://example.com/article"
        web_result.title = "Web Article"
        mock_searxng.search = Mock(return_value=[web_result])

        results = engine.search("explore new topics")

        # Should have triggered web search
        mock_searxng.search.assert_called()

    def test_iteration_stops_at_max_iterations_boundary(self, mock_kbase, mock_searxng, mock_converter, mock_cache):
        """Test iteration stops at max_iterations boundary."""
        config = {"max_iterations": 2, "max_time_seconds": 180}

        # kbase always returns insufficient results
        kbase_results = [self.make_kbase_result(0.1)]
        mock_kbase.search = Mock(return_value=kbase_results)

        # Web search always returns new URL
        web_result = Mock()
        web_result.url = "https://example.com/new"
        web_result.title = "New Article"
        mock_searxng.search = Mock(return_value=[web_result])

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config=config,
        )

        # Run search
        results = engine.search("test query")

        # Should have stopped at max iterations
        # Web search may be called multiple times but limited by boundary
        assert mock_searxng.search.call_count <= config["max_iterations"] + 1

    def test_kbase_auto_ingestion_from_web_results(self, mock_kbase, mock_searxng, mock_converter, mock_cache, config):
        """Test kbase auto-ingestion from web results."""
        # kbase returns low results
        kbase_results = [self.make_kbase_result(0.2)]
        mock_kbase.search = Mock(return_value=kbase_results)

        # Web returns new URL
        web_result = Mock()
        web_result.url = "https://example.com/ingest"
        web_result.title = "Ingest Article"
        mock_searxng.search = Mock(return_value=[web_result])

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config={"max_iterations": 1},
        )

        results = engine.search("test")

        # kbase should have ingested web content
        mock_kbase.ingest_file_from_content.assert_called()

    def test_iterative_search_saves_web_results_to_cache(self, mock_kbase, mock_searxng, mock_converter, config):
        """Test iterative search persists converted web content into cache."""
        mock_kbase.search = Mock(return_value=[self.make_kbase_result(0.1)])

        web_result = Mock()
        web_result.url = "https://example.com/iterative"
        web_result.title = "Iterative Article"
        web_result.engine = "duckduckgo"
        web_result.published_date = "2026-04-28"
        mock_searxng.search = Mock(return_value=[web_result])

        mock_cache = Mock()
        mock_cache.exists = Mock(return_value=False)
        mock_cache.save = Mock(return_value="/tmp/iterative.md")

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config={"max_iterations": 1, "max_results": 5, "kbase_top_k": 5},
        )

        results = engine.search("test")

        mock_cache.save.assert_called_once()
        assert any(entry.file_path == "/tmp/iterative.md" for entry in results)
        assert any(entry.cached is False for entry in results)

    def test_iterative_search_skips_repeated_urls_within_same_run(self, mock_kbase, mock_converter, mock_cache):
        """Test iterative search does not reconvert the same URL across iterations."""
        mock_kbase.search = Mock(return_value=[self.make_kbase_result(0.1)])

        web_result = Mock()
        web_result.url = "https://repeat.example.com"
        web_result.title = "Repeat"
        web_result.engine = "google"
        web_result.published_date = ""

        mock_searxng = Mock()
        mock_searxng.search = Mock(return_value=[web_result])
        mock_cache.exists = Mock(return_value=False)
        mock_cache.save = Mock(return_value="/tmp/repeat.md")

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config={"max_iterations": 3, "max_results": 5, "kbase_top_k": 5},
        )

        engine.search("test")

        assert mock_converter.convert_url.call_count == 1

    def test_convergence_stops_iteration(self, mock_kbase, mock_searxng, mock_converter, mock_cache):
        """Test convergence stops iteration early."""
        config = {"max_iterations": 10}

        # kbase returns same results each time
        kbase_results = [self.make_kbase_result(0.5)]
        mock_kbase.search = Mock(return_value=kbase_results)

        # Web search returns same URL each time (will trigger convergence)
        web_result = Mock()
        web_result.url = "https://same-url.com"
        web_result.title = "Same Article"
        mock_searxng.search = Mock(return_value=[web_result])

        # Converter returns same content
        mock_converter.convert_url = Mock(return_value="Same content every time")

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config=config,
        )

        results = engine.search("test")

        # After convergence, should stop early (not hit max_iterations)
        # Note: Due to convergence logic, iteration may stop before max
        assert mock_searxng.search.call_count < config["max_iterations"]

    def test_convert_kbase_results(self, engine):
        """Test _convert_kbase_results method."""
        kbase_results = [self.make_kbase_result(0.9)]

        converted = engine._convert_kbase_results(kbase_results)

        assert len(converted) == 1
        assert isinstance(converted[0], ResultEntry)
        assert converted[0].url == "/kbase/path"
        assert converted[0].title == "kbase Title"

    def test_combine_results_deduplication(self, engine):
        """Test _combine_results deduplicates by file_path."""
        kbase_results = [self.make_kbase_result(0.9)]

        # Web entry with same file_path
        web_entry = ResultEntry(
            url="https://example.com",
            title="Web Title",
            content="Web content",
            file_path="/kbase/path",  # Same as kbase
            cached=True,
            source="web",
            cached_date="2024-01-01",
        )

        combined = engine._combine_results(kbase_results, [web_entry])

        # Should deduplicate, kbase entry wins
        assert len(combined) == 1
        assert combined[0].source == "kbase"

    def test_combine_results_different_paths(self, engine):
        """Test _combine_results keeps entries with different paths."""
        kbase_results = [self.make_kbase_result(0.9)]

        web_entry = ResultEntry(
            url="https://example.com",
            title="Web Title",
            content="Web content",
            file_path="/different/path",  # Different from kbase
            cached=True,
            source="web",
            cached_date="2024-01-01",
        )

        combined = engine._combine_results(kbase_results, [web_entry])

        # Both should be included
        assert len(combined) == 2
        sources = [r.source for r in combined]
        assert "kbase" in sources
        assert "web" in sources

    def test_convert_kbase_results_prefers_original_url_metadata(self, engine):
        """Test converted kbase results keep original web URL when available."""
        kbase_result = KnowledgeBaseSearchResult(
            id="web_1",
            content="Converted web content",
            file_path="/tmp/store/web.md",
            title="Web Title",
            source="web",
            score=0.9,
            metadata={"url": "https://example.com/article", "created_at": "2024-01-01"},
        )

        converted = engine._convert_kbase_results([kbase_result])

        assert converted[0].url == "https://example.com/article"
        assert converted[0].file_path == "/tmp/store/web.md"

    def test_combine_results_deduplicates_kbase_chunks_by_file_path(self, engine):
        """Test kbase chunk results from the same file collapse into one output entry."""
        kbase_results = [
            KnowledgeBaseSearchResult(
                id="chunk_1",
                content="chunk one",
                file_path="/tmp/store/web.md",
                title="Web Title",
                source="web",
                score=0.9,
                metadata={"url": "https://example.com/article", "created_at": "2024-01-01"},
            ),
            KnowledgeBaseSearchResult(
                id="chunk_2",
                content="chunk two",
                file_path="/tmp/store/web.md",
                title="Web Title",
                source="web",
                score=0.8,
                metadata={"url": "https://example.com/article", "created_at": "2024-01-01"},
            ),
        ]

        combined = engine._combine_results(kbase_results, [])

        assert len(combined) == 1
        assert combined[0].url == "https://example.com/article"

    def test_cache_check_prevents_duplicate_conversion(self, mock_kbase, mock_searxng, mock_converter, mock_cache):
        """Test cache check prevents duplicate conversion."""
        # kbase insufficient
        mock_kbase.search = Mock(return_value=[self.make_kbase_result(0.1)])

        # URL already cached
        web_result = Mock()
        web_result.url = "https://cached-url.com"
        web_result.title = "Cached Article"
        mock_searxng.search = Mock(return_value=[web_result])
        mock_cache.exists = Mock(return_value=True)  # Already cached

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config={"max_iterations": 1},
        )

        results = engine.search("test")

        # Converter should not be called for cached URL
        mock_converter.convert_url.assert_not_called()

    def test_empty_web_search_results(self, mock_kbase, mock_searxng, mock_converter, mock_cache, config):
        """Test handling of empty web search results."""
        # kbase insufficient
        mock_kbase.search = Mock(return_value=[self.make_kbase_result(0.1)])

        # Web search returns empty
        mock_searxng.search = Mock(return_value=[])

        engine = IterativeSearchEngine(
            kbase=mock_kbase,
            searxng_client=mock_searxng,
            converter=mock_converter,
            cache=mock_cache,
            config=config,
        )

        results = engine.search("test")

        # Should still return kbase results
        assert len(results) >= 1


class TestConvergenceResult:
    """Tests for ConvergenceResult dataclass."""

    def test_convergence_result_creation(self):
        """Test ConvergenceResult dataclass creation."""
        result = ConvergenceResult(
            is_converged=True,
            score_delta=0.05,
            overlap_ratio=0.85,
            redundancy_ratio=0.70,
            factors_met=["score_delta", "overlap"],
        )

        assert result.is_converged is True
        assert result.score_delta == 0.05
        assert result.overlap_ratio == 0.85
        assert result.redundancy_ratio == 0.70
        assert result.factors_met == ["score_delta", "overlap"]

    def test_convergence_result_not_converged(self):
        """Test ConvergenceResult for non-converged state."""
        result = ConvergenceResult(
            is_converged=False,
            score_delta=0.5,
            overlap_ratio=0.2,
            redundancy_ratio=0.1,
            factors_met=["score_delta"],  # Only one factor
        )

        assert result.is_converged is False
        assert len(result.factors_met) == 1
