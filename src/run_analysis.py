"""Retain the full validation search and frozen held geographic stress lattice."""

import argparse
import csv
from datetime import date, timedelta
from fractions import Fraction as Q
import gzip
import io
import json
import math
from pathlib import Path
import random
import time

from model import (
    BASELINE,
    candidates,
    history,
    load,
    neighbor_weights,
    prediction,
    rank_key,
)
from metrics import all_metrics

ROOT = Path(__file__).resolve().parents[1]


def write(path, rows, compressed=False):
    assert rows
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = stream.getvalue().encode("utf-8")
    path.write_bytes(gzip.compress(data, mtime=0) if compressed else data)


def run(phase, root=ROOT):
    started = time.perf_counter()
    root = Path(root)
    cfg = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    stations, counts = load(root)
    donors = sorted(s for s, r in stations.items() if int(r["fold"]) < 3)
    fold = 3 if phase == "validation" else 4
    targets = sorted(s for s, r in stations.items() if int(r["fold"]) == fold)
    start = date.fromisoformat(
        cfg["validation" if phase == "validation" else "held"]["start"]
    )
    end = date.fromisoformat(
        cfg["validation" if phase == "validation" else "held"]["end_exclusive"]
    )
    dates = [start + timedelta(days=i) for i in range((end - start).days)]
    policies = (
        candidates() + [BASELINE]
        if phase == "validation"
        else [
            json.loads((root / "SELECTION.json").read_text(encoding="utf-8"))[
                "selected"
            ],
            BASELINE,
        ]
    )
    contexts = {}
    feature_rows = []
    for window, calendar in sorted({(p["window"], p["calendar"]) for p in policies}):
        for target_date in dates:
            feature = history(counts, donors, target_date, window, calendar)
            contexts[window, calendar, target_date] = feature
            for donor, r in feature.items():
                feature_rows.append(
                    dict(
                        window=window,
                        calendar=calendar,
                        date=target_date.isoformat(),
                        donor=donor,
                        window_start=(target_date - timedelta(days=window)).isoformat(),
                        window_end_exclusive=target_date.isoformat(),
                        first=r["first"].isoformat(),
                        last=r["last"].isoformat(),
                        n=r["n"],
                        total=r["total"],
                        mean_exact=str(r["mean"]),
                    )
                )
    preparation = time.perf_counter() - started
    predictions = []
    weights_export = []
    metrics = []
    execution = []
    for policy in policies:
        scenarios = [("unshifted", 0, 0)]
        if phase == "held" and policy["k"]:
            scenarios += [
                (
                    f"shift{int(1000*float(distance))}m-b{bearing:03d}",
                    float(distance),
                    bearing,
                )
                for distance in cfg["held_geometry_stress"]["distances_km"]
                for bearing in cfg["held_geometry_stress"]["bearings_degrees"]
            ]
        for scenario, displacement, bearing in scenarios:
            tick = time.perf_counter()
            rows = []
            for target in targets:
                weights = neighbor_weights(
                    stations, donors, target, policy, displacement, bearing
                )
                for donor, km, weight in weights:
                    weights_export.append(
                        dict(
                            scenario=scenario,
                            policy=policy["policy"],
                            station=target,
                            donor=donor,
                            distance_km=km,
                            weight=weight,
                        )
                    )
                for target_date in dates:
                    value, low, high = prediction(
                        contexts[policy["window"], policy["calendar"], target_date],
                        weights,
                        policy["power"],
                    )
                    rows.append(
                        dict(
                            scenario=scenario,
                            policy=policy["policy"],
                            station=target,
                            group=stations[target]["group"],
                            date=target_date.isoformat(),
                            actual=counts[target, target_date],
                            prediction=value,
                            donor_min=low,
                            donor_max=high,
                            neighbor_count=len(weights),
                        )
                    )
            predictions.extend(rows)
            policy_metrics = [
                dict(scenario=scenario, policy=policy["policy"], **m)
                for m in all_metrics(rows)
            ]
            metrics.extend(policy_metrics)
            execution.append(
                dict(
                    policy=policy["policy"],
                    scenario=scenario,
                    prediction_rows=len(rows),
                    elapsed_seconds=time.perf_counter() - tick,
                    status="PASS_EXECUTED_CHECKS_PENDING",
                )
            )
    output = root / "results"
    output.mkdir(exist_ok=True)
    write(output / (phase + "-features.csv.gz"), feature_rows, True)
    write(output / (phase + "-weights.csv.gz"), weights_export, True)
    write(output / (phase + "-predictions.csv.gz"), predictions, True)
    write(output / (phase + "-metrics.csv"), metrics)
    if phase == "validation":
        scores = {
            r["policy"]: Q(r["mae_equal_group_exact"])
            for r in metrics
            if r["scope"] == "overall"
        }
        ordered = sorted(candidates(), key=lambda p: (scores[p["policy"]], rank_key(p)))
        selected = ordered[0]
        selection = dict(
            selected=selected,
            objective="Equal-coordinate-group validation MAE of round-trip decimal predictions",
            objective_exact=str(scores[selected["policy"]]),
            baseline=BASELINE,
            baseline_mae_exact=str(scores[BASELINE["policy"]]),
            attempted_geographic_configurations=54,
            selection_period=cfg["validation"],
            held_outcomes_inspected=False,
            source_inputs_visible_without_blinding=True,
        )
        (root / "SELECTION.json").write_text(
            json.dumps(selection, indent=2) + "\n", encoding="utf-8"
        )
    else:
        selected = policies[0]["policy"]
        base = BASELINE["policy"]
        losses = {
            p: {
                r["unit"]: Q(r["mae_exact"])
                for r in metrics
                if r["scenario"] == "unshifted"
                and r["policy"] == p
                and r["scope"] == "coordinate_group"
            }
            for p in [selected, base]
        }
        groups = sorted(losses[selected])
        assert groups == sorted(losses[base])
        rng = random.Random(cfg["bootstrap"]["seed"])
        draw_rows = []
        samples = []
        for replicate in range(cfg["bootstrap"]["replicates"]):
            draw = [groups[rng.randrange(len(groups))] for _ in groups]
            for index, group in enumerate(draw):
                draw_rows.append(dict(replicate=replicate, draw=index, group=group))
            difference = sum(losses[selected][g] - losses[base][g] for g in draw) / len(
                draw
            )
            samples.append(
                dict(replicate=replicate, mae_difference_exact=str(difference))
            )
        write(output / "held-bootstrap-indices.csv", draw_rows)
        write(output / "held-bootstrap.csv", samples)
        ordered = sorted(Q(r["mae_difference_exact"]) for r in samples)
        n = len(ordered)
        summary = dict(
            seed=cfg["bootstrap"]["seed"],
            replicates=n,
            coordinate_groups=len(groups),
            scenario="unshifted",
            lower_exact=str(ordered[math.ceil(0.025 * n) - 1]),
            upper_exact=str(ordered[math.ceil(0.975 * n) - 1]),
            quantile="Nearest-rank empirical2.5th/97.5th percentiles, no interpolation",
            meaning="Conditional finite-coordinate-group resampling sensitivity, not guaranteed future coverage or independent spatial sampling.",
        )
        (output / "BOOTSTRAP_SUMMARY.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    result = dict(
        phase=phase,
        shared_feature_preparation_seconds=preparation,
        elapsed_seconds=time.perf_counter() - started,
        policies=execution,
        prediction_rows=len(predictions),
        feature_rows=len(feature_rows),
        weight_rows=len(weights_export),
        metric_rows=len(metrics),
        availability="Strictly past donor indices under idealized complete prior-day counts; actual source publication vintages and live feasibility unverified.",
    )
    (output / (phase + "-execution.json")).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "policies"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["validation", "held"])
    args = parser.parse_args()
    run(args.phase)
