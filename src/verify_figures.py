"""Compare every numeric plot artist with the independently checked source exports."""

import csv
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def display(value, places=3):
    value = Q(value)
    with localcontext() as context:
        context.prec = 80
        return format(
            (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
                Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN
            ),
            "." + str(places) + "f",
        )


def verify():
    with (ROOT / "results/held-metrics.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    with (ROOT / "data/source/station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        stations = [r for r in csv.DictReader(stream) if r["eligible"] == "1"]
    selected = json.loads((ROOT / "SELECTION.json").read_text(encoding="utf-8"))[
        "selected"
    ]["policy"]
    base = "pooled_weekday_w84"
    metrics = lambda p: {
        r["unit"]: r
        for r in rows
        if r["policy"] == p
        and r["scenario"] == "unshifted"
        and r["scope"] == "coordinate_group"
    }
    a, b = metrics(selected), metrics(base)
    groups = sorted(a)
    difference = {g: Q(a[g]["mae_exact"]) - Q(b[g]["mae_exact"]) for g in groups}
    evidence = json.loads(
        (ROOT / "figures/ARTIST_VALUES.json").read_text(encoding="utf-8")
    )
    checks = 0

    def same(actual, expected):
        nonlocal checks
        assert abs(float(actual) - float(expected)) <= 1e-10, (actual, expected)
        checks += 1

    expected_roles = {
        "baseline": groups,
        "geo_lower": [g for g in groups if difference[g] <= 0],
        "geo_higher": [g for g in groups if difference[g] > 0],
    }
    assert set(evidence["paired"]) == set(expected_roles)
    for role, ids in expected_roles.items():
        assert evidence["paired"][role]["groups"] == ids and len(
            evidence["paired"][role]["offsets"]
        ) == len(ids)
        for (x, y), g in zip(evidence["paired"][role]["offsets"], ids):
            same(x, Q((b if role == "baseline" else a)[g]["mae_exact"]))
            same(y, groups.index(g))
    assert len(evidence["connectors"]) == 12
    for record, g in zip(evidence["connectors"], groups):
        assert record["group"] == g
        for point, value in zip(
            record["xy"], [Q(b[g]["mae_exact"]), Q(a[g]["mae_exact"])]
        ):
            same(point[0], value)
            same(point[1], groups.index(g))
    role_sets = {
        "donor": [r for r in stations if int(r["fold"]) < 3],
        "validation": [r for r in stations if r["fold"] == "3"],
        "held_lower": [
            r for r in stations if r["fold"] == "4" and difference[r["group"]] <= 0
        ],
        "held_higher": [
            r for r in stations if r["fold"] == "4" and difference[r["group"]] > 0
        ],
    }
    assert set(evidence["map"]) == set(role_sets)
    for role, values in role_sets.items():
        assert evidence["map"][role]["stations"] == [
            r["station"] for r in values
        ] and len(evidence["map"][role]["offsets"]) == len(values)
        for point, r in zip(evidence["map"][role]["offsets"], values):
            same(point[0], r["longitude"])
            same(point[1], r["latitude"])
    held = sorted(r["station"] for r in stations if r["fold"] == "4")
    assert [r["station"] for r in evidence["map_labels"]] == held
    assert all(r["station"] == r["text"] for r in evidence["map_labels"])
    assert len(evidence["stress"]) == 2 and all(
        len(row) == 8 for row in evidence["stress"]
    )
    for i, meters in enumerate([100, 500]):
        for j, bearing in enumerate(range(0, 360, 45)):
            r = next(
                r
                for r in rows
                if r["policy"] == selected
                and r["scenario"] == f"shift{meters}m-b{bearing:03d}"
                and r["scope"] == "overall"
            )
            same(evidence["stress"][i][j], Q(r["mae_equal_group_exact"]))

    def light(rgb):
        return sum(
            x * w
            for x, w in zip(
                [
                    c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                    for c in rgb
                ],
                [0.2126, 0.7152, 0.0722],
            )
        )

    assert len(evidence["stress_annotations"]) == 16
    minimum = 100
    for annotation in evidence["stress_annotations"]:
        assert annotation["text"] == display(
            str(evidence["stress"][annotation["row"]][annotation["column"]]), 2
        )
        f, c = light(annotation["foreground"]), light(annotation["background"])
        ratio = (max(f, c) + 0.05) / (min(f, c) + 0.05)
        assert ratio >= 4.5
        minimum = min(minimum, ratio)
    overall = {
        r["policy"]: r
        for r in rows
        if r["scope"] == "overall" and r["scenario"] == "unshifted"
    }
    assert (
        display(
            Q(overall[selected]["mae_equal_group_exact"])
            - Q(overall[base]["mae_equal_group_exact"])
        )
        in evidence["references"]["paired_note"]
    )
    bootstrap = json.loads(
        (ROOT / "results/BOOTSTRAP_SUMMARY.json").read_text(encoding="utf-8")
    )
    for key in ["lower_exact", "upper_exact"]:
        assert display(bootstrap[key]) in evidence["references"]["paired_note"]
    for policy in [selected, base]:
        assert (
            display(overall[policy]["mae_equal_group_exact"])
            in evidence["references"]["stress_note"]
        )
    manifest = json.loads((ROOT / "figures/MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest) == 9
    for name, digest in manifest.items():
        assert (
            hashlib.sha256((ROOT / "figures" / name).read_bytes()).hexdigest() == digest
        ), name
    return dict(
        status="PASS",
        actual_artist_values=checks,
        map_labels=12,
        heatmap_annotation_and_contrast_checks=16,
        minimum_annotation_contrast=minimum,
        export_hashes=9,
    )


if __name__ == "__main__":
    result = verify()
    (ROOT / "figures/VERIFICATION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
