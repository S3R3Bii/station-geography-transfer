"""Independent numeric display, scope, approved-byte and PDF-action checks."""

import csv
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction as Q
import gzip
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def display(value, places=3):
    q = Q(value)
    with localcontext() as context:
        context.prec = 90
        value = (Decimal(q.numerator) / Decimal(q.denominator)).quantize(
            Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN
        )
        return format(value, ",." + str(places) + "f")


def verify():
    def read(name):
        with (ROOT / "results" / name).open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    tex = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    md = (ROOT / "DECISION_SUMMARY.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    selected = json.loads((ROOT / "SELECTION.json").read_text(encoding="utf-8"))
    policy = selected["selected"]["policy"]
    base = "pooled_weekday_w84"
    held = read("held-metrics.csv")
    validation = read("validation-metrics.csv")
    checks = 0

    def row(fields, markdown=True):
        nonlocal checks
        values = list(map(str, fields))
        assert " & ".join(values) + " " + chr(92) * 2 in tex, values
        checks += len(values)
        if markdown:
            assert "| " + " | ".join(values) + " |" in md, values
            checks += len(values)

    with (ROOT / "data/source/station_eligibility.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        allstations = list(csv.DictReader(stream))
    stations = [r for r in allstations if r["eligible"] == "1"]
    assert len(allstations) == 99 and len(stations) == 83
    checks += 2
    for fold in range(5):
        values = [r for r in stations if int(r["fold"]) == fold]
        row(
            [
                fold,
                len(values),
                len({r["group"] for r in values}),
                "Donor" if fold < 3 else "Validation" if fold == 3 else "Held",
            ],
            False,
        )
    for calendar in ["weekday", "daytype"]:
        for k in [3, 5, 10]:
            for power in [0, 1, 2]:
                scores = [
                    next(
                        r["mae_equal_group_exact"]
                        for r in validation
                        if r["policy"] == f"geo-w{window}-{calendar}-k{k}-p{power}"
                        and r["scope"] == "overall"
                    )
                    for window in [28, 56, 84]
                ]
                row(
                    [
                        "Weekday" if calendar == "weekday" else "Weekday/weekend",
                        k,
                        power,
                        *map(display, scores),
                    ]
                )
    overall = {
        r["policy"]: r
        for r in held
        if r["scenario"] == "unshifted" and r["scope"] == "overall"
    }
    for key, label in [(policy, "Geographic"), (base, "Pooled")]:
        r = overall[key]
        with localcontext() as context:
            context.prec = 80
            q = Q(r["mse_equal_group_exact"])
            root = (Decimal(q.numerator) / Decimal(q.denominator)).sqrt()
            rmse = format(
                root.quantize(Decimal(".001"), rounding=ROUND_HALF_EVEN), ".3f"
            )
        row(
            [
                label,
                display(r["mae_equal_group_exact"]),
                display(r["mse_equal_group_exact"]),
                rmse,
                display(100 * Q(r["wape_exact"])),
            ]
        )
    groups = {
        key: {
            r["unit"]: r
            for r in held
            if r["policy"] == key
            and r["scenario"] == "unshifted"
            and r["scope"] == "coordinate_group"
        }
        for key in [policy, base]
    }
    assert set(groups[policy]) == set(groups[base]) and len(groups[policy]) == 12
    checks += 2
    worse = []
    for group in sorted(groups[policy]):
        a, b = groups[policy][group], groups[base][group]
        difference = Q(a["mae_exact"]) - Q(b["mae_exact"])
        row(
            [
                group,
                a["n"],
                format(int(a["observed"]), ","),
                display(a["mae_exact"]),
                display(b["mae_exact"]),
                display(difference),
            ]
        )
        if difference > 0:
            worse.append(group)
    assert worse == ["HB408", "JC052"]
    checks += 1
    assert (
        display(
            abs(
                Q(groups[policy]["HB501"]["mae_exact"])
                - Q(groups[base]["HB501"]["mae_exact"])
            )
        )
        == "0.045"
    )
    checks += 1
    for month in sorted({r["period"] for r in held if r["scope"] == "month"}):
        a = next(
            r
            for r in held
            if r["policy"] == policy
            and r["scenario"] == "unshifted"
            and r["scope"] == "month"
            and r["period"] == month
        )
        b = next(
            r
            for r in held
            if r["policy"] == base
            and r["scenario"] == "unshifted"
            and r["scope"] == "month"
            and r["period"] == month
        )
        row(
            [
                month,
                a["n"],
                display(a["mae_equal_group_exact"]),
                display(b["mae_equal_group_exact"]),
                display(Q(a["mae_equal_group_exact"]) - Q(b["mae_equal_group_exact"])),
            ]
        )
    for meters, bearing in [(0, None)] + [
        (m, b) for m in [100, 500] for b in range(0, 360, 45)
    ]:
        scenario = "unshifted" if meters == 0 else f"shift{meters}m-b{bearing:03d}"
        value = Q(
            next(
                r["mae_equal_group_exact"]
                for r in held
                if r["policy"] == policy
                and r["scenario"] == scenario
                and r["scope"] == "overall"
            )
        )
        row(
            [
                meters,
                "n/a" if bearing is None else bearing,
                display(value),
                display(value - Q(overall[policy]["mae_equal_group_exact"])),
                display(value - Q(overall[base]["mae_equal_group_exact"])),
            ]
        )
        assert value < Q(overall[base]["mae_equal_group_exact"])
        checks += 1
    with gzip.open(
        ROOT / "results/held-predictions.csv.gz", "rt", newline=""
    ) as stream:
        predictions = list(csv.DictReader(stream))
    assert len(predictions) == 39744
    checks += 1
    for key in [policy, base]:
        values = [
            r
            for r in predictions
            if r["scenario"] == "unshifted" and r["policy"] == key
        ]
        assert len(values) == 2208 and sum(int(r["actual"]) for r in values) == 81839
        checks += 2
        group_abs = {}
        for group in groups[key]:
            sample = [r for r in values if r["group"] == group]
            assert len(sample) == 184 and len({r["station"] for r in sample}) == 1
            group_abs[group] = sum(
                abs(Q(r["prediction"]) - int(r["actual"])) for r in sample
            ) / len(sample)
            checks += 2
        assert sum(group_abs.values()) / len(group_abs) == Q(
            overall[key]["mae_equal_group_exact"]
        )
        checks += 1
    reduction = (
        100
        * (
            Q(overall[base]["mae_equal_group_exact"])
            - Q(overall[policy]["mae_equal_group_exact"])
        )
        / Q(overall[base]["mae_equal_group_exact"])
    )
    assert display(reduction, 1) == "44.8"
    checks += 1
    bootstrap = json.loads(
        (ROOT / "results/BOOTSTRAP_SUMMARY.json").read_text(encoding="utf-8")
    )
    assert (
        bootstrap["coordinate_groups"] == 12
        and bootstrap["replicates"] == 1000
        and bootstrap["seed"] == 20261029
    )
    checks += 3
    for key in ["lower_exact", "upper_exact"]:
        assert display(bootstrap[key]) in tex
        checks += 1
    source = json.loads(
        (ROOT / "data/source/INDEPENDENT_PARSE.json").read_text(encoding="utf-8")
    )
    replay = json.loads((ROOT / "REPRODUCTION_CHECK.json").read_text(encoding="utf-8"))
    freeze = json.loads((ROOT / "FREEZE.json").read_text(encoding="utf-8"))
    assert len(freeze["dependencies"]) == replay["protected_dependencies"] == 24
    checks += 1
    for value in [
        source["source_rows"],
        source["selected_field_scalars_matched_by_canonical_parser_hash"],
        source["projection_and_geometry_exact_checks"],
        replay["exact_csv_and_document_fields"],
        replay["numeric_tolerance_fields"],
    ]:
        assert format(value, ",") in tex
        checks += 1
    for phrase in [
        "simulates cold start on previously observed station IDs",
        "does not isolate geography",
        "pooled baseline is not separately tuned",
        "matched-setting comparison on a new held cohort",
        "public files were posted later",
        "idealized prior-day",
        "not guaranteed confidence or future coverage",
        "no embedding or parameter optimizer",
        "not additional independent observations",
        "not validated physical thresholds",
        "not peer reviewed",
        "not source or physical accuracy",
        "(departures/day) squared",
        "Formal-publication projects, including Azure optimization, remain private",
    ]:
        assert phrase.lower() in tex.lower(), phrase
        checks += 1
    for document in [md, readme]:
        for phrase in [
            "44.8%",
            "11.621",
            "21.047",
            "does not isolate geography",
            "idealized",
            "private",
        ]:
            assert phrase in document, phrase
            checks += 1
    scope = json.loads(
        (ROOT / "paper/PUBLICATION_SCOPE.json").read_text(encoding="utf-8")
    )
    assert (
        scope["scope"] == "independent-program-study"
        and scope["formal_submission_target"] is False
        and len(scope["public_files"]) == 5
    )
    checks += 3
    for name, digest in scope["public_files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        checks += 1
    figure_hashes = json.loads(
        (ROOT / "figures/MANIFEST.json").read_text(encoding="utf-8")
    )
    for name in ["held_group_errors", "coordinate_groups", "geography_sensitivity"]:
        assert (
            scope["public_files"]["paper/images/" + name + ".pdf"]
            == figure_hashes[name + ".pdf"]
        )
        checks += 1
    doc = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(doc.pages) == 7
    checks += 1
    normal = re.sub(
        r"\s+",
        " ",
        unicodedata.normalize(
            "NFKC", " ".join(page.extract_text() for page in doc.pages)
        ),
    )
    for phrase in [
        "Decision brief",
        "11.621",
        "21.047",
        "44.8%",
        "1,643,477",
        "505,372",
        "HB408",
        "JC052",
        "does not isolate geography",
        "not peer reviewed",
    ]:
        assert phrase.lower() in normal.lower(), phrase
        checks += 1
    for command in [
        "python -m pip install -r requirements.txt",
        "python -m unittest discover -s tests -v",
        "python src/check_reproduction.py",
        "python src/verify_figures.py",
        "python src/verify_paper.py",
        "python src/verify_public_package.py",
    ]:
        assert command in normal, command
        checks += 1
    forbidden = [
        "/JavaScript",
        "/JS",
        "/Launch",
        "/EmbeddedFiles",
        "/RichMedia",
        "/AcroForm",
        "/AA",
    ]
    pdfs = [
        ROOT / "paper/manuscript.pdf",
        *sorted((ROOT / "paper/images").glob("*.pdf")),
    ]
    assert len(pdfs) == 4
    for path in pdfs:
        pdf = PdfReader(path)
        catalog = pdf.trailer["/Root"]
        assert not any(k in catalog for k in forbidden)
        assert "/EmbeddedFiles" not in catalog.get("/Names", {})
        action = catalog.get("/OpenAction")
        if hasattr(action, "get"):
            assert action.get("/S") not in ["/JavaScript", "/Launch"]
        for page in pdf.pages:
            assert not any(k in page for k in forbidden)
            for annotation in page.get("/Annots", []):
                a = annotation.get_object()
                assert not any(k in a for k in ["/AA", "/RichMedia"])
                if "/A" in a:
                    assert a["/A"].get("/S") == "/URI"
        checks += 1
    return dict(
        status="PASS",
        independent_paper_checks=checks,
        validation_configurations_displayed=54,
        held_groups_displayed=12,
        held_months_displayed=6,
        geographic_scenarios_displayed=17,
        pdf_pages=7,
        pdf_active_content_checks=4,
        scope="Independent table recomputation, primary row-loss and claim checks, exact approved hashes and bounded PDF actions. Rights and rendered readability reviewed separately.",
    )


if __name__ == "__main__":
    result = verify()
    (ROOT / "paper/VERIFICATION.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
