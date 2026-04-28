"""Iterative search convergence and boundary management.

Provides classes for multi-factor convergence detection and hard limit
enforcement during iterative knowledge base search cycles.
"""

from dataclasses import dataclass
from typing import Optional

from ksearch.cache import CacheManager
from ksearch.converter import ContentConverter
from ksearch.kbase import KnowledgeBase, KnowledgeBaseSearchResult
from ksearch.models import ResultEntry
from ksearch.searxng import SearXNGClient


@dataclass
class ConvergenceResult:
    """Result of convergence check."""
    is_converged: bool
    score_delta: float
    overlap_ratio: float
    redundancy_ratio: float
    factors_met: list[str]


class ConvergenceEvaluator:
    """Multi-factor convergence detection for iterative search.

    Evaluates convergence based on three factors:
    - score_delta: Change in average similarity scores between iterations
    - overlap_ratio: Percentage of same results between iterations
    - redundancy_ratio: Percentage of duplicate content between iterations

    Convergence is reached when any two of three factors meet thresholds.
    """

    def __init__(
        self,
        score_delta_threshold: float = 0.05,
        overlap_threshold: float = 0.80,
        redundancy_threshold: float = 0.70,
    ):
        """Initialize convergence evaluator with thresholds.

        Args:
            score_delta_threshold: Max acceptable score change (default 5%)
            overlap_threshold: Min overlap ratio (default 80%)
            redundancy_threshold: Min redundancy ratio (default 70%)
        """
        self.score_delta_threshold = score_delta_threshold
        self.overlap_threshold = overlap_threshold
        self.redundancy_threshold = redundancy_threshold

    def check_convergence(
        self,
        prev_results: Optional[list[KnowledgeBaseSearchResult]],
        current_results: list[KnowledgeBaseSearchResult],
    ) -> ConvergenceResult:
        """Check if search has converged between iterations.

        Args:
            prev_results: Results from previous iteration (None for first)
            current_results: Results from current iteration

        Returns:
            ConvergenceResult with convergence status and metrics
        """
        if prev_results is None or len(prev_results) == 0:
            return ConvergenceResult(
                is_converged=False,
                score_delta=1.0,
                overlap_ratio=0.0,
                redundancy_ratio=0.0,
                factors_met=[],
            )

        # Calculate score delta
        prev_avg_score = self._average_score(prev_results)
        curr_avg_score = self._average_score(current_results)
        score_delta = abs(curr_avg_score - prev_avg_score) / max(prev_avg_score, 0.001)

        # Calculate overlap ratio (same result IDs)
        prev_ids = {r.id for r in prev_results}
        curr_ids = {r.id for r in current_results}
        overlap_count = len(prev_ids & curr_ids)
        overlap_ratio = overlap_count / max(len(prev_ids), 1)

        # Calculate redundancy ratio (similar content)
        redundancy_ratio = self._calculate_redundancy(prev_results, current_results)

        # Check which factors are met
        factors_met = []
        if score_delta < self.score_delta_threshold:
            factors_met.append("score_delta")
        if overlap_ratio >= self.overlap_threshold:
            factors_met.append("overlap")
        if redundancy_ratio >= self.redundancy_threshold:
            factors_met.append("redundancy")

        # Convergence when any two factors met
        is_converged = len(factors_met) >= 2

        return ConvergenceResult(
            is_converged=is_converged,
            score_delta=score_delta,
            overlap_ratio=overlap_ratio,
            redundancy_ratio=redundancy_ratio,
            factors_met=factors_met,
        )

    def _average_score(self, results: list[KnowledgeBaseSearchResult]) -> float:
        """Calculate average similarity score."""
        if not results:
            return 0.0
        return sum(r.score for r in results) / len(results)

    def _calculate_redundancy(
        self,
        prev_results: list[KnowledgeBaseSearchResult],
        current_results: list[KnowledgeBaseSearchResult],
    ) -> float:
        """Calculate content redundancy ratio between iterations.

        Measures how much content overlap exists between result sets.
        Uses simple content hash comparison for efficiency.
        """
        if not prev_results or not current_results:
            return 0.0

        prev_hashes = {hash(r.content[:200]) for r in prev_results}
        curr_hashes = {hash(r.content[:200]) for r in current_results}

        common_hashes = len(prev_hashes & curr_hashes)
        return common_hashes / max(len(prev_hashes), 1)


