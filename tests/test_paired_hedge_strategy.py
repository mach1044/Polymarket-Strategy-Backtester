from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from backtesting.paired_hedge_strategy import (
    run_paired_hedge_strategy,
    run_sport_strategy,
    sport_strategy_cli,
)
from backtesting.sport_strategy_config import get_sport_config


CSV_TEXT = """\
country,opponent,match,kickoff_edt,end_edt,series_winner_start,series_winner_end,championship_loss_start,championship_loss_end
Favorite,Underdog,favorite-underdog,2026-04-01 07:00 PM EDT,2026-04-10 10:00 PM EDT,0.700000,0.000000,0.750000,1.000000
Underdog,Favorite,favorite-underdog,2026-04-01 07:00 PM EDT,2026-04-10 10:00 PM EDT,0.200000,1.000000,0.950000,0.700000
"""

RANGE_CSV_TEXT = """\
country,opponent,match,kickoff_edt,end_edt,series_winner_start,series_winner_end,championship_loss_start,championship_loss_end
Lower Bound,Opponent,lower-bound,2026-04-01 07:00 PM EDT,2026-04-01 10:00 PM EDT,0.300000,1.000000,0.900000,0.800000
Upper Bound,Opponent,upper-bound,2026-04-02 07:00 PM EDT,2026-04-02 10:00 PM EDT,0.500000,1.000000,0.850000,0.700000
Trigger Below,Opponent,trigger-below,2026-04-03 07:00 PM EDT,2026-04-03 10:00 PM EDT,0.299000,1.000000,0.900000,0.800000
Trigger Above,Opponent,trigger-above,2026-04-04 07:00 PM EDT,2026-04-04 10:00 PM EDT,0.501000,1.000000,0.900000,0.800000
Championship Below,Opponent,championship-below,2026-04-05 07:00 PM EDT,2026-04-05 10:00 PM EDT,0.400000,1.000000,0.901000,0.800000
Championship Above,Opponent,championship-above,2026-04-06 07:00 PM EDT,2026-04-06 10:00 PM EDT,0.400000,1.000000,0.849000,0.700000
"""


