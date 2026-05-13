"""Sufficiency scoring helpers for iterative search."""

from typing import Optional

from ksearch.kbase import KnowledgeBaseSearchResult


class SufficiencyEvaluator:
    """Evaluates sufficiency of knowledge base search results."""

    WEIGHT_VECTOR_SIMILARITY = 0.4
    WEIGHT_RESULT_COUNT = 0.3
    WEIGHT_CONTENT_COVERAGE = 0.3

    FACT_THRESHOLD = 0.7
    EXPLORATION_THRESHOLD = 0.4
    MIN_AVG_RELEVANCE = 0.2
    MIN_TOP_RELEVANCE = 0.45

    MIN_RESULTS_FOR_MAX_SCORE = 10
    MIN_RESULTS_FOR_MIN_SCORE = 3

    def __init__(
        self,
        fact_threshold: float = 0.7,
        exploration_threshold: float = 0.4,
        weights: Optional[dict[str, float]] = None,
    ):
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
        if not kbase_results:
            return 0.0

        relevance_scores = [self._relevance_score(result) for result in kbase_results]
        avg_similarity = sum(relevance_scores) / len(relevance_scores)
        top_similarity = max(relevance_scores)
        similarity_component = avg_similarity * self.vector_weight

        # Count and content length should only help once the retrieved set is
        # meaningfully relevant to the query. Otherwise long off-topic chunks
        # can incorrectly block the web fallback path.
        if (
            avg_similarity < self.MIN_AVG_RELEVANCE
            or top_similarity < self.MIN_TOP_RELEVANCE
        ):
            return similarity_component

        count = len(kbase_results)
        if count >= self.MIN_RESULTS_FOR_MAX_SCORE:
            count_score = 1.0
        elif count <= self.MIN_RESULTS_FOR_MIN_SCORE:
            count_score = 0.3
        else:
            ratio = (count - self.MIN_RESULTS_FOR_MIN_SCORE) / (
                self.MIN_RESULTS_FOR_MAX_SCORE - self.MIN_RESULTS_FOR_MIN_SCORE
            )
            count_score = 0.3 + 0.7 * ratio
        count_component = count_score * self.count_weight

        avg_content_length = sum(len(result.content) for result in kbase_results) / len(kbase_results)
        coverage_score = min(avg_content_length / 500.0, 1.0)
        coverage_component = coverage_score * self.coverage_weight

        return similarity_component + count_component + coverage_component

    def get_threshold(self, query_type: str) -> float:
        return self.fact_threshold if query_type == "fact" else self.exploration_threshold

    def is_sufficient(self, score: float, threshold: float) -> bool:
        return score >= threshold

    @staticmethod
    def _relevance_score(result: KnowledgeBaseSearchResult) -> float:
        metadata = result.metadata or {}

        rerank_score = metadata.get("rerank_score")
        if rerank_score is not None:
            return float(rerank_score)

        vector_score = metadata.get("vector_score")
        if vector_score is not None and float(vector_score) > 0:
            return float(vector_score)

        return max(float(result.score), 0.0)


__all__ = ["SufficiencyEvaluator"]
