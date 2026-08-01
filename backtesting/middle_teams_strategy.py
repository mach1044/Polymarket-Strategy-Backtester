from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__:
    from .paired_hedge_strategy import (
        StrategyResult,
        print_strategy_result,
        run_sport_strategy,
    )
    from .sport_strategy_config import SPORTS, get_sport_config
else:
    from paired_hedge_strategy import (
        StrategyResult,
        print_strategy_result,
        run_sport_strategy,
    )
    from sport_strategy_config import SPORTS, get_sport_config


TRIGGER_WIN_MIN = 0.30
TRIGGER_WIN_MAX = 0.80
CHAMPIONSHIP_WIN_MIN = 0.10
CHAMPIONSHIP_WIN_MAX = 0.20


def run_middle_teams_strategy(
    sport: str,
    csv_path: Path | None = None,
    *,
    stake_per_trade: float = 100.0,
    initial_cash: float = 1_000.0,
    fee_rate: float = 0.0,
) -> StrategyResult:
    """Run the fixed middle-teams probability window for any sport."""
    return run_sport_strategy(
        sport,
        csv_path,
        threshold=TRIGGER_WIN_MIN,
        trigger_max=TRIGGER_WIN_MAX,
        championship_win_min=CHAMPIONSHIP_WIN_MIN,
        championship_win_max=CHAMPIONSHIP_WIN_MAX,
        stake_per_trade=stake_per_trade,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the middle-teams paired hedge: 30%-80% trigger win "
            "and 10%-20% implied championship win."
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
    parser.add_argument("--initial-cash", type=float, default=1_000.0)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    return parser


def middle_teams_cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = get_sport_config(args.sport)
        result = run_middle_teams_strategy(
            args.sport,
            args.csv,
            stake_per_trade=args.stake,
            initial_cash=args.initial_cash,
            fee_rate=args.fee_rate,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"{config.display_name} - middle teams paired hedge")
    print(
        f"Trigger win range: {TRIGGER_WIN_MIN:.0%}-{TRIGGER_WIN_MAX:.0%} | "
        "championship win range: "
        f"{CHAMPIONSHIP_WIN_MIN:.0%}-{CHAMPIONSHIP_WIN_MAX:.0%}"
    )
    print_strategy_result(
        result,
        config.trigger_label,
        config.loss_label,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return middle_teams_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
