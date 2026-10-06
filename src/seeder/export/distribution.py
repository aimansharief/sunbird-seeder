"""Builds read-test ID lists where a few IDs are hot and the rest are long tail."""
from __future__ import annotations

import random


def weighted_rows(ids: list[str], rows: int, skew: float, seed: int) -> list[str]:
    """Samples `rows` IDs with Zipf-like weights 1/rank^skew. skew=0 is uniform.

    Ranks are shuffled with the seed, so which IDs are hot is random but reproducible.
    """
    if not ids:
        return []
    rng = random.Random(seed)
    ranked = list(ids)
    rng.shuffle(ranked)
    weights = [1.0 / ((r + 1) ** skew) for r in range(len(ranked))]
    return rng.choices(ranked, weights=weights, k=rows)