class IterationBoundary:
    """Hard limit enforcement for iterative search.

    Enforces maximum iteration count and time limits to prevent
    infinite loops during iterative search cycles.
    """

    def __init__(
        self,
        max_iterations: int = 5,
        max_time_seconds: float = 180.0,
    ):
        """Initialize iteration boundary limits.

        Args:
            max_iterations: Maximum number of iterations allowed
            max_time_seconds: Maximum elapsed time in seconds
        """
        self.max_iterations = max_iterations
        self.max_time_seconds = max_time_seconds

    def check_limits(
        self,
        iteration_count: int,
        elapsed_time: float,
    ) -> bool:
        """Check if iteration limits have been exceeded.

        Args:
            iteration_count: Current iteration number
            elapsed_time: Elapsed time in seconds

        Returns:
            True if should stop (limits exceeded), False otherwise
        """
        if iteration_count >= self.max_iterations:
            return True
        if elapsed_time >= self.max_time_seconds:
            return True
        return False


class QueryClassifier:
    """Classifies search queries as fact-seeking or exploration queries.

    Uses keyword matching and query length to determine query type.
    Fact queries are short and specific; exploration queries are broad.
    """

    # Keywords indicating fact-seeking queries
    FACT_KEYWORDS = [
        "如何", "是什么", "定义", "怎么", "怎样",
        "how to", "what is", "definition", "who is", "when",
        "where", "what are", "explain",
    ]

    # Keywords indicating exploration queries
    EXPLORATION_KEYWORDS = [
        "探索", "研究", "对比", "分析", "综述",
        "explore", "compare", "analyze", "review", "overview",
        "survey", "investigate", "deep dive",
    ]

    def classify(self, query: str) -> str:
        """Classify a query as fact-seeking or exploration.

        Args:
            query: Search query string

        Returns:
            "fact" or "exploration"
        """
        query_lower = query.lower().strip()
        word_count = len(query.split())

        # Check for exploration keywords first (explicit intent overrides length)
        for keyword in self.EXPLORATION_KEYWORDS:
            if keyword in query_lower:
                return "exploration"

        # Check for fact keywords
        for keyword in self.FACT_KEYWORDS:
            if keyword in query_lower:
                return "fact"

        # Short queries (< 5 words) are typically fact-seeking
        if word_count < 5:
            return "fact"

        # Default: exploration (conservative - requires more results)
        return "exploration"


