"""Content optimization compatibility shim.

Delegates to ksearch.content_optimization package.
"""

from ksearch.content_optimization.evaluator import QualityEvaluator
from ksearch.content_optimization.ollama_client import OllamaChatClient
from ksearch.content_optimization.optimizer import ContentOptimizer

__all__ = [
    "OllamaChatClient",
    "QualityEvaluator",
    "ContentOptimizer",
]
