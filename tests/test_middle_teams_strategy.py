from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from backtesting.middle_teams_strategy import (
    middle_teams_cli,
    run_middle_teams_strategy,
)


CSV_TEXT = """\
country,opponent,match,kickoff_edt,end_edt,series_winner_start,series_winner_end,championship_loss_start,championship_loss_end
Lower Bound,Opponent,lower-bound,2026-04-01 07:00 PM EDT,2026-04-01 10:00 PM EDT,0.300000,1.000000,0.900000,0.800000
Upper Bound,Opponent,upper-bound,2026-04-02 07:00 PM EDT,2026-04-02 10:00 PM EDT,0.800000,1.000000,0.800000,0.700000
Trigger Outside,Opponent,trigger-outside,2026-04-03 07:00 PM EDT,2026-04-03 10:00 PM EDT,0.801000,1.000000,0.850000,0.700000
Championship Outside,Opponent,championship-outside,2026-04-04 07:00 PM EDT,2026-04-04 10:00 PM EDT,0.500000,1.000000,0.799000,0.700000
"""


class MiddleTeamsStrategyTest(unittest.TestCase):
    def test_selects_only_the_fixed_middle_teams_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nba.csv"
            path.write_text(CSV_TEXT, encoding="utf-8")

            result = run_middle_teams_strategy(
                "nba",
                path,
                stake_per_trade=10.0,
                initial_cash=100.0,
            )

        self.assertEqual(
            [quote.team for quote in result.selected],
            ["Lower Bound", "Upper Bound"],
        )
        self.assertEqual(result.stats.trade_count, 8)

    def test_cli_runs_without_probability_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nba.csv"
            path.write_text(CSV_TEXT, encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = middle_teams_cli(
                    [
                        "nba",
                        str(path),
                        "--stake",
                        "10",
                        "--initial-cash",
                        "100",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("middle teams paired hedge", output.getvalue())
        self.assertIn("Trigger win range: 30%-80%", output.getvalue())
        self.assertIn("Qualifying teams: 2", output.getvalue())


if __name__ == "__main__":
    unittest.main()
