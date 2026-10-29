"""Validate captured coarse inputs, recorded parser proof and spatial fold contracts."""

import csv
from datetime import date
from fractions import Fraction as Q
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def arc(a, b, c, d):
    a, b, c, d = map(math.radians, [a, b, c, d])
    u = [math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)]
    v = [math.cos(c) * math.cos(d), math.cos(c) * math.sin(d), math.sin(c)]
    cross = [
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    ]
    return 6371 * math.atan2(
        math.sqrt(sum(x * x for x in cross)), sum(x * y for x, y in zip(u, v))
    )


def verify(root=ROOT):
    root = Path(root)
    dest = root / "data/source"
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    proof = json.loads((dest / "INDEPENDENT_PARSE.json").read_text(encoding="utf-8"))
    config = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    assert (
        proof["status"] == "PASS"
        and proof["projection_hashes"] == manifest["projection_hashes"]
    )
    for name, digest in manifest["projection_hashes"].items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == digest
    assert len(manifest["sources"]) == len(config["source"]["objects"]) == 12
    for original, captured in zip(config["source"]["objects"], manifest["sources"]):
        assert (
            original["key"] == captured["archive"]
            and original["size"] == captured["bytes"]
            and original["modified"] == captured["object_modified"]
            and original["etag"] == captured["etag"]
        )
    source_rows = sum(
        m["quality"]["rows"] for s in manifest["sources"] for m in s["members"]
    )
    assert (
        source_rows == proof["source_rows"]
        and 4 * source_rows
        == proof["selected_field_scalars_matched_by_canonical_parser_hash"]
    )
    with (dest / "station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        allstations = list(csv.DictReader(stream))
    selected = {r["station"]: r for r in allstations if r["eligible"] == "1"}
    assert len({r["station"] for r in allstations}) == len(allstations)
    for row in allstations:
        passed = (
            row["observed_initial_months"] == "1|2|3"
            and Q(row["valid_fraction_exact"]) >= Q(95, 100)
            and row["radius95_km"] != ""
            and float(row["radius95_km"]) <= 0.150
        )
        assert passed == (row["eligible"] == "1")
        assert 0 <= int(row["valid_coordinate_records"]) <= int(row["initial_records"])
        assert Q(row["valid_fraction_exact"]) == Q(
            int(row["valid_coordinate_records"]), int(row["initial_records"])
        )
        if row["eligible"] == "1":
            assert (
                row["exclusion_reason"] == ""
                and 40 <= float(row["latitude"]) <= 41
                and -75 <= float(row["longitude"]) <= -73
            )
    graph = {s: set() for s in selected}
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
        stack = [min(remaining)]
        component = set()
        while stack:
            station = stack.pop()
            if station in component:
                continue
            component.add(station)
            stack.extend(graph[station] - component)
        remaining -= component
        key = min(component)
        fold = (
            int.from_bytes(
                hashlib.sha256(("study06-v1|" + key).encode()).digest()[:8], "big"
            )
            % 5
        )
        assert all(
            selected[s]["group"] == key and int(selected[s]["fold"]) == fold
            for s in component
        )
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE counts(station TEXT,day TEXT,n INT CHECK(n>=0),PRIMARY KEY(station,day))"
    )
    gridchecks = 0
    with gzip.open(dest / "counts.csv.gz", "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            day = date.fromisoformat(row["date"])
            assert day.year == 2024 and row["station"] in selected
            db.execute(
                "INSERT INTO counts VALUES(?,?,?)",
                (row["station"], row["date"], int(row["departures"])),
            )
            gridchecks += 3
    for station, n, first, last, initial in db.execute(
        "SELECT station,COUNT(*),MIN(day),MAX(day),SUM(CASE WHEN day<'2024-04-01' THEN n ELSE 0 END) FROM counts GROUP BY station"
    ):
        assert (
            n == 366
            and first == "2024-01-01"
            and last == "2024-12-31"
            and initial == int(selected[station]["initial_records"])
        )
        gridchecks += 4
    assert (
        db.execute("SELECT COUNT(DISTINCT station) FROM counts").fetchone()[0]
        == len(selected)
        == proof["selected_stations"]
    )
    with (dest / "monthly_controls.csv").open(encoding="utf-8", newline="") as stream:
        controls = list(csv.DictReader(stream))
    assert len(controls) == 12
    for row in controls:
        month = int(row["month"])
        total = db.execute(
            "SELECT SUM(n) FROM counts WHERE CAST(substr(day,6,2) AS INT)=?", (month,)
        ).fetchone()[0]
        assert total == int(row["selected_records"])
        assert total + int(row["unselected_known_records"]) == int(
            row["known_station_records"]
        )
        gridchecks += 2
    member_quality = [m["quality"] for s in manifest["sources"] for m in s["members"]]
    assert sum(int(r["known_station_records"]) for r in controls) == sum(
        r.get("known_station", 0) for r in member_quality
    )
    assert sum(int(r["unknown_station_records"]) for r in controls) == sum(
        r.get("unknown_station", 0) for r in member_quality
    )
    assert source_rows == sum(
        sum(
            r.get(k, 0)
            for k in [
                "invalid_date",
                "outside_year",
                "known_station",
                "unknown_station",
            ]
        )
        for r in member_quality
    )
    folds = {
        str(f): len({r["group"] for r in selected.values() if int(r["fold"]) == f})
        for f in range(5)
    }
    assert folds == manifest["coordinate_groups_by_fold"]
    assert (
        sum(int(r["fold"]) < 3 for r in selected.values()) >= 10
        and int(folds["3"]) >= 2
        and int(folds["4"]) >= 2
    )
    return dict(
        status="PASS",
        grid_and_control_checks=gridchecks,
        source_rows=source_rows,
        selected_stations=len(selected),
        grid_rows=len(selected) * 366,
        coordinate_groups_by_fold=folds,
        source_truth="Captured published-record consistency and proxy coordinate groups only; no physical lineage, stock/demand, historical-vintage or prospective-availability clearance.",
    )


if __name__ == "__main__":
    result = verify()
    (ROOT / "data/source/VERIFICATION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