class PairedHedgeStrategyTest(unittest.TestCase):
    def test_buys_only_teams_at_or_above_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nba.csv"
            path.write_text(CSV_TEXT, encoding="utf-8")

            result = run_paired_hedge_strategy(
                path,
                trigger_prefix="series_winner",
                loss_prefix="championship_loss",
                namespace="test",
                stake_per_trade=10.0,
                initial_cash=100.0,
            )

        self.assertEqual([quote.team for quote in result.selected], ["Favorite"])
        hedge = result.hedges[0]
        self.assertAlmostEqual(hedge.trigger_quantity, 3.571428571)
        self.assertAlmostEqual(hedge.loss_quantity, 10.0)
        self.assertEqual(result.stats.buy_count, 2)
        self.assertEqual(result.stats.sell_count, 2)
        self.assertEqual(result.stats.open_positions, 0)
        self.assertAlmostEqual(result.stats.total_pnl, 0.0)
        self.assertAlmostEqual(result.stats.ending_equity, 100.0)

    def test_rejects_threshold_outside_probability_range(self) -> None:
        with self.assertRaises(ValueError):
            run_paired_hedge_strategy(
                Path("unused.csv"),
                trigger_prefix="series_winner",
                loss_prefix="championship_loss",
                namespace="test",
                threshold=1.01,
            )

    def test_selects_inclusive_trigger_and_championship_win_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nba.csv"
            path.write_text(RANGE_CSV_TEXT, encoding="utf-8")

            result = run_paired_hedge_strategy(
                path,
                trigger_prefix="series_winner",
                loss_prefix="championship_loss",
                namespace="test",
                threshold=0.30,
                trigger_max=0.50,
                championship_win_min=0.10,
                championship_win_max=0.15,
                stake_per_trade=10.0,
                initial_cash=100.0,
            )

        self.assertEqual(
            [quote.team for quote in result.selected],
            ["Lower Bound", "Upper Bound"],
        )
        self.assertEqual(result.stats.trade_count, 8)

    def test_rejects_reversed_probability_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "trigger probability range"):
            run_paired_hedge_strategy(
                Path("unused.csv"),
                trigger_prefix="series_winner",
                loss_prefix="championship_loss",
                namespace="test",
                threshold=0.50,
                trigger_max=0.30,
            )

        with self.assertRaisesRegex(
            ValueError,
            "championship win probability range",
        ):
            run_paired_hedge_strategy(
                Path("unused.csv"),
                trigger_prefix="series_winner",
                loss_prefix="championship_loss",
                namespace="test",
                championship_win_min=0.15,
                championship_win_max=0.10,
            )

    def test_sport_wrapper_forwards_probability_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nba.csv"
            path.write_text(RANGE_CSV_TEXT, encoding="utf-8")

            result = run_sport_strategy(
                "nba",
                path,
                threshold=0.30,
                trigger_max=0.50,
                championship_win_min=0.10,
                championship_win_max=0.15,
                stake_per_trade=10.0,
                initial_cash=100.0,
            )

        self.assertEqual(
            [quote.team for quote in result.selected],
            ["Lower Bound", "Upper Bound"],
        )

    def test_cli_accepts_probability_window_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nba.csv"
            path.write_text(RANGE_CSV_TEXT, encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = sport_strategy_cli(
                    [
                        "nba",
                        str(path),
                        "--trigger-min",
                        "0.30",
                        "--trigger-max",
                        "0.50",
                        "--championship-win-min",
                        "0.10",
                        "--championship-win-max",
                        "0.15",
                        "--stake",
                        "10",
                        "--initial-cash",
                        "100",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Trigger win range: 30.0%-50.0%", output.getvalue())
        self.assertIn("Qualifying teams: 2", output.getvalue())

    def test_current_nhl_data_runs_through_generic_strategy(self) -> None:
        result = run_sport_strategy("nhl")

        self.assertEqual(len(result.selected), 5)
        self.assertEqual(result.stats.trade_count, 20)
        self.assertEqual(result.stats.open_positions, 0)
        self.assertAlmostEqual(result.stats.total_pnl, -3.096740649075855)

    def test_2025_nba_data_runs_from_central_configuration(self) -> None:
        config = get_sport_config("nba_2025")
        result = run_sport_strategy("nba_2025")

        self.assertEqual(config.display_name, "NBA 2025")
        self.assertEqual(config.csv_path.name, "nba_2025_match_data.csv")
        self.assertGreater(len(result.selected), 0)
        self.assertTrue(
            all(
                hedge.quote.trigger_instrument.startswith("nba_2025::")
                for hedge in result.hedges
            )
        )

    def test_2025_nhl_data_runs_from_central_configuration(self) -> None:
        config = get_sport_config("nhl_2025")
        result = run_sport_strategy("nhl_2025")

        self.assertEqual(config.display_name, "NHL 2025")
        self.assertEqual(config.csv_path.name, "nhl_2025_match_data.csv")
        self.assertGreater(len(result.selected), 0)
        self.assertTrue(
            all(
                hedge.quote.trigger_instrument.startswith("nhl_2025::")
                for hedge in result.hedges
            )
        )

    def test_nfl_config_selects_game_winner_columns(self) -> None:
        result = run_sport_strategy("nfl")

        self.assertEqual(len(result.selected), 2)
        self.assertEqual(result.stats.trade_count, 8)
        self.assertTrue(
            all(
                "::game_winner::" in hedge.quote.trigger_instrument
                for hedge in result.hedges
            )
        )

    def test_fifa_config_uses_world_cup_columns(self) -> None:
        config = get_sport_config("fifa")
        result = run_sport_strategy("fifa")

        self.assertEqual(config.display_name, "FIFA World Cup 2026")
        self.assertEqual(config.csv_path.name, "polymarket_match_data.csv")
        self.assertEqual(config.trigger_prefix, "game_winner")
        self.assertEqual(config.loss_prefix, "tournament_loss")
        self.assertGreater(len(result.selected), 0)
        self.assertEqual(result.stats.open_positions, 0)

    def test_lol_worlds_uses_shared_series_strategy_columns(self) -> None:
        config = get_sport_config("lol_worlds_2025")
        result = run_sport_strategy("lol_worlds_2025")

        self.assertEqual(config.display_name, "LoL Worlds 2025")
        self.assertEqual(
            config.csv_path.name, "lol_worlds_2025_match_data.csv"
        )
        self.assertEqual(config.trigger_prefix, "series_winner")
        self.assertEqual(config.loss_prefix, "championship_loss")
        self.assertGreater(len(result.selected), 0)
        self.assertEqual(result.stats.open_positions, 0)

    def test_mens_wimbledon_data_runs_from_central_configuration(self) -> None:
        config = get_sport_config("wimbledon_2026")
        result = run_sport_strategy("wimbledon_2026")

        self.assertEqual(config.display_name, "Men's Wimbledon 2026")
        self.assertEqual(
            config.csv_path.name,
            "wimbledon_2026_men_match_data.csv",
        )
        self.assertGreater(len(result.selected), 0)
        self.assertTrue(
            all(
                hedge.quote.trigger_instrument.startswith(
                    "wimbledon_2026_men::"
                )
                for hedge in result.hedges
            )
        )

    def test_mens_ucl_backfill_uses_shared_series_strategy_columns(self) -> None:
        config = get_sport_config("ucl_2026")
        result = run_sport_strategy("ucl_2026")

        self.assertEqual(
            config.display_name,
            "Men's UEFA Champions League 2025-26",
        )
        self.assertEqual(config.csv_path.name, "ucl_2026_match_data.csv")
        self.assertEqual(config.trigger_prefix, "series_winner")
        self.assertEqual(config.loss_prefix, "championship_loss")
        self.assertEqual(config.namespace, "ucl_2026")
        self.assertGreater(len(result.selected), 0)
        self.assertEqual(result.stats.open_positions, 0)


if __name__ == "__main__":
    unittest.main()
