"""Compatibility facade for iterative search components."""

from ksearch.iterative_convergence import (
    ConvergenceEvaluator,
    ConvergenceResult,
    IterationBoundary,
)
from ksearch.iterative_engine import IterativeSearchEngine
from ksearch.iterative_query import QueryClassifier
from ksearch.iterative_sufficiency import SufficiencyEvaluator

__all__ = [
    "ConvergenceEvaluator",
    "ConvergenceResult",
    "IterationBoundary",
    "IterativeSearchEngine",
    "QueryClassifier",
    "SufficiencyEvaluator",
]
