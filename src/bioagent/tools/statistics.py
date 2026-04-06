"""Statistics tool — basic statistical analysis for agent use."""

from __future__ import annotations

import math
from collections import Counter


def describe(values: list[float]) -> dict:
    """Compute descriptive statistics for a list of numeric values."""
    if not values:
        return {"count": 0}

    n = len(values)
    sorted_vals = sorted(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n if n > 1 else 0.0
    std = math.sqrt(variance)

    return {
        "count": n,
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "median": _median(sorted_vals),
        "q25": _percentile(sorted_vals, 0.25),
        "q75": _percentile(sorted_vals, 0.75),
    }


def compare_groups(
    group_a: list[float],
    group_b: list[float],
    label_a: str = "A",
    label_b: str = "B",
) -> dict:
    """Compare two groups of values with basic statistics."""
    stats_a = describe(group_a)
    stats_b = describe(group_b)

    mean_diff = (stats_a.get("mean", 0) or 0) - (stats_b.get("mean", 0) or 0)

    return {
        label_a: stats_a,
        label_b: stats_b,
        "mean_difference": round(mean_diff, 4),
    }


def frequency_table(values: list[str], top_n: int = 20) -> list[dict]:
    """Build a frequency table for categorical values."""
    counts = Counter(values)
    total = len(values)
    return [
        {"value": val, "count": count, "pct": round(count / total * 100, 1)}
        for val, count in counts.most_common(top_n)
    ]


def _median(sorted_vals: list[float]) -> float:
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2, 4)
    return sorted_vals[mid]


def _percentile(sorted_vals: list[float], p: float) -> float:
    n = len(sorted_vals)
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return round(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f), 4)