class SufficiencyEvaluator:
    """Evaluates sufficiency of knowledge base search results.

    Uses weighted scoring combining vector similarity, result count,
    and content coverage to determine if results are sufficient.
    """

    # Weight configuration
    WEIGHT_VECTOR_SIMILARITY = 0.4
    WEIGHT_RESULT_COUNT = 0.3
    WEIGHT_CONTENT_COVERAGE = 0.3

    # Thresholds by query type
    FACT_THRESHOLD = 0.7
    EXPLORATION_THRESHOLD = 0.4

    # Result count scoring thresholds
    MIN_RESULTS_FOR_MAX_SCORE = 10
    MIN_RESULTS_FOR_MIN_SCORE = 3

    def __init__(
        self,
        fact_threshold: float = 0.7,
        exploration_threshold: float = 0.4,
        weights: Optional[dict[str, float]] = None,
    ):
        """Initialize sufficiency evaluation thresholds and weights."""
        weights = weights or {}
        self.fact_threshold = fact_threshold
        self.exploration_threshold = exploration_threshold
        self.vector_weight = weights.get("vector", self.WEIGHT_VECTOR_SIMILARITY)
        self.count_weight = weights.get("count", self.WEIGHT_RESULT_COUNT)
        self.coverage_weight = weights.get("coverage", self.WEIGHT_CONTENT_COVERAGE)

        total_weight = self.vector_weight + self.count_weight + self.coverage_weight
        if total_weight > 0 and abs(total_weight - 1.0) > 1e-9:
            self.vector_weight /= total_weight
            self.count_weight /= total_weight
            self.coverage_weight /= total_weight

    def score(self, kbase_results: list[KnowledgeBaseSearchResult]) -> float:
        """Calculate sufficiency score for kbase search results.

        Args:
            kbase_results: List of KnowledgeBaseSearchResult objects with score field

        Returns:
            Sufficiency score (0.0-1.0)
        """
        if not kbase_results:
            return 0.0

        # Vector similarity component (average of scores)
        similarity_scores = [r.score for r in kbase_results]
        avg_similarity = sum(similarity_scores) / len(similarity_scores)
        similarity_component = avg_similarity * self.vector_weight

        # Result count component (normalized)
        count = len(kbase_results)
        if count >= self.MIN_RESULTS_FOR_MAX_SCORE:
            count_score = 1.0
        elif count <= self.MIN_RESULTS_FOR_MIN_SCORE:
            count_score = 0.3
        else:
            # Linear interpolation between min and max thresholds
            ratio = (count - self.MIN_RESULTS_FOR_MIN_SCORE) / (
                self.MIN_RESULTS_FOR_MAX_SCORE - self.MIN_RESULTS_FOR_MIN_SCORE
            )
            count_score = 0.3 + 0.7 * ratio
        count_component = count_score * self.count_weight

        # Content coverage component (average content length normalized)
        avg_content_length = sum(len(r.content) for r in kbase_results) / len(kbase_results)
        # Normalize: 500 chars = full coverage
        coverage_score = min(avg_content_length / 500.0, 1.0)
        coverage_component = coverage_score * self.coverage_weight

        return similarity_component + count_component + coverage_component

    def get_threshold(self, query_type: str) -> float:
        """Get sufficiency threshold for query type.

        Args:
            query_type: "fact" or "exploration"

        Returns:
            Threshold value (0.7 for fact, 0.4 for exploration)
        """
        if query_type == "fact":
            return self.fact_threshold
        return self.exploration_threshold

    def is_sufficient(self, score: float, threshold: float) -> bool:
        """Check if score meets threshold.

        Args:
            score: Calculated sufficiency score
            threshold: Threshold value to compare against

        Returns:
            True if score >= threshold
        """
        return score >= threshold

