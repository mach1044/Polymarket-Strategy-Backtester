from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__:
    from .engine import BacktestEngine, BacktestStats, Order, Side, Trade
    from .sport_strategy_config import SPORTS, get_sport_config
else:
    from engine import BacktestEngine, BacktestStats, Order, Side, Trade
    from sport_strategy_config import SPORTS, get_sport_config


BASE_COLUMNS = {"country", "match", "kickoff_edt", "end_edt"}
MARKET_TIMEZONES = {
    "EDT": timezone(timedelta(hours=-4), name="EDT"),
    "EST": timezone(timedelta(hours=-5), name="EST"),
}
PROBABILITY_EPSILON = 1e-12


@dataclass(frozen=True)
class HedgeQuote:
    trigger_instrument: str
    loss_instrument: str
    team: str
    match: str
    start_time: datetime
    end_time: datetime
    trigger_start_price: float
    trigger_end_price: float
    loss_start_price: float
    loss_end_price: float


@dataclass(frozen=True)
class HedgePosition:
    quote: HedgeQuote
    trigger_quantity: float
    loss_quantity: float


@dataclass(frozen=True)
class StrategyResult:
    selected: tuple[HedgeQuote, ...]
    hedges: tuple[HedgePosition, ...]
    trades: tuple[Trade, ...]
    stats: BacktestStats


@dataclass(frozen=True)
class _Action:
    kind: str
    hedge: HedgePosition


def _parse_timestamp(value: str) -> datetime:
    try:
        timestamp_text, abbreviation = value.rsplit(" ", 1)
        parsed = datetime.strptime(timestamp_text, "%Y-%m-%d %I:%M %p")
        market_timezone = MARKET_TIMEZONES[abbreviation]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid market timestamp: {value!r}") from exc
    return parsed.replace(tzinfo=market_timezone)


def _parse_price(row_number: int, column: str, value: str) -> float:
    try:
        price = float(value)
    except ValueError as exc:
        raise ValueError(
            f"CSV row {row_number} has invalid {column}: {value!r}"
        ) from exc
    if not 0.0 <= price <= 1.0:
        raise ValueError(
            f"CSV row {row_number} has {column} outside [0, 1]: {price}"
        )
    return price


def load_hedge_quotes(
    path: Path,
    trigger_prefix: str,
    loss_prefix: str,
    namespace: str,
) -> list[HedgeQuote]:
    trigger_start = f"{trigger_prefix}_start"
    trigger_end = f"{trigger_prefix}_end"
    loss_start = f"{loss_prefix}_start"
    loss_end = f"{loss_prefix}_end"
    required = BASE_COLUMNS | {
        trigger_start,
        trigger_end,
        loss_start,
        loss_end,
    }

    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

        quotes = []
        instruments = set()
        for row_number, row in enumerate(reader, start=2):
            identity = f"{row['match']}::{row['country']}"
            trigger_instrument = (
                f"{namespace}::{trigger_prefix}::{identity}"
            )
            loss_instrument = f"{namespace}::{loss_prefix}::{identity}"
            if trigger_instrument in instruments:
                raise ValueError(
                    f'Duplicate instrument "{trigger_instrument}"'
                )
            instruments.add(trigger_instrument)
            start_time = _parse_timestamp(row["kickoff_edt"])
            end_time = _parse_timestamp(row["end_edt"])
            if end_time < start_time:
                raise ValueError(f"CSV row {row_number} ends before it starts")
            quotes.append(
                HedgeQuote(
                    trigger_instrument=trigger_instrument,
                    loss_instrument=loss_instrument,
                    team=row["country"],
                    match=row["match"],
                    start_time=start_time,
                    end_time=end_time,
                    trigger_start_price=_parse_price(
                        row_number, trigger_start, row[trigger_start]
                    ),
                    trigger_end_price=_parse_price(
                        row_number, trigger_end, row[trigger_end]
                    ),
                    loss_start_price=_parse_price(
                        row_number, loss_start, row[loss_start]
                    ),
                    loss_end_price=_parse_price(
                        row_number, loss_end, row[loss_end]
                    ),
                )
            )
    return quotes


