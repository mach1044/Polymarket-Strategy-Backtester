from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtesting import (
    BacktestEngine,
    ChronologyError,
    InsufficientCashError,
    InsufficientInventoryError,
    Order,
    Position,
    Side,
)
from backtesting.polymarket_csv import run_csv_accounting_smoke_test


class BacktestEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_executes_round_trip_and_calculates_stats(self) -> None:
        engine = BacktestEngine(initial_cash=100.0)
        engine.update_prices(self.start, {"example": 0.4})
        engine.execute(Order("example", Side.BUY, 10.0))
        engine.update_prices(
            self.start + timedelta(hours=1), {"example": 0.6}
        )

        marked = engine.portfolio_snapshot()
        self.assertAlmostEqual(marked.cash, 96.0)
        self.assertAlmostEqual(marked.market_value, 6.0)
        self.assertAlmostEqual(marked.unrealized_pnl, 2.0)

        engine.execute(Order("example", Side.SELL, 10.0))
        stats = engine.stats()

        self.assertAlmostEqual(stats.ending_cash, 102.0)
        self.assertAlmostEqual(stats.ending_equity, 102.0)
        self.assertAlmostEqual(stats.total_pnl, 2.0)
        self.assertAlmostEqual(stats.total_return or 0.0, 0.02)
        self.assertAlmostEqual(stats.realized_pnl, 2.0)
        self.assertEqual(stats.trade_count, 2)
        self.assertEqual(stats.winning_sells, 1)
        self.assertEqual(stats.open_positions, 0)

    def test_applies_fees_to_cash_and_cost_basis(self) -> None:
        engine = BacktestEngine(initial_cash=100.0, fee_rate=0.01)
        engine.update_prices(self.start, {"example": 0.5})
        engine.execute(Order("example", Side.BUY, 10.0))
        engine.execute(Order("example", Side.SELL, 10.0))
        stats = engine.stats()

        self.assertAlmostEqual(stats.ending_cash, 99.9)
        self.assertAlmostEqual(stats.total_pnl, -0.1)
        self.assertAlmostEqual(stats.realized_pnl, -0.1)
        self.assertAlmostEqual(stats.fees_paid, 0.1)
        self.assertEqual(stats.losing_sells, 1)

    def test_rejects_orders_without_cash_or_inventory(self) -> None:
        engine = BacktestEngine(initial_cash=1.0)
        engine.update_prices(self.start, {"example": 0.6})

        with self.assertRaises(InsufficientCashError):
            engine.execute(Order("example", Side.BUY, 2.0))
        with self.assertRaises(InsufficientInventoryError):
            engine.execute(Order("example", Side.SELL, 1.0))

    def test_rejects_time_travel(self) -> None:
        engine = BacktestEngine(initial_cash=1.0)
        engine.update_prices(self.start, {"example": 0.5})

        with self.assertRaises(ChronologyError):
            engine.update_prices(
                self.start - timedelta(seconds=1), {"example": 0.4}
            )

    def test_marks_and_liquidates_starting_inventory(self) -> None:
        engine = BacktestEngine(
            initial_cash=10.0,
            initial_positions={"example": Position(5.0, 0.2)},
        )
        engine.update_prices(self.start, {"example": 0.3})

        marked = engine.stats()
        self.assertAlmostEqual(marked.starting_equity, 11.0)
        self.assertAlmostEqual(marked.ending_equity, 11.5)
        self.assertAlmostEqual(marked.unrealized_pnl, 0.5)

        engine.liquidate()
        liquidated = engine.stats()
        self.assertAlmostEqual(liquidated.ending_cash, 11.5)
        self.assertAlmostEqual(liquidated.realized_pnl, 0.5)
        self.assertEqual(liquidated.open_positions, 0)

    def test_current_polymarket_csv_balances_complementary_outcomes(self) -> None:
        csv_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "match_data"
            / "polymarket_match_data.csv"
        )

        result = run_csv_accounting_smoke_test(csv_path)

        self.assertEqual(result.source_rows, 64)
        self.assertEqual(result.matches, 32)
        self.assertEqual(result.stats.trade_count, 128)
        self.assertEqual(result.stats.buy_count, 64)
        self.assertEqual(result.stats.sell_count, 64)
        self.assertEqual(result.stats.open_positions, 0)
        self.assertAlmostEqual(result.stats.ending_equity, 1_000.0)
        self.assertAlmostEqual(result.stats.total_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