class IterativeSearchEngine:
    """Orchestrates iterative kbase-first search with web fallback.

    Implements the sufficiency-driven iteration loop:
    1. Classify query → determine threshold
    2. kbase search → evaluate sufficiency
    3. If insufficient → web search + ingest
    4. Repeat until sufficient or boundaries reached
    """

    def __init__(
        self,
        kbase: KnowledgeBase,
        searxng_client: SearXNGClient,
        converter: ContentConverter,
        cache: CacheManager,
        config: dict,
    ):
        """Initialize the iterative search engine.

        Args:
            kbase: KnowledgeBase instance for kbase search and ingestion
            searxng_client: SearXNGClient for web search
            converter: ContentConverter for URL-to-markdown conversion
            cache: CacheManager for URL cache checking
            config: Configuration dict with max_iterations, max_time_seconds, etc.
        """
        self.kbase = kbase
        self.searxng = searxng_client
        self.converter = converter
        self.cache = cache
        self.query_classifier = QueryClassifier()
        self.config = config
        self.sufficiency = SufficiencyEvaluator(
            fact_threshold=config.get("fact_threshold", SufficiencyEvaluator.FACT_THRESHOLD),
            exploration_threshold=config.get(
                "exploration_threshold",
                SufficiencyEvaluator.EXPLORATION_THRESHOLD,
            ),
            weights=config.get("scoring_weights"),
        )
        self.convergence = ConvergenceEvaluator()
        self.boundary = IterationBoundary(
            max_iterations=config.get("max_iterations", 5),
            max_time_seconds=config.get("max_time_seconds", 180),
        )

    def search(self, query: str) -> list[ResultEntry]:
        """Execute iterative kbase-first search.

        Args:
            query: Search query string

        Returns:
            Combined results from kbase and web searches as ResultEntry list
        """
        import time
        start_time = time.time()
        kbase_top_k = self.config.get("kbase_top_k", 10)
        max_results = self.config.get("max_results", 5)

        # 1. Classify query
        query_type = self.query_classifier.classify(query)
        threshold = self.sufficiency.get_threshold(query_type)

        # 2. Initial kbase search
        kbase_results = self.kbase.search(query, top_k=kbase_top_k)

        # 3. Evaluate sufficiency
        score = self.sufficiency.score(kbase_results)

        # If kbase sufficient, return early
        if self.sufficiency.is_sufficient(score, threshold):
            return self._convert_kbase_results(kbase_results)

        # 4. Iteration loop
        iteration = 0
        prev_results = kbase_results
        all_web_entries = []
        seen_web_urls = set()

        while not self.boundary.check_limits(iteration, time.time() - start_time):
            # Web search
            web_urls = self.searxng.search(query, max_results=max_results)

            # Convert and filter URLs
            ingested_any = False
            for url_result in web_urls:
                if url_result.url in seen_web_urls or self.cache.exists(url_result.url):
                    continue
                seen_web_urls.add(url_result.url)

                content = self.converter.convert_url(url_result.url)
                if not content:
                    continue

                file_path = self.cache.save(
                    url=url_result.url,
                    content=content,
                    keyword=query,
                    metadata={
                        "title": getattr(url_result, "title", ""),
                        "engine": getattr(url_result, "engine", "web"),
                        "published_date": getattr(url_result, "published_date", ""),
                    },
                )

                self.kbase.ingest_file_from_content(
                    content,
                    metadata={
                        "source": "web",
                        "url": url_result.url,
                        "title": getattr(url_result, "title", ""),
                        "file_path": file_path,
                        "published_date": getattr(url_result, "published_date", ""),
                    },
                )
                ingested_any = True

                all_web_entries.append(ResultEntry(
                    url=url_result.url,
                    title=getattr(url_result, "title", ""),
                    content=content,
                    file_path=file_path,
                    cached=False,
                    source=getattr(url_result, "engine", "web"),
                    cached_date="",
                ))

            if not ingested_any:
                break

            iteration += 1
            current_results = self.kbase.search(query, top_k=kbase_top_k)
            score = self.sufficiency.score(current_results)
            if self.sufficiency.is_sufficient(score, threshold):
                kbase_results = current_results
                break

            # Check convergence
            convergence = self.convergence.check_convergence(prev_results, current_results)
            if convergence.is_converged:
                kbase_results = current_results
                break

            prev_results = current_results
            kbase_results = current_results

        # 5. Return combined results
        return self._combine_results(kbase_results, all_web_entries)

    def _convert_kbase_results(self, kbase_results: list[KnowledgeBaseSearchResult]) -> list[ResultEntry]:
        """Convert KnowledgeBaseSearchResult to ResultEntry format."""
        entries = []
        seen_paths = set()
        for result in kbase_results:
            if result.file_path in seen_paths:
                continue
            seen_paths.add(result.file_path)
            entries.append(ResultEntry(
                url=result.metadata.get("url", result.file_path) if result.metadata else result.file_path,
                title=result.title or "",
                content=result.content,
                file_path=result.file_path,
                cached=True,
                source=result.source or "kbase",
                cached_date=result.metadata.get("created_at", "") if result.metadata else "",
            ))
        return entries

    def _combine_results(
        self,
        kbase_results: list[KnowledgeBaseSearchResult],
        web_entries: list[ResultEntry],
    ) -> list[ResultEntry]:
        """Combine kbase and web results, deduplicating by URL/file_path."""
        kbase_entries = self._convert_kbase_results(kbase_results)

        # Deduplicate: prefer kbase entries over web entries with same path
        seen_paths = {e.file_path for e in kbase_entries}
        combined = kbase_entries + [e for e in web_entries if e.file_path not in seen_paths]

        return combined
