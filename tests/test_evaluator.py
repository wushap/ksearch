"""Tests for QualityEvaluator."""

import json
from unittest.mock import MagicMock, patch

import pytest

from ksearch.content_optimization.evaluator import QualityEvaluator
from ksearch.models import QualityAssessment


class TestQualityEvaluator:
    def _make_evaluator(self, response_json: dict) -> QualityEvaluator:
        mock_client = MagicMock()
        mock_client.chat.return_value = json.dumps(response_json)
        return QualityEvaluator(client=mock_client, confidence_threshold=0.8)

    def test_evaluate_returns_assessment(self):
        response = {
            "action": "REFINE",
            "confidence": 0.6,
            "gaps": ["missing pricing"],
            "refinement_query": "pricing info",
            "summary": "Incomplete",
        }
        evaluator = self._make_evaluator(response)
        result = evaluator.evaluate("test query", "some content")

        assert isinstance(result, QualityAssessment)
        assert result.action == "REFINE"
        assert result.confidence == 0.6
        assert result.gaps == ["missing pricing"]

    def test_evaluate_parses_json_from_llm(self):
        response = {"action": "COMPLETE", "confidence": 0.9, "gaps": [], "refinement_query": "", "summary": "Good"}
        evaluator = self._make_evaluator(response)
        result = evaluator.evaluate("query", "content")

        assert result.action == "COMPLETE"
        assert result.confidence == 0.9

    def test_evaluate_handles_malformed_json(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = "this is not json at all"
        evaluator = QualityEvaluator(client=mock_client, confidence_threshold=0.8)

        result = evaluator.evaluate("query", "content")
        assert result.action == "COMPLETE"
        assert result.confidence == 0.5
        assert "parsing failed" in result.summary.lower()

    def test_should_continue_true_when_refine_below_threshold(self):
        evaluator = self._make_evaluator({})
        assessment = QualityAssessment(
            action="REFINE", confidence=0.6, gaps=["gap"], refinement_query="q", summary="s"
        )
        assert evaluator.should_continue(assessment) is True

    def test_should_continue_false_when_complete(self):
        evaluator = self._make_evaluator({})
        assessment = QualityAssessment(
            action="COMPLETE", confidence=0.9, gaps=[], refinement_query="", summary="s"
        )
        assert evaluator.should_continue(assessment) is False

    def test_should_continue_false_when_above_threshold(self):
        evaluator = self._make_evaluator({})
        assessment = QualityAssessment(
            action="REFINE", confidence=0.85, gaps=["gap"], refinement_query="q", summary="s"
        )
        assert evaluator.should_continue(assessment) is False

    def test_evaluate_logs_action_and_confidence(self):
        response = {
            "action": "REFINE",
            "confidence": 0.6,
            "gaps": ["missing pricing"],
            "refinement_query": "pricing info",
            "summary": "Incomplete",
        }
        evaluator = self._make_evaluator(response)

        with patch("ksearch.content_optimization.evaluator.log_event") as log_event:
            evaluator.evaluate("test query", "some content")

        completion_calls = [call for call in log_event.call_args_list if call.args[1] == "evaluation_completed"]
        assert completion_calls
        payload = completion_calls[0].args[2]
        assert payload["action"] == "REFINE"
        assert payload["confidence"] == 0.6
        assert payload["gap_count"] == 1
