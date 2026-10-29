"""Independent pandas parsing and coordinate reconstruction of private originals."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction as Q
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["started_at", "start_station_id", "start_lat", "start_lng"]


def arc(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, [lat1, lon1, lat2, lon2])
    u = np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])
    v = np.array([np.cos(c) * np.cos(d), np.cos(c) * np.sin(d), np.sin(c)])
    return 6371 * float(np.arctan2(np.linalg.norm(np.cross(u, v)), np.dot(u, v)))


def row_hash(rows):
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        digest.update(
            (
                json.dumps(list(row), separators=(",", ":"), ensure_ascii=False) + "\n"
            ).encode("utf-8")
        )
        count += 1
    return digest.hexdigest(), count


def verify(private_dir):
    private_dir = Path(private_dir)
    dest = ROOT / "data/source"
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    counts = Counter()
    initial = []
    month_known = Counter()
    month_unknown = Counter()
    members = []
    selected_scalar_checks = 0
    for source in manifest["sources"]:
        packed = (private_dir / source["archive"]).read_bytes()
        assert hashlib.sha256(packed).hexdigest() == source["sha256"]
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            for member in source["members"]:
                data = archive.read(member["name"])
                assert hashlib.sha256(data).hexdigest() == member["sha256"]
                standard = csv.DictReader(
                    io.StringIO(data.decode("utf-8-sig"), newline="")
                )
                expected, n = row_hash(([r[f] for f in FIELDS] for r in standard))
                frame = pd.read_csv(
                    io.BytesIO(data),
                    usecols=FIELDS,
                    dtype=str,
                    keep_default_na=False,
                    encoding="utf-8-sig",
                )
                actual, n2 = row_hash(frame[FIELDS].itertuples(index=False, name=None))
                assert actual == expected and n2 == n == member["quality"]["rows"]
                selected_scalar_checks += 4 * n
                members.append(
                    dict(
                        archive=source["archive"],
                        member=member["name"],
                        sha256=member["sha256"],
                        canonical_selected_field_rows_sha256=actual,
                        rows=n,
                    )
                )
                timestamp = pd.to_datetime(
                    frame["started_at"], format="mixed", errors="coerce"
                )
                valid = timestamp.notna()
                year = timestamp.dt.year
                quality = Counter(
                    rows=n,
                    invalid_date=int((~valid).sum()),
                    outside_year=int((valid & (year != 2024)).sum()),
                )
                frame = frame.loc[valid & (year == 2024)].copy()
                frame["day"] = timestamp.loc[frame.index].dt.date
                frame["station"] = frame["start_station_id"].str.strip()
                quality["unknown_station"] = int((frame["station"] == "").sum())
                quality["known_station"] = int((frame["station"] != "").sum())
                filemonth = int(source["archive"][7:9])
                quality["file_month_mismatch"] = int(
                    (timestamp.loc[frame.index].dt.month != filemonth).sum()
                )
                for field, value in quality.items():
                    assert member["quality"].get(field, 0) == value, (
                        source["archive"],
                        field,
                    )
                unknown = frame.loc[frame["station"] == ""]
                for month, value in (
                    unknown.groupby(unknown["day"].map(lambda x: x.month))
                    .size()
                    .items()
                ):
                    month_unknown[int(month)] += int(value)
                known = frame.loc[frame["station"] != ""].copy()
                for month, value in (
                    known.groupby(known["day"].map(lambda x: x.month)).size().items()
                ):
                    month_known[int(month)] += int(value)
                for (station, day), value in (
                    known.groupby(["station", "day"]).size().items()
                ):
                    counts[station, day] += int(value)
                initial.append(known.loc[known["day"] < date(2024, 4, 1)])
    initial = pd.concat(initial, ignore_index=True)
    with (dest / "station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        eligibility = list(csv.DictReader(stream))
    actual = {r["station"]: r for r in eligibility}
    assert len(actual) == len(eligibility)
    groups = {station: frame for station, frame in initial.groupby("station")}
    assert set(actual) == set(groups)
    numeric_checks = 0
    float_checks = 0
    selected = {}

    def equal(row, key, value):
        nonlocal numeric_checks
        assert row[key] == str(value), (row["station"], key, row[key], value)
        numeric_checks += 1

    for station, frame in groups.items():
        row = actual[station]
        n = len(frame)
        months = sorted({d.month for d in frame["day"]})
        lat = pd.to_numeric(frame["start_lat"], errors="coerce")
        lon = pd.to_numeric(frame["start_lng"], errors="coerce")
        good = frame.loc[lat.between(40, 41) & lon.between(-75, -73)]
        fraction = Q(len(good), n)
        reasons = []
        if months != [1, 2, 3]:
            reasons.append("not_positive_each_initial_month")
        if fraction < Q(95, 100):
            reasons.append("valid_coordinate_fraction_below_95pct")
        equal(row, "initial_records", n)
        equal(row, "valid_coordinate_records", len(good))
        equal(row, "valid_fraction_exact", fraction)
        equal(row, "observed_initial_months", "|".join(map(str, months)))
        if len(good):
            with localcontext() as ctx:
                ctx.prec = 60
                medlat = statistics.median([Decimal(x) for x in good["start_lat"]])
                medlon = statistics.median([Decimal(x) for x in good["start_lng"]])
            equal(
                row,
                "latitude",
                format(
                    medlat.quantize(Decimal(".0001"), rounding=ROUND_HALF_EVEN), ".4f"
                ),
            )
            equal(
                row,
                "longitude",
                format(
                    medlon.quantize(Decimal(".0001"), rounding=ROUND_HALF_EVEN), ".4f"
                ),
            )
            a = np.radians(good["start_lat"].astype(float).to_numpy())
            b = np.radians(good["start_lng"].astype(float).to_numpy())
            vectors = np.column_stack(
                [np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)]
            )
            c, d = math.radians(float(medlat)), math.radians(float(medlon))
            center = np.array(
                [math.cos(c) * math.cos(d), math.cos(c) * math.sin(d), math.sin(c)]
            )
            distances = 6371 * np.arctan2(
                np.linalg.norm(np.cross(vectors, center), axis=1), vectors @ center
            )
            rank = math.ceil(0.95 * len(good))
            radius = float(np.partition(distances, rank - 1)[rank - 1])
            assert abs(float(row["radius95_km"]) - radius) <= 1e-8
            float_checks += 1
            if radius > 0.150:
                reasons.append("initial_coordinate_radius_above_150m")
        else:
            equal(row, "latitude", "")
            equal(row, "longitude", "")
            equal(row, "radius95_km", "")
            reasons.append("no_valid_initial_coordinates")
        equal(row, "exclusion_reason", "|".join(reasons))
        equal(row, "eligible", int(not reasons))
        if not reasons:
            selected[station] = row
    graph = {station: set() for station in selected}
    names = sorted(selected)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            ra, rb = selected[a], selected[b]
            if (
                arc(
                    float(ra["latitude"]),
                    float(ra["longitude"]),
                    float(rb["latitude"]),
                    float(rb["longitude"]),
                )
                <= 0.100
            ):
                graph[a].add(b)
                graph[b].add(a)
    remaining = set(selected)
    while remaining:
        todo = [min(remaining)]
        component = set()
        while todo:
            value = todo.pop()
            if value in component:
                continue
            component.add(value)
            todo.extend(graph[value] - component)
        remaining -= component
        key = min(component)
        fold = (
            int.from_bytes(
                hashlib.sha256(("study06-v1|" + key).encode()).digest()[:8], "big"
            )
            % 5
        )
        for station in component:
            equal(selected[station], "group", key)
            equal(selected[station], "fold", fold)
    with gzip.open(dest / "counts.csv.gz", "rt", newline="") as stream:
        projected = list(csv.DictReader(stream))
    seen = set()
    month_selected = Counter()
    for row in projected:
        station = row["station"]
        day = date.fromisoformat(row["date"])
        assert station in selected and day.year == 2024
        key = (station, day)
        assert key not in seen
        seen.add(key)
        assert int(row["departures"]) == counts[key]
        numeric_checks += 3
        month_selected[day.month] += int(row["departures"])
    assert len(seen) == len(selected) * 366
    with (dest / "monthly_controls.csv").open(encoding="utf-8", newline="") as stream:
        controls = list(csv.DictReader(stream))
    assert len(controls) == 12
    for row in controls:
        month = int(row["month"])
        expected = dict(
            month=month,
            known_station_records=month_known[month],
            unknown_station_records=month_unknown[month],
            selected_records=month_selected[month],
            unselected_known_records=month_known[month] - month_selected[month],
        )
        assert row == {k: str(v) for k, v in expected.items()}
        numeric_checks += 5
    for name, digest in manifest["projection_hashes"].items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == digest
    result = dict(
        status="PASS",
        source_rows=sum(m["rows"] for m in members),
        selected_field_scalars_matched_by_canonical_parser_hash=selected_scalar_checks,
        projection_and_geometry_exact_checks=numeric_checks,
        coordinate_radius_tolerance_checks=float_checks,
        selected_stations=len(selected),
        grid_rows=len(projected),
        members=members,
        projection_hashes=manifest["projection_hashes"],
        scope="Independent pandas C-parser versus standard CSV selected-field hashes; independent list medians, unit-vector angular radii, graph components and count controls. Source truth, physical lineage, occupancy and historical availability not established.",
    )
    (dest / "INDEPENDENT_PARSE.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["members", "projection_hashes"]
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("private_dir")
    verify(parser.parse_args().private_dir)
