"""Compatibility shim for iterative convergence helpers."""

from ksearch.iterative_flow.convergence import (
    ConvergenceEvaluator,
    ConvergenceResult,
    IterationBoundary,
)

__all__ = ["ConvergenceEvaluator", "ConvergenceResult", "IterationBoundary"]
