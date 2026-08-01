from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .paired_hedge_strategy import (
        load_hedge_quotes,
        run_sport_strategy,
    )
    from .sport_strategy_config import SPORTS, get_sport_config
else:
    from paired_hedge_strategy import load_hedge_quotes, run_sport_strategy
    from sport_strategy_config import SPORTS, get_sport_config


@dataclass(frozen=True)
class ThresholdResult:
    threshold_percent: int
    qualifying_hedges: int
    trade_count: int
    total_pnl: float
    pnl_per_hedge: float | None
    return_on_stake: float | None
    max_drawdown: float


@dataclass(frozen=True)
class ThresholdSweep:
    sport: str
    csv_path: Path
    stake_per_hedge: float
    initial_cash: float
    fee_rate: float
    results: tuple[ThresholdResult, ...]


def compare_thresholds(
    sport: str,
    csv_path: Path | None = None,
    *,
    stake_per_hedge: float = 100.0,
    initial_cash: float | None = None,
    fee_rate: float = 0.0,
) -> ThresholdSweep:
    """Run the paired hedge at every whole-percent trigger threshold."""
    if stake_per_hedge <= 0.0:
        raise ValueError("stake_per_hedge must be positive")
    if not 0.0 <= fee_rate < 1.0:
        raise ValueError("fee_rate must be in [0, 1)")

    config = get_sport_config(sport)
    path = csv_path or config.csv_path
    quotes = load_hedge_quotes(
        path,
        config.trigger_prefix,
        config.loss_prefix,
        config.namespace,
    )
    comparison_cash = (
        initial_cash
        if initial_cash is not None
        else max(stake_per_hedge, len(quotes) * stake_per_hedge)
    )
    if comparison_cash <= 0.0:
        raise ValueError("initial_cash must be positive")

    results = []
    for threshold_percent in range(101):
        strategy_result = run_sport_strategy(
            sport,
            path,
            threshold=threshold_percent / 100.0,
            stake_per_trade=stake_per_hedge,
            initial_cash=comparison_cash,
            fee_rate=fee_rate,
        )
        hedge_count = len(strategy_result.hedges)
        deployed_stake = hedge_count * stake_per_hedge
        total_pnl = strategy_result.stats.total_pnl
        results.append(
            ThresholdResult(
                threshold_percent=threshold_percent,
                qualifying_hedges=hedge_count,
                trade_count=strategy_result.stats.trade_count,
                total_pnl=total_pnl,
                pnl_per_hedge=(
                    total_pnl / hedge_count if hedge_count else None
                ),
                return_on_stake=(
                    total_pnl / deployed_stake
                    if deployed_stake
                    else None
                ),
                max_drawdown=strategy_result.stats.max_drawdown,
            )
        )

    return ThresholdSweep(
        sport=sport.casefold(),
        csv_path=path,
        stake_per_hedge=stake_per_hedge,
        initial_cash=comparison_cash,
        fee_rate=fee_rate,
        results=tuple(results),
    )


def write_comparison_csv(path: Path, sweep: ThresholdSweep) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "threshold_percent",
                "qualifying_hedges",
                "trade_count",
                "total_pnl",
                "pnl_per_hedge",
                "return_on_stake",
                "max_drawdown",
            )
        )
        for result in sweep.results:
            writer.writerow(
                (
                    result.threshold_percent,
                    result.qualifying_hedges,
                    result.trade_count,
                    f"{result.total_pnl:.6f}",
                    (
                        f"{result.pnl_per_hedge:.6f}"
                        if result.pnl_per_hedge is not None
                        else ""
                    ),
                    (
                        f"{result.return_on_stake:.6f}"
                        if result.return_on_stake is not None
                        else ""
                    ),
                    f"{result.max_drawdown:.6f}",
                )
            )


def print_comparison(sweep: ThresholdSweep) -> None:
    config = get_sport_config(sweep.sport)
    print(f"{config.display_name} - paired hedge threshold comparison")
    print(
        f"Stake per hedge: ${sweep.stake_per_hedge:.2f} | "
        f"comparison cash: ${sweep.initial_cash:.2f} | "
        f"fee rate: {sweep.fee_rate:.2%}"
    )
    print(
        "Threshold  Hedges  Trades    Total P&L  "
        "P&L/Hedge  Stake Return  Max Drawdown"
    )
    for result in sweep.results:
        pnl_per_hedge = (
            f"${result.pnl_per_hedge:>9.2f}"
            if result.pnl_per_hedge is not None
            else "        -"
        )
        stake_return = (
            f"{result.return_on_stake:>11.2%}"
            if result.return_on_stake is not None
            else "          -"
        )
        print(
            f"{result.threshold_percent:>8}%  "
            f"{result.qualifying_hedges:>6}  "
            f"{result.trade_count:>6}  "
            f"${result.total_pnl:>10.2f}  "
            f"{pnl_per_hedge}  "
            f"{stake_return}  "
            f"{result.max_drawdown:>11.2%}"
        )

    active_results = [
        result for result in sweep.results if result.qualifying_hedges
    ]
    if active_results:
        best = max(active_results, key=lambda result: result.total_pnl)
        print(
            f"Highest in-sample total P&L (descriptive only): "
            f"{best.threshold_percent}% (${best.total_pnl:.2f})"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the paired hedge at every whole-percent threshold "
            "from 0% through 100%."
        )
    )
    parser.add_argument(
        "sport",
        choices=sorted(SPORTS),
        help="sporting event configuration to use",
    )
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        help="optional override for the sport's default CSV",
    )
    parser.add_argument("--stake", type=float, default=100.0)
    parser.add_argument(
        "--initial-cash",
        type=float,
        help=(
            "comparison bankroll; by default enough cash is allocated to "
            "open every hedge"
        ),
    )
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument(
        "--out",
        type=Path,
        help="optional path for the complete 101-row comparison CSV",
    )
    return parser


def comparison_cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        sweep = compare_thresholds(
            args.sport,
            args.csv,
            stake_per_hedge=args.stake,
            initial_cash=args.initial_cash,
            fee_rate=args.fee_rate,
        )
        if args.out is not None:
            write_comparison_csv(args.out, sweep)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_comparison(sweep)
    if args.out is not None:
        print(f"Saved comparison to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return comparison_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
