"""Convergence and boundary helpers for iterative search."""

from dataclasses import dataclass
from typing import Optional

from ksearch.kbase import KnowledgeBaseSearchResult


@dataclass
class ConvergenceResult:
    """Result of convergence check."""
    is_converged: bool
    score_delta: float
    overlap_ratio: float
    redundancy_ratio: float
    factors_met: list[str]


class ConvergenceEvaluator:
    """Multi-factor convergence detection for iterative search."""

    def __init__(
        self,
        score_delta_threshold: float = 0.05,
        overlap_threshold: float = 0.80,
        redundancy_threshold: float = 0.70,
    ):
        self.score_delta_threshold = score_delta_threshold
        self.overlap_threshold = overlap_threshold
        self.redundancy_threshold = redundancy_threshold

    def check_convergence(
        self,
        prev_results: Optional[list[KnowledgeBaseSearchResult]],
        current_results: list[KnowledgeBaseSearchResult],
    ) -> ConvergenceResult:
        if prev_results is None or len(prev_results) == 0:
            return ConvergenceResult(
                is_converged=False,
                score_delta=1.0,
                overlap_ratio=0.0,
                redundancy_ratio=0.0,
                factors_met=[],
            )

        prev_avg_score = self._average_score(prev_results)
        curr_avg_score = self._average_score(current_results)
        score_delta = abs(curr_avg_score - prev_avg_score) / max(prev_avg_score, 0.001)

        prev_ids = {result.id for result in prev_results}
        curr_ids = {result.id for result in current_results}
        overlap_count = len(prev_ids & curr_ids)
        overlap_ratio = overlap_count / max(len(prev_ids), 1)

        redundancy_ratio = self._calculate_redundancy(prev_results, current_results)

        factors_met = []
        if score_delta < self.score_delta_threshold:
            factors_met.append("score_delta")
        if overlap_ratio >= self.overlap_threshold:
            factors_met.append("overlap")
        if redundancy_ratio >= self.redundancy_threshold:
            factors_met.append("redundancy")

        return ConvergenceResult(
            is_converged=len(factors_met) >= 2,
            score_delta=score_delta,
            overlap_ratio=overlap_ratio,
            redundancy_ratio=redundancy_ratio,
            factors_met=factors_met,
        )

    def _average_score(self, results: list[KnowledgeBaseSearchResult]) -> float:
        if not results:
            return 0.0
        return sum(result.score for result in results) / len(results)

    def _calculate_redundancy(
        self,
        prev_results: list[KnowledgeBaseSearchResult],
        current_results: list[KnowledgeBaseSearchResult],
    ) -> float:
        if not prev_results or not current_results:
            return 0.0

        prev_hashes = {hash(result.content[:200]) for result in prev_results}
        curr_hashes = {hash(result.content[:200]) for result in current_results}
        return len(prev_hashes & curr_hashes) / max(len(prev_hashes), 1)


class IterationBoundary:
    """Hard limit enforcement for iterative search."""

    def __init__(
        self,
        max_iterations: int = 5,
        max_time_seconds: float = 180.0,
    ):
        self.max_iterations = max_iterations
        self.max_time_seconds = max_time_seconds

    def check_limits(
        self,
        iteration_count: int,
        elapsed_time: float,
    ) -> bool:
        return iteration_count >= self.max_iterations or elapsed_time >= self.max_time_seconds