def _validate_probability_range(
    label: str,
    minimum: float,
    maximum: float,
) -> None:
    if not 0.0 <= minimum <= maximum <= 1.0:
        raise ValueError(
            f"{label} range must satisfy 0 <= minimum <= maximum <= 1"
        )


def _in_probability_range(
    value: float,
    minimum: float,
    maximum: float,
) -> bool:
    """Return whether a probability is inside an inclusive range."""
    return (
        minimum - PROBABILITY_EPSILON
        <= value
        <= maximum + PROBABILITY_EPSILON
    )


def run_paired_hedge_strategy(
    path: Path,
    *,
    trigger_prefix: str,
    loss_prefix: str,
    namespace: str,
    threshold: float = 0.70,
    trigger_max: float = 1.0,
    championship_win_min: float = 0.0,
    championship_win_max: float = 1.0,
    stake_per_trade: float = 100.0,
    initial_cash: float = 1_000.0,
    fee_rate: float = 0.0,
) -> StrategyResult:
    """Buy paired hedges whose trigger and outright odds fit both ranges."""
    _validate_probability_range(
        "trigger probability",
        threshold,
        trigger_max,
    )
    _validate_probability_range(
        "championship win probability",
        championship_win_min,
        championship_win_max,
    )
    if stake_per_trade <= 0.0:
        raise ValueError("stake_per_trade must be positive")
    if not 0.0 <= fee_rate < 1.0:
        raise ValueError("fee_rate must be in [0, 1)")

    selected = tuple(
        quote
        for quote in load_hedge_quotes(
            path, trigger_prefix, loss_prefix, namespace
        )
        if _in_probability_range(
            quote.trigger_start_price,
            threshold,
            trigger_max,
        )
        and _in_probability_range(
            1.0 - quote.loss_start_price,
            championship_win_min,
            championship_win_max,
        )
    )
    hedges = []
    for quote in selected:
        loss_quantity = stake_per_trade / (1.0 - fee_rate)
        loss_cost = (
            loss_quantity * quote.loss_start_price * (1.0 + fee_rate)
        )
        trigger_budget = stake_per_trade - loss_cost
        if trigger_budget <= 0.0:
            raise ValueError(
                f'Cannot build a break-even hedge for "{quote.team}" '
                "with these prices and fees"
            )
        if quote.trigger_start_price == 0.0:
            raise ValueError("Cannot buy a trigger token at a zero price")
        trigger_quantity = trigger_budget / (
            quote.trigger_start_price * (1.0 + fee_rate)
        )
        hedges.append(
            HedgePosition(quote, trigger_quantity, loss_quantity)
        )

    schedule: dict[datetime, list[_Action]] = defaultdict(list)
    for hedge in hedges:
        schedule[hedge.quote.start_time].append(_Action("open", hedge))
        schedule[hedge.quote.end_time].append(_Action("close", hedge))

    engine = BacktestEngine(initial_cash=initial_cash, fee_rate=fee_rate)
    for timestamp in sorted(schedule):
        actions = schedule[timestamp]
        prices = {}
        for action in actions:
            quote = action.hedge.quote
            is_open = action.kind == "open"
            prices[quote.trigger_instrument] = (
                quote.trigger_start_price
                if is_open
                else quote.trigger_end_price
            )
            prices[quote.loss_instrument] = (
                quote.loss_start_price if is_open else quote.loss_end_price
            )
        engine.update_prices(timestamp, prices)

        for action in sorted(actions, key=lambda item: item.kind):
            hedge = action.hedge
            side = Side.SELL if action.kind == "close" else Side.BUY
            engine.execute(
                Order(
                    hedge.quote.trigger_instrument,
                    side,
                    hedge.trigger_quantity,
                )
            )
            engine.execute(
                Order(
                    hedge.quote.loss_instrument,
                    side,
                    hedge.loss_quantity,
                )
            )

    return StrategyResult(selected, tuple(hedges), engine.trades, engine.stats())


