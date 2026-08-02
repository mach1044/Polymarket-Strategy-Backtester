from __future__ import annotations

import unittest

from backtesting.experiments.fifa_model.compare_hedge_models import compare_models
from backtesting.experiments.fifa_model.train_hedge_model import FEATURE_SETS, TARGETS


class CompareHedgeModelsTest(unittest.TestCase):
    def test_fits_every_feature_and_target_combination(self) -> None:
        rows = compare_models()

        self.assertEqual(len(rows), len(FEATURE_SETS) * len(TARGETS))
        self.assertEqual(
            {(row.feature_set, row.target) for row in rows},
            {
                (feature_set, target)
                for feature_set in FEATURE_SETS
                for target in TARGETS
            },
        )
        self.assertTrue(all(row.external_rows > 0 for row in rows))
        self.assertTrue(all(row.training_sports == ("fifa",) for row in rows))
        self.assertTrue(all(row.training_rows == 64 for row in rows))
        self.assertTrue(all(row.external_rows == 234 for row in rows))


if __name__ == "__main__":
    unittest.main()
