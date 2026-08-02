from __future__ import annotations

import unittest

from backtesting.experiments.multi_sport_model.train_multi_sport_model import (
    EVALUATION_SPORTS,
    FEATURE_SETS,
    TARGETS,
    TRAINING_SPORTS,
    benchmark_row,
    run_experiment,
    verify_benchmark,
)


class MultiSportModelTest(unittest.TestCase):
    def test_reproduces_fixed_pooled_experiment(self) -> None:
        rows = run_experiment()

        self.assertEqual(len(rows), len(FEATURE_SETS) * len(TARGETS))
        self.assertTrue(all(row.training_sports == TRAINING_SPORTS for row in rows))
        self.assertTrue(
            all(row.evaluation_sports == EVALUATION_SPORTS for row in rows)
        )
        reference = benchmark_row(rows)
        verify_benchmark(reference)
        self.assertEqual(reference.external_selected, 89)
        self.assertAlmostEqual(reference.selected_engine_pnl, 57.28378222)


if __name__ == "__main__":
    unittest.main()
