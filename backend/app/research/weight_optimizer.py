from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable


@dataclass(frozen=True)
class WeightOptimizationResult:
    weights: dict[str, float]
    objective_score: float
    method: str


def optimize_weights_grid(
    *,
    search_space: dict[str, list[float]],
    objective: Callable[[dict[str, float]], float],
) -> WeightOptimizationResult:
    keys = list(search_space.keys())
    best_weights: dict[str, float] = {key: values[0] for key, values in search_space.items()}
    best_score = float("-inf")

    for combination in product(*(search_space[key] for key in keys)):
        weights = {key: value for key, value in zip(keys, combination)}
        score = float(objective(weights))
        if score > best_score:
            best_score = score
            best_weights = weights

    return WeightOptimizationResult(
        weights=best_weights,
        objective_score=round(best_score, 6),
        method="grid_search",
    )


def optimize_weights_bayesian(
    *,
    search_space: dict[str, list[float]],
    objective: Callable[[dict[str, float]], float],
) -> WeightOptimizationResult:
    # Bayesian optimization is feature-flagged later in rollout; default to grid-search-compatible behavior now.
    return optimize_weights_grid(search_space=search_space, objective=objective)
