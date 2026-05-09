"""LLM-based content quality evaluator."""

import json
import logging

from ksearch.content_optimization.ollama_client import OllamaChatClient
from ksearch.content_optimization.prompts import format_evaluation_prompt
from ksearch.models import QualityAssessment

logger = logging.getLogger(__name__)


class QualityEvaluator:
    """Evaluates content quality using an LLM."""

    def __init__(self, client: OllamaChatClient, confidence_threshold: float = 0.8):
        self.client = client
        self.confidence_threshold = confidence_threshold

    def evaluate(self, query: str, content: str) -> QualityAssessment:
        """Evaluate content quality for a given query."""
        system, user = format_evaluation_prompt(query, content)

        try:
            raw = self.client.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                format_json=True,
            )
            data = json.loads(raw)
            action = data.get("action", "COMPLETE")
            if action not in ("REFINE", "COMPLETE"):
                logger.warning("Unexpected action from LLM: %s, defaulting to COMPLETE", action)
                action = "COMPLETE"
            return QualityAssessment(
                action=action,
                confidence=float(data.get("confidence", 0.5)),
                gaps=data.get("gaps", []),
                refinement_query=data.get("refinement_query", ""),
                summary=data.get("summary", ""),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Failed to parse evaluation response: %s", exc)
            return QualityAssessment(
                action="COMPLETE",
                confidence=0.5,
                gaps=[],
                refinement_query="",
                summary=f"Evaluation parsing failed: {exc}",
            )

    def should_continue(self, assessment: QualityAssessment) -> bool:
        """Check if optimization should continue."""
        return assessment.action == "REFINE" and assessment.confidence < self.confidence_threshold
