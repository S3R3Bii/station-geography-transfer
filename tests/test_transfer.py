from datetime import date, timedelta
from fractions import Fraction as Q
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from geo import distance, shift
from model import (
    calendar_dates,
    candidates,
    history,
    neighbor_weights,
    prediction,
    rank_key,
)
from metrics import summarize


class TransferFixtures(unittest.TestCase):
    def test_zero_distance(self):
        self.assertEqual(distance(40.7, -74, 40.7, -74), 0)

    def test_quarter_circumference(self):
        self.assertAlmostEqual(distance(0, 0, 0, 90), math.pi * 6371 / 2, places=8)

    def test_distance_symmetry(self):
        self.assertAlmostEqual(
            distance(40.7, -74, 40.8, -74.1),
            distance(40.8, -74.1, 40.7, -74),
            places=10,
        )

    def test_north_shift(self):
        lat, lon = shift(0, 0, 0.5, 0)
        self.assertAlmostEqual(lat, 0.5 / 6371 * 180 / math.pi, places=12)
        self.assertAlmostEqual(lon, 0, places=12)

    def test_weekday_history(self):
        target = date(2024, 4, 1)
        days = calendar_dates(target, 28, "weekday")
        self.assertEqual(len(days), 4)
        self.assertEqual(days[-1], target - timedelta(days=7))
        self.assertTrue(all(x < target and x.weekday() == 0 for x in days))

    def test_weekend_history(self):
        self.assertEqual(len(calendar_dates(date(2024, 4, 6), 28, "daytype")), 8)

    def test_unknown_calendar(self):
        with self.assertRaises(ValueError):
            calendar_dates(date(2024, 4, 1), 28, "unknown")

    def test_insufficient_history(self):
        with self.assertRaises(ValueError):
            history({}, ["a"], date(2024, 4, 1), 7, "weekday")

    def test_target_value_not_used(self):
        target = date(2024, 4, 1)
        days = calendar_dates(target, 28, "weekday")
        data = {("a", d): 2 for d in days}
        data["a", target] = 999999
        self.assertEqual(history(data, ["a"], target, 28, "weekday")["a"]["mean"], 2)

    def test_uniform_prediction(self):
        features = {"a": {"mean": Q(9)}, "b": {"mean": Q(3)}}
        self.assertEqual(
            prediction(features, [("a", 1, 0.5), ("b", 2, 0.5)], 0), (6, 3, 9)
        )

    def test_distance_weighted_prediction(self):
        features = {"a": {"mean": Q(9)}, "b": {"mean": Q(3)}}
        self.assertEqual(
            prediction(features, [("a", 1, 0.75), ("b", 2, 0.25)], 2), (7.5, 3, 9)
        )

    def test_target_cannot_donate(self):
        with self.assertRaises(ValueError):
            neighbor_weights({}, ["a"], "a", dict(k=1, power=0))

    def test_k_cannot_shrink_silently(self):
        with self.assertRaises(ValueError):
            neighbor_weights({}, ["a"], "b", dict(k=3, power=0))

    def test_neighbor_tie_identifier(self):
        stations = {
            s: dict(latitude="0", longitude=lon)
            for s, lon in [("target", "0"), ("a", "1"), ("b", "-1")]
        }
        self.assertEqual(
            neighbor_weights(stations, ["b", "a"], "target", dict(k=1, power=0))[0][0],
            "a",
        )

    def test_distance_floor_and_sum(self):
        stations = {s: dict(latitude="0", longitude="0") for s in ["target", "a", "b"]}
        rows = neighbor_weights(stations, ["a", "b"], "target", dict(k=2, power=2))
        self.assertEqual([r[2] for r in rows], [0.5, 0.5])

    def test_search_size_and_ties(self):
        policies = candidates()
        self.assertEqual(len({r["policy"] for r in policies}), 54)
        self.assertEqual(min(policies, key=rank_key)["policy"], "geo-w28-weekday-k3-p0")

    def test_group_weighting(self):
        rows = [
            dict(actual=10, prediction=p, group=g)
            for p, g in [(12, "a"), (10, "a"), (13, "b")]
        ]
        result = summarize(rows)
        self.assertEqual(Q(result["mae_exact"]), Q(5, 3))
        self.assertEqual(Q(result["mae_equal_group_exact"]), 2)
        self.assertEqual(Q(result["wape_exact"]), Q(1, 6))

    def test_decimal_loss(self):
        self.assertEqual(
            Q(summarize([dict(actual=0, prediction=0.1, group="a")])["mae_exact"]),
            Q(1, 10),
        )

    def test_zero_wape_denominator(self):
        self.assertEqual(
            summarize([dict(actual=0, prediction=1, group="a")])["wape_exact"], ""
        )


if __name__ == "__main__":
    unittest.main()
