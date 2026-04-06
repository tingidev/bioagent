"""Statistics tool — analytical capabilities for agent use."""

from __future__ import annotations

import math
from collections import Counter
from itertools import groupby


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
    """Compare two groups with descriptive stats and effect size."""
    stats_a = describe(group_a)
    stats_b = describe(group_b)

    mean_a = stats_a.get("mean", 0) or 0
    mean_b = stats_b.get("mean", 0) or 0
    std_a = stats_a.get("std", 0) or 0
    std_b = stats_b.get("std", 0) or 0
    mean_diff = mean_a - mean_b

    # Cohen's d effect size
    pooled_std = math.sqrt((std_a ** 2 + std_b ** 2) / 2) if (std_a + std_b) > 0 else 0
    cohens_d = round(mean_diff / pooled_std, 4) if pooled_std > 0 else 0

    effect_label = (
        "negligible" if abs(cohens_d) < 0.2 else
        "small" if abs(cohens_d) < 0.5 else
        "medium" if abs(cohens_d) < 0.8 else
        "large"
    )

    return {
        label_a: stats_a,
        label_b: stats_b,
        "mean_difference": round(mean_diff, 4),
        "cohens_d": cohens_d,
        "effect_size": effect_label,
    }


def frequency_table(values: list[str], top_n: int = 20) -> list[dict]:
    """Build a frequency table for categorical values."""
    counts = Counter(values)
    total = len(values)
    return [
        {"value": val, "count": count, "pct": round(count / total * 100, 1)}
        for val, count in counts.most_common(top_n)
    ]


def correlation(xs: list[float], ys: list[float]) -> dict:
    """Compute Pearson correlation between two numeric series.

    Returns correlation coefficient, interpretation, and sample size.
    Both lists must have the same length.
    """
    n = min(len(xs), len(ys))
    if n < 3:
        return {"error": "Need at least 3 paired values", "n": n}

    xs, ys = xs[:n], ys[:n]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / n)
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / n)

    if std_x == 0 or std_y == 0:
        return {"r": 0, "interpretation": "no variance in one or both variables", "n": n}

    r = cov / (std_x * std_y)

    interpretation = (
        "negligible" if abs(r) < 0.1 else
        "weak" if abs(r) < 0.3 else
        "moderate" if abs(r) < 0.5 else
        "strong" if abs(r) < 0.7 else
        "very strong"
    )
    direction = "positive" if r > 0 else "negative"

    return {
        "r": round(r, 4),
        "r_squared": round(r ** 2, 4),
        "direction": direction,
        "strength": interpretation,
        "interpretation": f"{interpretation} {direction} correlation",
        "n": n,
    }


def outlier_detection(
    values: list[float],
    labels: list[str] | None = None,
    method: str = "iqr",
) -> dict:
    """Detect outliers using IQR method.

    Returns outlier values/labels, thresholds, and summary stats.
    Labels are optional identifiers for each value (e.g. sequence IDs).
    """
    if len(values) < 4:
        return {"error": "Need at least 4 values for outlier detection"}

    sorted_vals = sorted(values)
    q25 = _percentile(sorted_vals, 0.25)
    q75 = _percentile(sorted_vals, 0.75)
    iqr = q75 - q25

    lower_bound = q25 - 1.5 * iqr
    upper_bound = q75 + 1.5 * iqr

    outliers_high = []
    outliers_low = []

    for i, v in enumerate(values):
        label = labels[i] if labels and i < len(labels) else str(i)
        if v > upper_bound:
            outliers_high.append({"label": label, "value": round(v, 4)})
        elif v < lower_bound:
            outliers_low.append({"label": label, "value": round(v, 4)})

    outliers_high.sort(key=lambda x: x["value"], reverse=True)
    outliers_low.sort(key=lambda x: x["value"])

    return {
        "method": "IQR (1.5x)",
        "lower_bound": round(lower_bound, 4),
        "upper_bound": round(upper_bound, 4),
        "q25": q25,
        "q75": q75,
        "iqr": round(iqr, 4),
        "total_values": len(values),
        "outliers_high": outliers_high[:20],
        "outliers_low": outliers_low[:20],
        "n_outliers_high": len(outliers_high),
        "n_outliers_low": len(outliers_low),
    }


def rank_and_filter(
    values: list[float],
    labels: list[str],
    top_n: int = 10,
    bottom_n: int = 0,
) -> dict:
    """Rank items by value and return top/bottom N with percentile context."""
    if not values or not labels:
        return {"error": "Need values and labels"}

    n = min(len(values), len(labels))
    pairs = [(labels[i], values[i]) for i in range(n)]
    pairs.sort(key=lambda x: x[1], reverse=True)

    sorted_vals = sorted(values[:n])
    stats = describe(values[:n])

    top = [
        {"rank": i + 1, "label": p[0], "value": round(p[1], 4)}
        for i, p in enumerate(pairs[:top_n])
    ]

    bottom = []
    if bottom_n > 0:
        bottom = [
            {"rank": n - len(pairs[-bottom_n:]) + i + 1, "label": p[0], "value": round(p[1], 4)}
            for i, p in enumerate(pairs[-bottom_n:])
        ]

    return {
        "total_items": n,
        "stats": stats,
        "top": top,
        "bottom": bottom,
    }


def cross_tabulate(
    row_categories: list[str],
    col_categories: list[str],
    row_label: str = "row",
    col_label: str = "col",
) -> dict:
    """Cross-tabulate two categorical variables.

    Both lists must be the same length. Returns counts and percentages
    for each combination.
    """
    n = min(len(row_categories), len(col_categories))
    if n == 0:
        return {"error": "Need at least one paired value"}

    rows = row_categories[:n]
    cols = col_categories[:n]

    table: dict[str, dict[str, int]] = {}
    for r, c in zip(rows, cols):
        if r not in table:
            table[r] = {}
        table[r][c] = table[r].get(c, 0) + 1

    row_totals = {r: sum(cs.values()) for r, cs in table.items()}
    col_totals: dict[str, int] = {}
    for cs in table.values():
        for c, count in cs.items():
            col_totals[c] = col_totals.get(c, 0) + count

    result_rows = []
    for r in sorted(table.keys()):
        for c in sorted(table[r].keys()):
            count = table[r][c]
            result_rows.append({
                row_label: r,
                col_label: c,
                "count": count,
                "pct_of_row": round(count / row_totals[r] * 100, 1),
                "pct_of_total": round(count / n * 100, 1),
            })

    return {
        "total": n,
        "rows": sorted(table.keys()),
        "cols": sorted(col_totals.keys()),
        "data": result_rows,
        "row_totals": row_totals,
        "col_totals": col_totals,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
