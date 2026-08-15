"""Core contracts for retail intelligence pipelines."""

from .inference_budget import InferenceBudget, evaluate_inference_budget

__all__ = ["InferenceBudget", "evaluate_inference_budget"]
