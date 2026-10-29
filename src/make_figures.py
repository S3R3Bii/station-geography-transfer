"""Original complete-case figures with evidence read back from plot artists."""

import csv
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.ticker import MaxNLocator
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def light(color):
    return sum(
        v * w
        for v, w in zip(
            [
                c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in to_rgb(color)
            ],
            [0.2126, 0.7152, 0.0722],
        )
    )


def main():
    with (ROOT / "results/held-metrics.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        metrics = list(csv.DictReader(stream))
    with (ROOT / "data/source/station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        stations = [r for r in csv.DictReader(stream) if r["eligible"] == "1"]
    selected = json.loads((ROOT / "SELECTION.json").read_text(encoding="utf-8"))[
        "selected"
    ]["policy"]
    baseline = "pooled_weekday_w84"
    group = lambda p: {
        r["unit"]: r
        for r in metrics
        if r["scenario"] == "unshifted"
        and r["policy"] == p
        and r["scope"] == "coordinate_group"
    }
    geo, pool = group(selected), group(baseline)
    ids = sorted(geo)
    differences = {
        s: float(Q(geo[s]["mae_exact"]) - Q(pool[s]["mae_exact"])) for s in ids
    }
    overall = {
        r["policy"]: r
        for r in metrics
        if r["scenario"] == "unshifted" and r["scope"] == "overall"
    }
    bootstrap = json.loads(
        (ROOT / "results/BOOTSTRAP_SUMMARY.json").read_text(encoding="utf-8")
    )
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "station06-fixed",
        }
    )
    dest = ROOT / "figures"
    dest.mkdir(exist_ok=True)
    evidence = {
        "paired": {},
        "connectors": [],
        "map": {},
        "map_labels": [],
        "stress": [],
        "stress_annotations": [],
        "references": {},
    }
    exports = {}

    def save(fig, name):
        for extension in ["pdf", "svg", "png"]:
            path = dest / (name + "." + extension)
            options = {}
            if extension == "pdf":
                options["metadata"] = {
                    "CreationDate": None,
                    "ModDate": None,
                    "Creator": "Original study06 figure",
                }
            if extension == "svg":
                options["metadata"] = {"Date": None}
            if extension == "png":
                options["dpi"] = 170
            fig.savefig(path, **options)
            if extension == "svg":
                path.write_bytes(
                    (
                        "\n".join(
                            line.rstrip()
                            for line in path.read_text(encoding="utf-8").splitlines()
                        )
                        + "\n"
                    ).encode()
                )
            exports[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.3, 4.9))
    fig.subplots_adjust(left=0.12, right=0.98, bottom=0.29, top=0.81)
    fig.suptitle(
        "The selected model lowers error in most held groups",
        y=0.975,
        fontweight="bold",
        fontsize=13,
    )
    fig.text(
        0.5,
        0.895,
        "Idealized prior-day counts; all 12 held groups; 184 dates each; two higher-error groups retained",
        ha="center",
        fontsize=9,
    )
    for i, station in enumerate(ids):
        a, b = float(Q(pool[station]["mae_exact"])), float(Q(geo[station]["mae_exact"]))
        (line,) = ax.plot(
            [a, b],
            [i, i],
            color="#b45521" if b > a else "#bbbbbb",
            linewidth=1.5,
            zorder=1,
        )
        evidence["connectors"].append(
            dict(group=station, xy=line.get_xydata().tolist())
        )
    for role, subset, color, marker, label in [
        ("baseline", ids, "#777777", "o", "Pooled baseline"),
        (
            "geo_lower",
            [s for s in ids if differences[s] <= 0],
            "#166d8a",
            "D",
            "Geo lower error",
        ),
        (
            "geo_higher",
            [s for s in ids if differences[s] > 0],
            "#b45521",
            "X",
            "Geo higher error",
        ),
    ]:
        collection = ax.scatter(
            [
                float(Q((pool if role == "baseline" else geo)[s]["mae_exact"]))
                for s in subset
            ],
            [ids.index(s) for s in subset],
            s=40,
            color=color,
            marker=marker,
            label=label,
            zorder=3,
        )
        evidence["paired"][role] = dict(
            groups=subset, offsets=collection.get_offsets().tolist()
        )
    ax.set_yticks(range(len(ids)), ids)
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.grid(axis="x", alpha=0.18)
    ax.set_xlabel("Mean absolute error (recorded departures/day)")
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.11),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    note = f"MAE difference: {float(Q(overall[selected]['mae_equal_group_exact'])-Q(overall[baseline]['mae_equal_group_exact'])):.3f}; conditional group-resampling range {float(Q(bootstrap['lower_exact'])):.3f} to {float(Q(bootstrap['upper_exact'])):.3f}"
    text = fig.text(0.5, 0.065, note, ha="center", fontsize=8)
    evidence["references"]["paired_note"] = text.get_text()
    fig.text(
        0.5,
        0.02,
        "Model bundles differ in temporal settings; recorded counts do not establish stock or relocation effects.",
        ha="center",
        fontsize=8,
    )
    save(fig, "held_group_errors")
    fig, ax = plt.subplots(figsize=(8.3, 5.4))
    fig.subplots_adjust(left=0.1, right=0.98, bottom=0.28, top=0.83)
    fig.suptitle(
        "Recorded geometry fixes the donor and held groups",
        y=0.975,
        fontweight="bold",
        fontsize=14,
    )
    fig.text(
        0.5,
        0.905,
        "First-quarter medians rounded to four decimals; nearby IDs grouped before count evaluation",
        ha="center",
        fontsize=9,
    )
    role_sets = {
        "donor": [r for r in stations if int(r["fold"]) < 3],
        "validation": [r for r in stations if r["fold"] == "3"],
        "held_lower": [
            r for r in stations if r["fold"] == "4" and differences[r["group"]] <= 0
        ],
        "held_higher": [
            r for r in stations if r["fold"] == "4" and differences[r["group"]] > 0
        ],
    }
    style = {
        "donor": ("#aaaaaa", "o", 19, "Donor IDs (49)"),
        "validation": ("#166d8a", "^", 30, "Validation groups (22)"),
        "held_lower": ("#638030", "D", 48, "Held lower error (10)"),
        "held_higher": ("#b45521", "X", 58, "Held higher error (2)"),
    }
    for role, rows in role_sets.items():
        color, marker, size, label = style[role]
        options = (
            {"facecolors": "none", "edgecolors": color}
            if role == "validation"
            else {"color": color}
        )
        collection = ax.scatter(
            [float(r["longitude"]) for r in rows],
            [float(r["latitude"]) for r in rows],
            marker=marker,
            s=size,
            label=label,
            **options,
        )
        evidence["map"][role] = dict(
            stations=[r["station"] for r in rows],
            offsets=collection.get_offsets().tolist(),
        )
    for i, row in enumerate(
        sorted([r for r in stations if r["fold"] == "4"], key=lambda r: r["station"])
    ):
        text = ax.annotate(
            row["station"],
            (float(row["longitude"]), float(row["latitude"])),
            xytext=(5, 5 if i % 2 == 0 else -10),
            textcoords="offset points",
            fontsize=8,
            color="#222222",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.5),
        )
        evidence["map_labels"].append(
            dict(station=row["station"], text=text.get_text())
        )
    ax.set_xlabel("Recorded median longitude (degrees)")
    ax.set_ylabel("Recorded median latitude (degrees)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.xaxis.set_major_locator(MaxNLocator(5))
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.grid(alpha=0.15)
    ax.set_aspect(
        1
        / math.cos(
            math.radians(sum(float(r["latitude"]) for r in stations) / len(stations))
        )
    )
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.045),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    fig.text(
        0.5,
        0.015,
        "Nominal IDs and coordinate groups are proxies; no verified physical-site lineage or road/accessibility map.",
        ha="center",
        fontsize=8,
    )
    save(fig, "coordinate_groups")
    bearings = [0, 45, 90, 135, 180, 225, 270, 315]
    grid = []
    for meters in [100, 500]:
        grid.append(
            [
                float(
                    Q(
                        next(
                            r["mae_equal_group_exact"]
                            for r in metrics
                            if r["scenario"] == f"shift{meters}m-b{b:03d}"
                            and r["policy"] == selected
                            and r["scope"] == "overall"
                        )
                    )
                )
                for b in bearings
            ]
        )
    fig, ax = plt.subplots(figsize=(8.3, 3.7))
    fig.subplots_adjust(left=0.11, right=0.85, bottom=0.28, top=0.76)
    fig.suptitle(
        "Metadata displacement changes forecast error",
        y=0.97,
        fontweight="bold",
        fontsize=14,
    )
    fig.text(
        0.5,
        0.86,
        "Frozen geographic model; unchanged count labels; every declared displacement",
        ha="center",
        fontsize=9,
    )
    artist = ax.imshow(
        grid,
        aspect="auto",
        interpolation="nearest",
        cmap="YlOrRd",
        vmin=0,
        vmax=float(Q(overall[baseline]["mae_equal_group_exact"])),
    )
    evidence["stress"] = artist.get_array().tolist()
    ax.set_xticks(range(8), ["N", "NE", "E", "SE", "S", "SW", "W", "NW"])
    ax.set_yticks(range(2), ["100 m", "500 m"])
    ax.set_xlabel("Synthetic metadata shift bearing")
    for i in range(2):
        for j in range(8):
            background = artist.cmap(artist.norm(grid[i][j]))[:3]
            l = light(background)
            foreground = "black" if (l + 0.05) / 0.05 >= 1.05 / (l + 0.05) else "white"
            text = ax.text(
                j,
                i,
                format(grid[i][j], ".2f"),
                ha="center",
                va="center",
                fontsize=9,
                color=foreground,
            )
            evidence["stress_annotations"].append(
                dict(
                    row=i,
                    column=j,
                    text=text.get_text(),
                    foreground=list(to_rgb(text.get_color())),
                    background=list(background),
                )
            )
    fig.colorbar(
        artist,
        cax=fig.add_axes([0.885, 0.28, 0.017, 0.48]),
        label="MAE (departures/day)",
    )
    reference = f"Unshifted geo MAE {float(Q(overall[selected]['mae_equal_group_exact'])):.3f}; pooled baseline {float(Q(overall[baseline]['mae_equal_group_exact'])):.3f}"
    text = fig.text(0.5, 0.105, reference, ha="center", fontsize=9)
    evidence["references"]["stress_note"] = text.get_text()
    fig.text(
        0.5,
        0.025,
        "Synthetic coordinate errors do not estimate the effect of physically relocating a station.",
        ha="center",
        fontsize=8,
    )
    save(fig, "geography_sensitivity")
    (dest / "ARTIST_VALUES.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    (dest / "MANIFEST.json").write_text(
        json.dumps(exports, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            dict(state="ORIGINAL_FIGURES_CREATED_CHECKS_PENDING", exports=len(exports))
        )
    )


if __name__ == "__main__":
    main()
