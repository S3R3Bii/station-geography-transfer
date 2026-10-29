"""Isolated replay with exact contracts and the predeclared numerical tolerances."""

from contextlib import ExitStack
import csv
from fractions import Fraction as Q
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verify_freeze import verify as verify_freeze
from verify_source import verify as verify_source
from verify_results import verify as verify_results

ROOT = Path(__file__).resolve().parents[1]


def main():
    frozen = verify_freeze(ROOT)
    source = verify_source(ROOT)
    cfg = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
    exact = numeric = 0

    def number(a, b, tolerance):
        nonlocal numeric
        if a == "" or b == "":
            assert a == b
        else:
            assert abs(Q(a) - Q(b)) <= Q(str(tolerance)), (a, b, tolerance)
        numeric += 1

    def compare_csv(left, right):
        nonlocal exact, numeric
        with ExitStack() as stack:
            streams = [
                stack.enter_context(
                    gzip.open(path, "rt", newline="")
                    if path.name.endswith(".gz")
                    else path.open(encoding="utf-8", newline="")
                )
                for path in [left, right]
            ]
            readers = [csv.DictReader(stream) for stream in streams]
            assert readers[0].fieldnames == readers[1].fieldnames
            if "weights" in left.name:
                keys = ["scenario", "policy", "station", "donor"]
                mappings = [
                    {tuple(r[k] for k in keys): r for r in reader} for reader in readers
                ]
                assert set(mappings[0]) == set(mappings[1])
                pairs = ((mappings[0][k], mappings[1][k]) for k in sorted(mappings[0]))
            else:
                from itertools import zip_longest

                pairs = zip_longest(*readers)
            for a, b in pairs:
                assert a is not None and b is not None
                for key, value in a.items():
                    tolerance = None
                    if "weights" in left.name and key in ["distance_km", "weight"]:
                        tolerance = 1e-8
                    elif "predictions" in left.name and key in [
                        "prediction",
                        "donor_min",
                        "donor_max",
                    ]:
                        tolerance = float(
                            cfg["floating_tolerances"]["prediction_absolute"]
                        )
                    elif "metrics" in left.name and key not in [
                        "scenario",
                        "policy",
                        "scope",
                        "unit",
                        "period",
                        "n",
                        "groups",
                        "observed",
                    ]:
                        tolerance = float(cfg["floating_tolerances"]["metric_absolute"])
                        if key in [
                            "abs_error_total_exact",
                            "squared_error_total_exact",
                            "bias_total_exact",
                        ]:
                            tolerance *= int(a["n"])
                    elif (
                        left.name == "held-bootstrap.csv"
                        and key == "mae_difference_exact"
                    ):
                        tolerance = float(cfg["floating_tolerances"]["metric_absolute"])
                    if tolerance is None:
                        assert value == b[key], (left.name, key, value, b[key])
                        exact += 1
                    else:
                        number(value, b[key], tolerance)

    phases = []
    documents = 0
    with tempfile.TemporaryDirectory(prefix="station-transfer-replay-") as directory:
        target = Path(directory)
        for folder in ["src", "tests", "data"]:
            shutil.copytree(
                ROOT / folder,
                target / folder,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        (target / "results").mkdir()
        protected = json.loads((ROOT / "FREEZE.json").read_text(encoding="utf-8"))[
            "dependencies"
        ]
        for name in [*protected, "FREEZE.json"]:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        verify_freeze(target)
        for phase in ["validation", "held"]:
            subprocess.run(
                [sys.executable, "src/run_analysis.py", phase],
                cwd=target,
                check=True,
                capture_output=True,
            )
            result = verify_results(phase, target)
            phases.append(result)
            assert result == json.loads(
                (ROOT / "results" / (phase + "-VERIFICATION.json")).read_text(
                    encoding="utf-8"
                )
            )
            documents += 1
            for original in sorted((ROOT / "results").glob(phase + "-*.csv*")):
                compare_csv(original, target / "results" / original.name)
            if phase == "validation":
                original = json.loads(
                    (ROOT / "SELECTION.json").read_text(encoding="utf-8")
                )
                replayed = json.loads(
                    (target / "SELECTION.json").read_text(encoding="utf-8")
                )
                for key, value in original.items():
                    if key in ["objective_exact", "baseline_mae_exact"]:
                        number(
                            value,
                            replayed[key],
                            float(cfg["floating_tolerances"]["metric_absolute"]),
                        )
                    else:
                        assert value == replayed[key]
                        exact += 1
                # Recomputed validation has been checked. Restore immutable selection/reference
                # bytes so held evaluation uses the originally frozen policy, never a new choice.
                for name in [
                    "SELECTION.json",
                    "results/validation-metrics.csv",
                    "results/validation-VERIFICATION.json",
                ]:
                    shutil.copy2(ROOT / name, target / name)
                verify_freeze(target)
        original = json.loads(
            (ROOT / "results/BOOTSTRAP_SUMMARY.json").read_text(encoding="utf-8")
        )
        replayed = json.loads(
            (target / "results/BOOTSTRAP_SUMMARY.json").read_text(encoding="utf-8")
        )
        for key, value in original.items():
            if key in ["lower_exact", "upper_exact"]:
                number(
                    value,
                    replayed[key],
                    float(cfg["floating_tolerances"]["metric_absolute"]),
                )
            else:
                assert value == replayed[key]
                exact += 1
        assert source == verify_source(target)
        documents += 1
        verify_freeze(target)
    result = dict(
        status="PASS",
        exact_csv_and_document_fields=exact,
        numeric_tolerance_fields=numeric,
        verification_documents=documents,
        protected_dependencies=frozen["dependencies"],
        phases=phases,
        scope="Source/categories/integers/histories/configuration exact; float predictions/distances/weights and derived export-decimal losses compared at fixed protocol tolerances. Frozen validation reference bytes restored after verified recomputation before held use. Variable phase timings excluded.",
    )
    (ROOT / "REPRODUCTION_CHECK.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
