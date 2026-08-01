from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from backtesting.threshold_comparison import (
    compare_thresholds,
    write_comparison_csv,
)


CSV_TEXT = """\
country,opponent,match,kickoff_edt,end_edt,series_winner_start,series_winner_end,championship_loss_start,championship_loss_end
Favorite,Underdog,favorite-underdog,2026-04-01 07:00 PM EDT,2026-04-10 10:00 PM EDT,0.700000,0.000000,0.750000,1.000000
Underdog,Favorite,favorite-underdog,2026-04-01 07:00 PM EDT,2026-04-10 10:00 PM EDT,0.200000,1.000000,0.950000,0.700000
"""


class ThresholdComparisonTest(unittest.TestCase):
    def test_compares_every_whole_percent_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nba.csv"
            source.write_text(CSV_TEXT, encoding="utf-8")

            sweep = compare_thresholds(
                "nba",
                source,
                stake_per_hedge=10.0,
            )

        self.assertEqual(len(sweep.results), 101)
        self.assertEqual(
            [result.threshold_percent for result in sweep.results],
            list(range(101)),
        )
        self.assertEqual(sweep.initial_cash, 20.0)
        self.assertEqual(sweep.results[0].qualifying_hedges, 2)
        self.assertEqual(sweep.results[20].qualifying_hedges, 2)
        self.assertEqual(sweep.results[21].qualifying_hedges, 1)
        self.assertEqual(sweep.results[70].qualifying_hedges, 1)
        self.assertEqual(sweep.results[71].qualifying_hedges, 0)
        self.assertEqual(sweep.results[100].qualifying_hedges, 0)
        self.assertAlmostEqual(sweep.results[0].total_pnl, -0.5)
        self.assertAlmostEqual(sweep.results[0].pnl_per_hedge, -0.25)
        self.assertAlmostEqual(sweep.results[0].return_on_stake, -0.025)
        self.assertAlmostEqual(sweep.results[70].total_pnl, 0.0)
        self.assertIsNone(sweep.results[71].pnl_per_hedge)
        self.assertIsNone(sweep.results[71].return_on_stake)

    def test_writes_all_thresholds_to_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nba.csv"
            output = Path(directory) / "comparison.csv"
            source.write_text(CSV_TEXT, encoding="utf-8")
            sweep = compare_thresholds(
                "nba",
                source,
                stake_per_hedge=10.0,
            )

            write_comparison_csv(output, sweep)

            with output.open(encoding="utf-8", newline="") as saved:
                rows = list(csv.DictReader(saved))

        self.assertEqual(len(rows), 101)
        self.assertEqual(rows[0]["threshold_percent"], "0")
        self.assertEqual(rows[-1]["threshold_percent"], "100")
        self.assertEqual(rows[70]["qualifying_hedges"], "1")
        self.assertEqual(rows[71]["pnl_per_hedge"], "")


if __name__ == "__main__":
    unittest.main()
