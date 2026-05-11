"""Tests for ContentOptimizer."""

import json
import time
from unittest.mock import MagicMock, call, patch

import pytest

from ksearch.content_optimization.optimizer import ContentOptimizer
from ksearch.models import OptimizationResult, QualityAssessment, ResultEntry


def _make_result(content: str, title: str = "Test") -> ResultEntry:
    return ResultEntry(
        url="http://example.com", title=title, content=content,
        file_path="/tmp/test.md", cached=False, source="web", cached_date="",
    )


class TestContentOptimizer:
    def _make_optimizer(self, evaluation_sequence: list[dict], synthesis: str = "synthesized") -> ContentOptimizer:
        mock_evaluator = MagicMock()
        assessments = []
        for ev in evaluation_sequence:
            assessments.append(QualityAssessment(**ev))
        mock_evaluator.evaluate.side_effect = assessments
        mock_evaluator.should_continue.side_effect = [
            ev.get("action") == "REFINE" and ev.get("confidence", 0) < 0.8
            for ev in evaluation_sequence
        ]

        mock_client = MagicMock()
        mock_client.chat.return_value = synthesis

        config = {
            "optimization_max_iterations": 3,
            "optimization_max_time_seconds": 120,
        }
        return ContentOptimizer(evaluator=mock_evaluator, client=mock_client, config=config)

    def test_optimize_stops_on_complete(self):
        optimizer = self._make_optimizer([
            {"action": "COMPLETE", "confidence": 0.9, "gaps": [], "refinement_query": "", "summary": "Good"}
        ])
        search_fn = MagicMock(return_value=[_make_result("content")])

        result = optimizer.optimize("test query", search_fn)

        assert isinstance(result, OptimizationResult)
        assert result.iterations_used == 1
        search_fn.assert_called_once_with("test query")

    def test_optimize_refines_and_stops(self):
        optimizer = self._make_optimizer([
            {"action": "REFINE", "confidence": 0.5, "gaps": ["gap1"], "refinement_query": "gap1 query", "summary": "Incomplete"},
            {"action": "COMPLETE", "confidence": 0.9, "gaps": [], "refinement_query": "", "summary": "Good"},
        ])
        search_fn = MagicMock(side_effect=[
            [_make_result("initial content")],
            [_make_result("gap1 content")],
        ])

        result = optimizer.optimize("test query", search_fn)

        assert result.iterations_used == 2
        assert search_fn.call_count == 2

    def test_optimize_stops_at_max_iterations(self):
        optimizer = self._make_optimizer([
            {"action": "REFINE", "confidence": 0.3, "gaps": ["g"], "refinement_query": "q", "summary": "s"},
            {"action": "REFINE", "confidence": 0.4, "gaps": ["g"], "refinement_query": "q", "summary": "s"},
            {"action": "REFINE", "confidence": 0.5, "gaps": ["g"], "refinement_query": "q", "summary": "s"},
        ])
        search_fn = MagicMock(return_value=[_make_result("content")])

        result = optimizer.optimize("test query", search_fn)

        assert result.iterations_used == 3

    def test_optimize_uses_initial_results(self):
        optimizer = self._make_optimizer([
            {"action": "COMPLETE", "confidence": 0.9, "gaps": [], "refinement_query": "", "summary": "Good"}
        ])
        search_fn = MagicMock()
        initial = [_make_result("pre-fetched")]

        result = optimizer.optimize("test query", search_fn, initial_results=initial)

        search_fn.assert_not_called()

    def test_optimize_content_without_search(self):
        optimizer = self._make_optimizer([
            {"action": "COMPLETE", "confidence": 0.9, "gaps": [], "refinement_query": "", "summary": "Good"}
        ])

        result = optimizer.optimize_content("query", "existing content to evaluate")

        assert isinstance(result, OptimizationResult)
        assert result.final_content == "synthesized"

    def test_aggregate_content(self):
        optimizer = self._make_optimizer([])
        results = [_make_result("content A"), _make_result("content B", title="B")]

        aggregated = optimizer._aggregate_content(results)
        assert "content A" in aggregated
        assert "content B" in aggregated

    def test_optimize_logs_iteration_events(self):
        optimizer = self._make_optimizer([
            {"action": "COMPLETE", "confidence": 0.9, "gaps": [], "refinement_query": "", "summary": "Good"}
        ])
        search_fn = MagicMock(return_value=[_make_result("content")])

        with patch("ksearch.content_optimization.optimizer.log_event") as log_event:
            optimizer.optimize("test query", search_fn)

        assert any(call.args[1] == "optimization_start" for call in log_event.call_args_list)
