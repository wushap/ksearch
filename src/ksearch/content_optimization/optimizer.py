"""Iterative content optimization orchestrator."""

import logging
import time
from collections.abc import Callable

from ksearch.debug_logging import log_event
from ksearch.content_optimization.evaluator import QualityEvaluator
from ksearch.content_optimization.ollama_client import OllamaChatClient
from ksearch.content_optimization.prompts import format_synthesis_prompt
from ksearch.models import OptimizationResult, QualityAssessment, ResultEntry

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8000


class ContentOptimizer:
    """Iterative content optimization pipeline."""

    def __init__(self, evaluator: QualityEvaluator, client: OllamaChatClient, config: dict):
        self.evaluator = evaluator
        self.client = client
        self.max_iterations = config.get("optimization_max_iterations", 3)
        self.max_time_seconds = config.get("optimization_max_time_seconds", 120)

    def optimize(
        self,
        query: str,
        search_fn: Callable[[str], list[ResultEntry]],
        initial_results: list[ResultEntry] | None = None,
    ) -> OptimizationResult:
        """Run iterative content optimization with search."""
        start_time = time.time()
        results = list(initial_results) if initial_results is not None else search_fn(query)
        log_event(
            "ksearch.content_optimization.optimizer",
            "optimization_start",
            {"query": query, "initial_result_count": len(results)},
        )
        aggregated = self._aggregate_content(results)
        refinement_history = []
        assessment = QualityAssessment(
            action="COMPLETE", confidence=0.0, gaps=[], refinement_query="",
            summary="No iterations performed",
        )

        for iteration in range(1, self.max_iterations + 1):
            if time.time() - start_time > self.max_time_seconds:
                logger.info("Optimization time limit reached at iteration %d", iteration)
                log_event(
                    "ksearch.content_optimization.optimizer",
                    "optimization_stop",
                    {"iteration": iteration, "reason": "time_limit"},
                    level="WARNING",
                )
                break

            assessment = self.evaluator.evaluate(query, aggregated)
            refinement_history.append({
                "iteration": iteration,
                "confidence": assessment.confidence,
                "action": assessment.action,
                "gaps": assessment.gaps,
            })
            log_event(
                "ksearch.content_optimization.optimizer",
                "optimization_iteration",
                {
                    "iteration": iteration,
                    "confidence": assessment.confidence,
                    "action": assessment.action,
                    "gaps": assessment.gaps,
                },
            )

            if not self.evaluator.should_continue(assessment):
                log_event(
                    "ksearch.content_optimization.optimizer",
                    "optimization_stop",
                    {"iteration": iteration, "reason": "assessment_complete"},
                )
                break

            refinement_query = assessment.refinement_query or query
            new_results = search_fn(refinement_query)
            results.extend(new_results)
            aggregated = self._aggregate_content(results)

        final_content = self._synthesize(query, aggregated)
        log_event(
            "ksearch.content_optimization.optimizer",
            "optimization_complete",
            {
                "iterations_used": len(refinement_history),
                "action": assessment.action,
                "confidence": assessment.confidence,
            },
        )
        return OptimizationResult(
            original_query=query,
            final_content=final_content,
            quality=assessment,
            iterations_used=len(refinement_history),
            elapsed_seconds=time.time() - start_time,
            refinement_history=refinement_history,
        )

    def optimize_content(self, query: str, content: str) -> OptimizationResult:
        """Optimize existing content without re-searching."""
        start_time = time.time()
        log_event(
            "ksearch.content_optimization.optimizer",
            "optimization_start",
            {"query": query, "initial_result_count": 0},
        )
        refinement_history = []
        assessment = QualityAssessment(
            action="COMPLETE", confidence=0.0, gaps=[], refinement_query="",
            summary="No iterations performed",
        )

        for iteration in range(1, self.max_iterations + 1):
            if time.time() - start_time > self.max_time_seconds:
                log_event(
                    "ksearch.content_optimization.optimizer",
                    "optimization_stop",
                    {"iteration": iteration, "reason": "time_limit"},
                    level="WARNING",
                )
                break

            truncated = content[:MAX_CONTENT_CHARS]
            assessment = self.evaluator.evaluate(query, truncated)
            refinement_history.append({
                "iteration": iteration,
                "confidence": assessment.confidence,
                "action": assessment.action,
                "gaps": assessment.gaps,
            })
            log_event(
                "ksearch.content_optimization.optimizer",
                "optimization_iteration",
                {
                    "iteration": iteration,
                    "confidence": assessment.confidence,
                    "action": assessment.action,
                    "gaps": assessment.gaps,
                },
            )

            if not self.evaluator.should_continue(assessment):
                log_event(
                    "ksearch.content_optimization.optimizer",
                    "optimization_stop",
                    {"iteration": iteration, "reason": "assessment_complete"},
                )
                break

        final_content = self._synthesize(query, content[:MAX_CONTENT_CHARS])
        log_event(
            "ksearch.content_optimization.optimizer",
            "optimization_complete",
            {
                "iterations_used": len(refinement_history),
                "action": assessment.action,
                "confidence": assessment.confidence,
            },
        )
        return OptimizationResult(
            original_query=query,
            final_content=final_content,
            quality=assessment,
            iterations_used=len(refinement_history),
            elapsed_seconds=time.time() - start_time,
            refinement_history=refinement_history,
        )

    def _aggregate_content(self, results: list[ResultEntry]) -> str:
        """Combine result contents into evaluation-ready text, respecting char limits."""
        parts = []
        total = 0
        for entry in results:
            text = f"## {entry.title}\n{entry.content}\n"
            if total + len(text) > MAX_CONTENT_CHARS:
                remaining = MAX_CONTENT_CHARS - total
                if remaining > 100:
                    parts.append(text[:remaining])
                break
            parts.append(text)
            total += len(text)
        return "\n".join(parts)

    def _synthesize(self, query: str, content: str) -> str:
        """Use LLM to synthesize optimized content from aggregated results."""
        system, user = format_synthesis_prompt(query, content)
        try:
            return self.client.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        except Exception as exc:
            logger.warning("Synthesis failed: %s", exc)
            return content
