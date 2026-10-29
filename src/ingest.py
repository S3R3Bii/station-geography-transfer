"""Aggregate authorized source files privately; publish only purpose-bound facts."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction as Q
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from geo import distance

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ResearchPortfolio-purpose-bound-analysis/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def weighted_median(values):
    n = sum(values.values())
    assert n > 0
    low, high = (n - 1) // 2, n // 2
    cumulative = 0
    selected = []
    for value, count in sorted(values.items()):
        for index in [low, high]:
            if cumulative <= index < cumulative + count:
                selected.append(value)
        cumulative += count
    assert len(selected) == 2
    with localcontext() as context:
        context.prec = 60
        return sum(selected) / 2


def write_csv(path, fields, rows, compressed=False):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    data = stream.getvalue().encode("utf-8")
    path.write_bytes(gzip.compress(data, mtime=0) if compressed else data)


def capture(private_dir):
    private_dir = Path(private_dir)
    assert private_dir.is_dir()
    config = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
    dest = ROOT / "data/source"
    counts, coordinate_pairs, initial_total = Counter(), defaultdict(Counter), Counter()
    initial_months = defaultdict(set)
    month_control = {m: Counter() for m in range(1, 13)}
    sources = []
    for item in config["source"]["objects"]:
        path = private_dir / item["key"]
        url = config["source"]["archive_base"] + item["key"]
        if not path.exists():
            path.write_bytes(get(url))
        packed = path.read_bytes()
        assert len(packed) == item["size"], "Source object size changed"
        filemonth = int(item["key"][7:9])
        record = dict(archive=item["key"], url=url, sha256=sha(packed), bytes=len(packed), object_modified=item["modified"], etag=item["etag"], members=[])
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            members = [m for m in archive.infolist() if m.filename.lower().endswith(".csv") and "__MACOSX" not in Path(m.filename).parts]
            assert members, "No eligible CSV member"
            for member in members:
                data = archive.read(member)
                reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
                assert len(reader.fieldnames) == len(set(reader.fieldnames))
                assert set(config["source"]["columns"]) <= set(reader.fieldnames)
                quality = Counter()
                for row in reader:
                    quality["rows"] += 1
                    try:
                        day = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00")).date()
                    except (ValueError, TypeError):
                        quality["invalid_date"] += 1; continue
                    if day.year != 2024:
                        quality["outside_year"] += 1; continue
                    if day.month != filemonth:
                        quality["file_month_mismatch"] += 1
                    station = row["start_station_id"].strip()
                    if not station:
                        quality["unknown_station"] += 1; month_control[day.month]["unknown_station_records"] += 1; continue
                    quality["known_station"] += 1; month_control[day.month]["known_station_records"] += 1
                    counts[station, day] += 1
                    if day < date(2024, 4, 1):
                        initial_total[station] += 1; initial_months[station].add(day.month)
                        try:
                            lat, lon = Decimal(row["start_lat"]), Decimal(row["start_lng"])
                            valid = lat.is_finite() and lon.is_finite() and 40 <= lat <= 41 and -75 <= lon <= -73
                        except Exception:
                            valid = False
                        if valid:
                            coordinate_pairs[station][lat, lon] += 1
                assert quality["rows"] == quality["invalid_date"] + quality["outside_year"] + quality["unknown_station"] + quality["known_station"]
                record["members"].append(dict(name=member.filename, sha256=sha(data), bytes=len(data), quality=dict(quality)))
        sources.append(record)
        print(json.dumps(dict(captured_archive=item["key"], rows=sum(m["quality"]["rows"] for m in record["members"]))), flush=True)
    eligibility = []
    quantum = Decimal("0.0001")
    for station in sorted(initial_total):
        pairs = coordinate_pairs[station]
        valid_count = sum(pairs.values())
        fraction = Q(valid_count, initial_total[station])
        reasons = []
        if initial_months[station] != {1, 2, 3}:
            reasons.append("not_positive_each_initial_month")
        if fraction < Q(95, 100):
            reasons.append("valid_coordinate_fraction_below_95pct")
        lat = lon = radius = ""
        if valid_count:
            lat_values, lon_values = Counter(), Counter()
            for (a, b), n in pairs.items():
                lat_values[a] += n; lon_values[b] += n
            rawlat, rawlon = weighted_median(lat_values), weighted_median(lon_values)
            ordered = sorted((distance(float(rawlat), float(rawlon), float(a), float(b)), n) for (a, b), n in pairs.items())
            rank, total = (95 * valid_count + 99) // 100, 0
            for value, n in ordered:
                total += n
                if total >= rank:
                    radius = value; break
            lat = format(rawlat.quantize(quantum, rounding=ROUND_HALF_EVEN), ".4f")
            lon = format(rawlon.quantize(quantum, rounding=ROUND_HALF_EVEN), ".4f")
            if radius > .150:
                reasons.append("initial_coordinate_radius_above_150m")
        else:
            reasons.append("no_valid_initial_coordinates")
        eligibility.append(dict(station=station, initial_records=initial_total[station], valid_coordinate_records=valid_count, valid_fraction_exact=str(fraction), observed_initial_months="|".join(map(str, sorted(initial_months[station]))), latitude=lat, longitude=lon, radius95_km=radius, eligible=int(not reasons), exclusion_reason="|".join(reasons), group="", fold=""))
    selected = {row["station"]: row for row in eligibility if row["eligible"]}
    parent = {station: station for station in selected}
    def find(station):
        while parent[station] != station:
            parent[station] = parent[parent[station]]; station = parent[station]
        return station
    stations = sorted(selected)
    for i, a in enumerate(stations):
        for b in stations[i + 1:]:
            ra, rb = selected[a], selected[b]
            if distance(float(ra["latitude"]), float(ra["longitude"]), float(rb["latitude"]), float(rb["longitude"])) <= .100:
                x, y = find(a), find(b)
                parent[max(x, y)] = min(x, y)
    for station, row in selected.items():
        group = find(station)
        row["group"] = group
        row["fold"] = int.from_bytes(hashlib.sha256(("study06-v1|" + group).encode()).digest()[:8], "big") % 5
    donor_count = sum(row["fold"] in [0, 1, 2] for row in selected.values())
    group_counts = {fold: len({row["group"] for row in selected.values() if row["fold"] == fold}) for fold in range(5)}
    assert donor_count >= 10 and group_counts[3] >= 2 and group_counts[4] >= 2, "Fixed cohort/fold sufficiency gate failed"
    rows = []
    for station in stations:
        for offset in range(366):
            day = date(2024, 1, 1) + timedelta(days=offset)
            value = counts[station, day]
            rows.append(dict(station=station, date=day.isoformat(), departures=value))
            month_control[day.month]["selected_records"] += value
    controls = []
    for month, control in sorted(month_control.items()):
        controls.append(dict(month=month, known_station_records=control["known_station_records"], unknown_station_records=control["unknown_station_records"], selected_records=control["selected_records"], unselected_known_records=control["known_station_records"] - control["selected_records"]))
    write_csv(dest / "counts.csv.gz", ["station", "date", "departures"], rows, True)
    write_csv(dest / "station_eligibility.csv", list(eligibility[0]), eligibility)
    write_csv(dest / "monthly_controls.csv", list(controls[0]), controls)
    listing = get("https://s3.amazonaws.com/tripdata?prefix=JC-2024")
    (private_dir / "object-list-after.xml").write_bytes(listing)
    doc = ET.fromstring(listing); ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    after = {e.findtext("s:Key", namespaces=ns): (int(e.findtext("s:Size", namespaces=ns)), e.findtext("s:LastModified", namespaces=ns), e.findtext("s:ETag", namespaces=ns)) for e in doc.findall("s:Contents", ns)}
    for item in config["source"]["objects"]:
        assert after[item["key"]] == (item["size"], item["modified"], item["etag"]), "Object metadata changed during capture"
    manifest = dict(retrieved_utc=datetime.now(timezone.utc).isoformat(), source_policy=config["source"]["policy"], publication_scope="Minimal coarse derived inputs within this noncommercial independent analysis; not standalone source redistribution. Original ZIP/CSV and customer/trajectory attributes private and excluded.", sources=sources, object_list_after_sha256=sha(listing), selected_stations=len(stations), donor_stations=donor_count, coordinate_groups_by_fold=group_counts, projection_hashes={name: sha((dest / name).read_bytes()) for name in ["counts.csv.gz", "station_eligibility.csv", "monthly_controls.csv"]}, source_quality="Recorded row/file consistency only; provider completeness, physical lineage, true demand and historical availability unverified.")
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(state="CAPTURE_COMPLETE_INDEPENDENT_CHECK_PENDING", source_rows=sum(m["quality"]["rows"] for s in sources for m in s["members"]), selected_stations=len(stations), donor_stations=donor_count, groups_by_fold=group_counts, grid_rows=len(rows))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("private_dir"); capture(parser.parse_args().private_dir)