def print_strategy_result(
    result: StrategyResult,
    trigger_label: str,
    loss_label: str,
) -> None:
    print(f"Qualifying teams: {len(result.selected)}")
    sell_pnl = {
        trade.instrument: trade.realized_pnl
        for trade in result.trades
        if trade.side is Side.SELL
    }
    hedge_pnls = []
    for hedge in result.hedges:
        quote = hedge.quote
        combined_pnl = (
            sell_pnl[quote.trigger_instrument]
            + sell_pnl[quote.loss_instrument]
        )
        hedge_pnls.append(combined_pnl)
        print(
            f"  {quote.team}: {trigger_label} "
            f"{quote.trigger_start_price:.1%}, {loss_label} "
            f"{quote.loss_start_price:.1%}, P&L ${combined_pnl:.2f}"
        )
    stats = result.stats
    print(f"Trades: {stats.trade_count}")
    print(f"Ending equity: ${stats.ending_equity:.2f}")
    print(f"Total P&L: ${stats.total_pnl:.2f}")
    print(
        "Total return: "
        + (
            f"{stats.total_return:.2%}"
            if stats.total_return is not None
            else "undefined"
        )
    )
    print(f"Winning hedges: {sum(pnl > 0.0 for pnl in hedge_pnls)}")
    print(f"Losing hedges: {sum(pnl < 0.0 for pnl in hedge_pnls)}")
    print(f"Open positions: {stats.open_positions}")


def run_sport_strategy(
    sport: str,
    csv_path: Path | None = None,
    *,
    threshold: float = 0.70,
    trigger_max: float = 1.0,
    championship_win_min: float = 0.0,
    championship_win_max: float = 1.0,
    stake_per_trade: float = 100.0,
    initial_cash: float = 1_000.0,
    fee_rate: float = 0.0,
) -> StrategyResult:
    """Run the shared paired-hedge strategy for a selected sport."""
    config = get_sport_config(sport)
    return run_paired_hedge_strategy(
        csv_path or config.csv_path,
        trigger_prefix=config.trigger_prefix,
        loss_prefix=config.loss_prefix,
        namespace=config.namespace,
        threshold=threshold,
        trigger_max=trigger_max,
        championship_win_min=championship_win_min,
        championship_win_max=championship_win_max,
        stake_per_trade=stake_per_trade,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
    )


def _sport_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the shared paired win/loss hedge strategy."
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
    parser.add_argument(
        "--threshold",
        "--trigger-min",
        dest="threshold",
        type=float,
        default=0.70,
        help="minimum match/series win probability (inclusive)",
    )
    parser.add_argument(
        "--trigger-max",
        type=float,
        default=1.0,
        help="maximum match/series win probability (inclusive)",
    )
    parser.add_argument(
        "--championship-win-min",
        type=float,
        default=0.0,
        help="minimum championship win probability (inclusive)",
    )
    parser.add_argument(
        "--championship-win-max",
        type=float,
        default=1.0,
        help="maximum championship win probability (inclusive)",
    )
    parser.add_argument("--stake", type=float, default=100.0)
    parser.add_argument("--initial-cash", type=float, default=1_000.0)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    return parser


def sport_strategy_cli(argv: list[str] | None = None) -> int:
    parser = _sport_parser()
    args = parser.parse_args(argv)
    try:
        config = get_sport_config(args.sport)
        result = run_sport_strategy(
            args.sport,
            args.csv,
            threshold=args.threshold,
            trigger_max=args.trigger_max,
            championship_win_min=args.championship_win_min,
            championship_win_max=args.championship_win_max,
            stake_per_trade=args.stake,
            initial_cash=args.initial_cash,
            fee_rate=args.fee_rate,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"{config.display_name} - paired hedge")
    print(
        "Trigger win range: "
        f"{args.threshold:.1%}-{args.trigger_max:.1%} | "
        "championship win range: "
        f"{args.championship_win_min:.1%}-"
        f"{args.championship_win_max:.1%}"
    )
    print_strategy_result(
        result,
        config.trigger_label,
        config.loss_label,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return sport_strategy_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
