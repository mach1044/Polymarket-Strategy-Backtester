from __future__ import annotations

import argparse
from pathlib import Path

from .polymarket_csv import run_csv_accounting_smoke_test


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data" / "match_data" / "polymarket_match_data.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a neutral accounting smoke test over Polymarket CSV data."
    )
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV,
    )
    parser.add_argument("--initial-cash", type=float, default=1_000.0)
    parser.add_argument("--quantity", type=float, default=1.0)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_csv_accounting_smoke_test(
        args.csv,
        initial_cash=args.initial_cash,
        quantity_per_outcome=args.quantity,
        fee_rate=args.fee_rate,
    )
    stats = result.stats
    print(f"Source rows: {result.source_rows}")
    print(f"Matches: {result.matches}")
    print(f"Trades: {stats.trade_count}")
    print(f"Ending equity: ${stats.ending_equity:.6f}")
    print(f"Total P&L: ${stats.total_pnl:.6f}")
    print(
        "Total return: "
        + (
            f"{stats.total_return:.6%}"
            if stats.total_return is not None
            else "undefined"
        )
    )
    print(f"Maximum drawdown: {stats.max_drawdown:.6%}")
    print(f"Open positions: {stats.open_positions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
