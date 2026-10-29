"""Declared rolling donor means and fixed-geometry nearest-neighbor regression."""

import csv
from datetime import date, timedelta
from fractions import Fraction as Q
import gzip
import itertools
import math
from pathlib import Path

from geo import distance, shift


def load(root):
    root = Path(root)
    with (root / "data/source/station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        stations = {
            r["station"]: r for r in csv.DictReader(stream) if r["eligible"] == "1"
        }
    with gzip.open(root / "data/source/counts.csv.gz", "rt", newline="") as stream:
        counts = {}
        for r in csv.DictReader(stream):
            key = (r["station"], date.fromisoformat(r["date"]))
            if key in counts:
                raise ValueError("Duplicate station/day")
            counts[key] = int(r["departures"])
    return stations, counts


def candidates():
    result = []
    for window, calendar, k, power in itertools.product(
        [28, 56, 84], ["weekday", "daytype"], [3, 5, 10], [0, 1, 2]
    ):
        result.append(
            dict(
                policy=f"geo-w{window}-{calendar}-k{k}-p{power}",
                window=window,
                calendar=calendar,
                k=k,
                power=power,
            )
        )
    return result


BASELINE = dict(
    policy="pooled_weekday_w84", window=84, calendar="weekday", k=0, power=0
)


def calendar_dates(target, window, calendar):
    if calendar not in ["weekday", "daytype"]:
        raise ValueError("Unknown calendar grouping")
    return [
        target - timedelta(days=offset)
        for offset in range(window, 0, -1)
        if (
            (target - timedelta(days=offset)).weekday() == target.weekday()
            if calendar == "weekday"
            else ((target - timedelta(days=offset)).weekday() >= 5)
            == (target.weekday() >= 5)
        )
    ]


def history(counts, donors, target, window, calendar):
    days = calendar_dates(target, window, calendar)
    if len(days) < 3:
        raise ValueError("Insufficient declared history")
    assert min(days) >= date(2024, 1, 1) and max(days) < target
    return {
        station: dict(
            total=sum(counts[station, day] for day in days),
            n=len(days),
            mean=Q(sum(counts[station, day] for day in days), len(days)),
            first=days[0],
            last=days[-1],
        )
        for station in donors
    }


def neighbor_weights(stations, donors, target, policy, displacement=0, bearing=0):
    if target in donors:
        raise ValueError("Withheld target cannot be a donor")
    if policy["k"] > len(donors):
        raise ValueError("Insufficient donor count for declared k")
    row = stations[target]
    lat, lon = float(row["latitude"]), float(row["longitude"])
    if displacement:
        lat, lon = shift(lat, lon, displacement, bearing)
    distances = sorted(
        (
            distance(
                lat,
                lon,
                float(stations[donor]["latitude"]),
                float(stations[donor]["longitude"]),
            ),
            donor,
        )
        for donor in donors
    )
    if policy["k"] == 0:
        return [(donor, value, 1 / len(donors)) for value, donor in distances]
    nearest = distances[: policy["k"]]
    raw = [max(value, 0.100) ** (-policy["power"]) for value, donor in nearest]
    total = math.fsum(raw)
    return [
        (donor, value, weight / total) for (value, donor), weight in zip(nearest, raw)
    ]


def prediction(features, weights, power):
    values = [features[donor]["mean"] for donor, distance, weight in weights]
    result = (
        float(sum(values) / len(values))
        if power == 0
        else math.fsum(
            float(features[donor]["mean"]) * weight
            for donor, distance, weight in weights
        )
    )
    assert float(min(values)) - 1e-10 <= result <= float(max(values)) + 1e-10
    return result, float(min(values)), float(max(values))


def rank_key(policy):
    return (
        policy["k"],
        policy["power"],
        policy["window"],
        0 if policy["calendar"] == "weekday" else 1,
    )
