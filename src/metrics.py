"""Losses as exact fractions of exported decimal predictions, with grouped means."""

from collections import defaultdict
from fractions import Fraction as Q
import math


def summarize(rows, scope="overall", unit="ALL", period="ALL"):
    n = len(rows)
    assert n
    absolute = squared = bias = Q(0)
    observed = 0
    groups = defaultdict(list)
    for row in rows:
        error = Q(str(row["prediction"])) - int(row["actual"])
        absolute += abs(error)
        squared += error * error
        bias += error
        observed += int(row["actual"])
        groups[row["group"]].append(error)
    group_mae = sum(
        sum(map(abs, values)) / len(values) for values in groups.values()
    ) / len(groups)
    group_mse = sum(
        sum(value * value for value in values) / len(values)
        for values in groups.values()
    ) / len(groups)
    return dict(
        scope=scope,
        unit=unit,
        period=period,
        n=n,
        groups=len(groups),
        observed=observed,
        abs_error_total_exact=str(absolute),
        squared_error_total_exact=str(squared),
        bias_total_exact=str(bias),
        mae_exact=str(absolute / n),
        mse_exact=str(squared / n),
        rmse=math.sqrt(float(squared / n)),
        mean_error_exact=str(bias / n),
        wape_exact="" if observed == 0 else str(absolute / observed),
        mae_equal_group_exact=str(group_mae),
        mse_equal_group_exact=str(group_mse),
        rmse_equal_group=math.sqrt(float(group_mse)),
    )


def all_metrics(rows):
    result = [summarize(rows)]
    for scope, key in [("coordinate_group", "group"), ("station", "station")]:
        for value in sorted({r[key] for r in rows}):
            result.append(summarize([r for r in rows if r[key] == value], scope, value))
    for month in sorted({r["date"][:7] for r in rows}):
        result.append(
            summarize(
                [r for r in rows if r["date"].startswith(month)], "month", "ALL", month
            )
        )
    return result
