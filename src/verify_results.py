"""Independent SQL histories, vector geometry and exact exported-loss reconstruction."""

import argparse
from collections import defaultdict
import csv
from datetime import date, timedelta
from fractions import Fraction as Q
import gzip
import itertools
import json
import math
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def vector(lat, lon):
    a, b = math.radians(lat), math.radians(lon)
    return [math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)]


def arc(position, other):
    u, v = vector(*position), vector(*other)
    cross = [
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    ]
    return 6371 * math.atan2(
        math.sqrt(sum(x * x for x in cross)), sum(x * y for x, y in zip(u, v))
    )


def moved(position, km, bearing):
    lat, lon = map(math.radians, position)
    theta = math.radians(bearing)
    delta = km / 6371
    u = vector(*position)
    north = [
        -math.sin(lat) * math.cos(lon),
        -math.sin(lat) * math.sin(lon),
        math.cos(lat),
    ]
    east = [-math.sin(lon), math.cos(lon), 0]
    v = [
        a * math.cos(delta)
        + (b * math.cos(theta) + c * math.sin(theta)) * math.sin(delta)
        for a, b, c in zip(u, north, east)
    ]
    return math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))), math.degrees(
        math.atan2(v[1], v[0])
    )


def verify(phase, root=ROOT):
    root = Path(root)
    cfg = json.loads((root / "protocol.json").read_text(encoding="utf-8"))

    def read(name):
        path = root / "results" / name
        with (
            gzip.open(path, "rt", newline="")
            if name.endswith(".gz")
            else path.open(encoding="utf-8", newline="")
        ) as stream:
            return list(csv.DictReader(stream))

    with (root / "data/source/station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        stations = {
            r["station"]: r for r in csv.DictReader(stream) if r["eligible"] == "1"
        }
    donors = sorted(s for s, r in stations.items() if int(r["fold"]) < 3)
    fold = 3 if phase == "validation" else 4
    targets = sorted(s for s, r in stations.items() if int(r["fold"]) == fold)
    period = cfg["validation" if phase == "validation" else "held"]
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end_exclusive"])
    dates = [start + timedelta(days=i) for i in range((end - start).days)]
    positions = {
        s: (float(r["latitude"]), float(r["longitude"])) for s, r in stations.items()
    }
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE counts(station TEXT,day TEXT,n INT,PRIMARY KEY(station,day))"
    )
    counts = {}
    with gzip.open(root / "data/source/counts.csv.gz", "rt", newline="") as stream:
        for r in csv.DictReader(stream):
            db.execute(
                "INSERT INTO counts VALUES(?,?,?)",
                (r["station"], r["date"], int(r["departures"])),
            )
            counts[r["station"], r["date"]] = int(r["departures"])
    geographic = {}
    for w, c, k, p in itertools.product(
        cfg["windows_days"],
        cfg["calendar_groups"],
        cfg["neighbors"],
        cfg["distance_exponents"],
    ):
        geographic[f"geo-w{w}-{c}-k{k}-p{p}"] = dict(
            policy=f"geo-w{w}-{c}-k{k}-p{p}", window=w, calendar=c, k=k, power=p
        )
    baseline = dict(
        policy="pooled_weekday_w84", window=84, calendar="weekday", k=0, power=0
    )
    selection = json.loads((root / "SELECTION.json").read_text(encoding="utf-8"))
    chosen = selection["selected"]
    assert chosen == geographic[chosen["policy"]]
    policies = (
        {**geographic, baseline["policy"]: baseline}
        if phase == "validation"
        else {chosen["policy"]: chosen, baseline["policy"]: baseline}
    )
    exact_checks = float_checks = 0

    def close(a, b, tolerance):
        nonlocal float_checks
        a, b = float(a), float(b)
        assert math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tolerance, (
            a,
            b,
            tolerance,
        )
        float_checks += 1

    feature_rows = read(phase + "-features.csv.gz")
    features = {}
    for r in feature_rows:
        w = int(r["window"])
        calendar = r["calendar"]
        day = date.fromisoformat(r["date"])
        donor = r["donor"]
        assert (
            (w, calendar) in {(p["window"], p["calendar"]) for p in policies.values()}
            and day in dates
            and donor in donors
        )
        key = w, calendar, r["date"], donor
        assert key not in features
        where = (
            "((CAST(strftime('%w',day) AS INT)+6)%7)=?"
            if calendar == "weekday"
            else "(((CAST(strftime('%w',day) AS INT)+6)%7)>=5)=?"
        )
        match = day.weekday() if calendar == "weekday" else int(day.weekday() >= 5)
        lower = (day - timedelta(days=w)).isoformat()
        n, total, first, last = db.execute(
            "SELECT COUNT(*),SUM(n),MIN(day),MAX(day) FROM counts WHERE station=? AND day>=? AND day<? AND "
            + where,
            (donor, lower, r["date"], match),
        ).fetchone()
        assert n >= 3 and first >= lower and last < r["date"]
        expected = dict(
            window=str(w),
            calendar=calendar,
            date=r["date"],
            donor=donor,
            window_start=lower,
            window_end_exclusive=r["date"],
            first=first,
            last=last,
            n=str(n),
            total=str(total),
            mean_exact=str(Q(total, n)),
        )
        assert r == expected, (key, r, expected)
        exact_checks += len(r)
        features[key] = Q(total, n)
    expected_feature_keys = {
        (w, c, d.isoformat(), s)
        for w, c in {(p["window"], p["calendar"]) for p in policies.values()}
        for d in dates
        for s in donors
    }
    assert set(features) == expected_feature_keys
    weights = defaultdict(list)
    for r in read(phase + "-weights.csv.gz"):
        weights[r["scenario"], r["policy"], r["station"]].append(r)
    scenarios = {("unshifted", p, s) for p in policies for s in targets}
    shifts = {"unshifted": (0, 0)}
    if phase == "held":
        shifts.update(
            {
                f"shift{int(float(km)*1000)}m-b{bearing:03d}": (float(km), bearing)
                for km in cfg["held_geometry_stress"]["distances_km"]
                for bearing in cfg["held_geometry_stress"]["bearings_degrees"]
            }
        )
        scenarios |= {
            (scenario, chosen["policy"], s) for scenario in shifts for s in targets
        }
    assert set(weights) == scenarios
    verified_weights = {}
    for key, rows in weights.items():
        scenario, policy_id, station = key
        policy = policies[policy_id]
        km, bearing = shifts[scenario]
        position = moved(positions[station], km, bearing) if km else positions[station]
        distances = {donor: arc(position, positions[donor]) for donor in donors}
        ids = [r["donor"] for r in rows]
        assert len(set(ids)) == len(ids) and set(ids) <= set(donors)
        assert len(rows) == (len(donors) if policy["k"] == 0 else policy["k"])
        assert station not in ids and all(
            stations[s]["group"] != stations[station]["group"] for s in ids
        )
        if policy["k"]:
            omitted = set(donors) - set(ids)
            assert not omitted or min(distances[s] for s in omitted) + 1e-8 >= max(
                distances[s] for s in ids
            )
        else:
            assert set(ids) == set(donors)
        raw = [
            1 if policy["k"] == 0 else max(distances[s], 0.100) ** (-policy["power"])
            for s in ids
        ]
        denom = math.fsum(raw)
        expected = [v / denom for v in raw]
        previous = None
        for r, s, weight in zip(rows, ids, expected):
            assert (
                r["scenario"] == scenario
                and r["policy"] == policy_id
                and r["station"] == station
            )
            close(
                r["distance_km"],
                distances[s],
                float(cfg["floating_tolerances"]["distance_km_absolute"]),
            )
            close(r["weight"], weight, 1e-8)
            if previous is not None:
                assert (float(r["distance_km"]), s) >= (
                    float(previous["distance_km"]),
                    previous["donor"],
                )
            previous = r
            exact_checks += 4
        close(sum(float(r["weight"]) for r in rows), 1, 1e-12)
        verified_weights[key] = list(zip(ids, expected))
    predictions = read(phase + "-predictions.csv.gz")
    seen = set()
    by_case = defaultdict(list)
    for r in predictions:
        scenario, policy_id, station = r["scenario"], r["policy"], r["station"]
        key = scenario, policy_id, station, r["date"]
        assert key not in seen
        seen.add(key)
        assert (
            scenario,
            policy_id,
            station,
        ) in verified_weights and date.fromisoformat(r["date"]) in dates
        assert (
            r["group"] == stations[station]["group"]
            and int(stations[station]["fold"]) == fold
            and int(r["actual"]) == counts[station, r["date"]]
        )
        policy = policies[policy_id]
        neighbors = verified_weights[scenario, policy_id, station]
        means = [
            features[policy["window"], policy["calendar"], r["date"], s]
            for s, w in neighbors
        ]
        expected = (
            float(sum(means) / len(means))
            if policy["power"] == 0
            else math.fsum(
                float(value) * weight for value, (s, weight) in zip(means, neighbors)
            )
        )
        close(
            r["prediction"],
            expected,
            float(cfg["floating_tolerances"]["prediction_absolute"]),
        )
        close(r["donor_min"], min(means), 1e-8)
        close(r["donor_max"], max(means), 1e-8)
        assert (
            int(r["neighbor_count"]) == len(neighbors)
            and float(r["donor_min"]) - 1e-8
            <= float(r["prediction"])
            <= float(r["donor_max"]) + 1e-8
        )
        exact_checks += 7
        by_case[scenario, policy_id].append(r)
    assert len(seen) == len(scenarios) * len(dates)
    metric_rows = read(phase + "-metrics.csv")
    expected_metric_keys = set()
    for case, rows in by_case.items():
        scopes = [("overall", "ALL", "ALL", rows)]
        for scope, field in [("coordinate_group", "group"), ("station", "station")]:
            scopes += [
                (scope, value, "ALL", [r for r in rows if r[field] == value])
                for value in sorted({r[field] for r in rows})
            ]
        scopes += [
            ("month", "ALL", month, [r for r in rows if r["date"].startswith(month)])
            for month in sorted({r["date"][:7] for r in rows})
        ]
        for scope, unit, period, sample in scopes:
            identity = (*case, scope, unit, period)
            expected_metric_keys.add(identity)
            actual = [
                r
                for r in metric_rows
                if (r["scenario"], r["policy"], r["scope"], r["unit"], r["period"])
                == identity
            ]
            assert len(actual) == 1
            actual = actual[0]
            errors = [Q(r["prediction"]) - int(r["actual"]) for r in sample]
            n = len(sample)
            observed = sum(int(r["actual"]) for r in sample)
            absolute = sum(map(abs, errors))
            squared = sum(e * e for e in errors)
            bias = sum(errors)
            group_errors = defaultdict(list)
            for r, error in zip(sample, errors):
                group_errors[r["group"]].append(error)
            group_abs = [sum(map(abs, e)) / len(e) for e in group_errors.values()]
            group_sq = [sum(x * x for x in e) / len(e) for e in group_errors.values()]
            gmae = sum(group_abs) / len(group_abs)
            gmse = sum(group_sq) / len(group_sq)
            expected = dict(
                scenario=case[0],
                policy=case[1],
                scope=scope,
                unit=unit,
                period=period,
                n=n,
                groups=len(group_errors),
                observed=observed,
                abs_error_total_exact=absolute,
                squared_error_total_exact=squared,
                bias_total_exact=bias,
                mae_exact=absolute / n,
                mse_exact=squared / n,
                mean_error_exact=bias / n,
                wape_exact="" if observed == 0 else absolute / observed,
                mae_equal_group_exact=gmae,
                mse_equal_group_exact=gmse,
            )
            for field, value in expected.items():
                assert actual[field] == str(value), (
                    identity,
                    field,
                    actual[field],
                    value,
                )
            exact_checks += len(expected)
            close(
                actual["rmse"],
                math.sqrt(float(squared / n)),
                float(cfg["floating_tolerances"]["metric_absolute"]),
            )
            close(
                actual["rmse_equal_group"],
                math.sqrt(float(gmse)),
                float(cfg["floating_tolerances"]["metric_absolute"]),
            )
    assert len(metric_rows) == len(expected_metric_keys)
    if phase == "validation":
        scores = {
            r["policy"]: Q(r["mae_equal_group_exact"])
            for r in metric_rows
            if r["scope"] == "overall"
        }
        tie = lambda p: (
            p["k"],
            p["power"],
            p["window"],
            0 if p["calendar"] == "weekday" else 1,
        )
        winner = min(geographic.values(), key=lambda p: (scores[p["policy"]], tie(p)))
        assert (
            chosen == winner
            and selection["objective_exact"] == str(scores[winner["policy"]])
            and selection["baseline_mae_exact"] == str(scores[baseline["policy"]])
            and selection["held_outcomes_inspected"] is False
        )
        exact_checks += 5
    else:
        group_losses = {
            p: {
                r["unit"]: Q(r["mae_exact"])
                for r in metric_rows
                if r["scenario"] == "unshifted"
                and r["policy"] == p
                and r["scope"] == "coordinate_group"
            }
            for p in [chosen["policy"], baseline["policy"]]
        }
        groups = sorted(group_losses[chosen["policy"]])
        assert groups == sorted(group_losses[baseline["policy"]])
        index_rows = read("held-bootstrap-indices.csv")
        replicates = defaultdict(list)
        for r in index_rows:
            assert r["group"] in groups
            replicates[int(r["replicate"])].append((int(r["draw"]), r["group"]))
            exact_checks += 3
        samples = read("held-bootstrap.csv")
        assert len(samples) == len(replicates) == cfg["bootstrap"]["replicates"]
        values = []
        for r in samples:
            draws = sorted(replicates[int(r["replicate"])])
            assert [i for i, g in draws] == list(range(len(groups)))
            value = sum(
                group_losses[chosen["policy"]][g] - group_losses[baseline["policy"]][g]
                for i, g in draws
            ) / len(groups)
            assert r["mae_difference_exact"] == str(value)
            values.append(value)
            exact_checks += 2
        summary = json.loads(
            (root / "results/BOOTSTRAP_SUMMARY.json").read_text(encoding="utf-8")
        )
        values.sort()
        n = len(values)
        assert summary["lower_exact"] == str(
            values[math.ceil(Q(25, 1000) * n) - 1]
        ) and summary["upper_exact"] == str(values[math.ceil(Q(975, 1000) * n) - 1])
        assert (
            summary["scenario"] == "unshifted"
            and summary["coordinate_groups"] == len(groups)
            and summary["seed"] == cfg["bootstrap"]["seed"]
        )
        exact_checks += 5
    return dict(
        status="PASS",
        phase=phase,
        exact_scalar_checks=exact_checks,
        numeric_tolerance_checks=float_checks,
        prediction_rows=len(predictions),
        feature_rows=len(feature_rows),
        weight_rows=sum(map(len, weights.values())),
        metric_rows=len(metric_rows),
        scope="Independent SQL histories, unit-vector angular distances/displacements and exact fractional losses from exported decimals. Neighbor ranks checked within fixed1e-8km distance precision; actual publication availability and physical sites remain unverified.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["validation", "held"])
    args = parser.parse_args()
    result = verify(args.phase)
    (ROOT / "results" / (args.phase + "-VERIFICATION.json")).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
