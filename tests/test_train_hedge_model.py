from __future__ import annotations

import io
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from backtesting.experiments.fifa_model.train_hedge_model import (
    HedgeSample,
    evaluate_model,
    fit_ridge_model,
    load_sport_samples,
    model_cli,
    run_cross_sport_model,
)


FIFA_CSV = """\
country,opponent,match,kickoff_edt,end_edt,game_winner_start,game_winner_end,tournament_loss_start,tournament_loss_end
Alpha,Beta,alpha-beta,2026-06-01 07:00 PM EDT,2026-06-01 10:00 PM EDT,0.400000,1.000000,0.900000,0.800000
Beta,Alpha,alpha-beta,2026-06-01 07:00 PM EDT,2026-06-01 10:00 PM EDT,0.600000,0.000000,0.800000,1.000000
"""


class TrainHedgeModelTest(unittest.TestCase):
    def test_builds_entry_features_and_all_target_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fifa.csv"
            path.write_text(FIFA_CSV, encoding="utf-8")

            samples_by_target = {
                target: load_sport_samples("fifa", path, target=target)
                for target in (
                    "engine_pnl_per_100",
                    "profit_per_100",
                    "strategy_ev",
                    "strategy_ev_relative",
                )
            }

        samples = samples_by_target["strategy_ev_relative"]
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0].team, "Alpha")
        self.assertEqual(len(samples[0].features), 5)
        self.assertAlmostEqual(samples[0].features[0], 0.4)
        self.assertAlmostEqual(samples[0].features[1], 0.1)
        self.assertAlmostEqual(samples[0].features[2], 0.25)
        self.assertAlmostEqual(samples[0].features[3], math.log(4.0))
        self.assertAlmostEqual(samples[0].features[4], 0.16)
        expected = {
            "engine_pnl_per_100": (5.0, 0.0),
            "profit_per_100": (5.5555555556, 0.0),
            "strategy_ev": (0.05, 0.0),
            "strategy_ev_relative": (1.0 / 3.0, 0.0),
        }
        for target, target_samples in samples_by_target.items():
            with self.subTest(target=target):
                self.assertAlmostEqual(
                    target_samples[0].target_value,
                    expected[target][0],
                )
                self.assertAlmostEqual(
                    target_samples[1].target_value,
                    expected[target][1],
                )

    def test_uses_explicit_target_column_when_present(self) -> None:
        source = FIFA_CSV.replace(
            "tournament_loss_end\n",
            "tournament_loss_end,strategy_ev_relative\n",
        ).replace(
            "0.900000,0.800000\n",
            "0.900000,0.800000,12.500000\n",
        ).replace(
            "0.800000,1.000000\n",
            "0.800000,1.000000,-3.000000\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fifa_with_profit.csv"
            path.write_text(source, encoding="utf-8")

            samples = load_sport_samples("fifa", path)

        self.assertEqual(
            [sample.target_value for sample in samples],
            [12.5, -3.0],
        )

    def test_fits_and_evaluates_a_deterministic_linear_target(self) -> None:
        feature_rows = (
            (0.0,),
            (1.0,),
            (2.0,),
        )
        samples = tuple(
            HedgeSample(
                sport="synthetic",
                team=f"Team {index}",
                match=f"match-{index}",
                kickoff=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
                features=features,
                target_value=(
                    2.0 + 3.0 * features[0]
                ),
            )
            for index, features in enumerate(feature_rows)
        )

        model = fit_ridge_model(samples, alpha=0.0)
        evaluation = evaluate_model(
            model,
            samples,
            sport="synthetic",
            prediction_threshold=-1.0,
        )

        self.assertAlmostEqual(evaluation.mae, 0.0)
        self.assertAlmostEqual(evaluation.rmse, 0.0)
        self.assertAlmostEqual(evaluation.r_squared, 1.0)
        self.assertEqual(evaluation.selected, len(samples))

    def test_ridge_penalty_shrinks_a_known_coefficient(self) -> None:
        samples = tuple(
            HedgeSample(
                sport="synthetic",
                team=f"Team {index}",
                match=f"match-{index}",
                kickoff=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
                features=(feature,),
                target_value=2.0 + 3.0 * feature,
            )
            for index, feature in enumerate((-1.0, 0.0, 1.0))
        )

        model = fit_ridge_model(samples, alpha=1.0)

        self.assertAlmostEqual(model.intercept, 2.0)
        self.assertAlmostEqual(model.coefficients[0], 1.8371173071)
        self.assertAlmostEqual(
            model.predict_features((1.0,)),
            4.25,
        )

    def test_rejects_empty_or_duplicate_evaluation_sports(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one"):
            run_cross_sport_model(())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            run_cross_sport_model(("nba", "nba"))

    def test_cli_trains_on_fifa_and_evaluates_one_other_sport(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = model_cli(["nba"])

        self.assertEqual(exit_code, 0)
        self.assertIn("FIFA-trained ridge hedge model", output.getvalue())
        self.assertIn("FIFA in-sample fit", output.getvalue())
        self.assertIn("nba", output.getvalue())


if __name__ == "__main__":
    unittest.main()
